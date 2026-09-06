#!/usr/bin/env python3
"""Publish only the reviewed current main; no retries or tag replacement."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote


REPO = "Fluxyard-Inc/images"
SOURCE = "https://github.com/" + REPO
NAMES = ("workspace", "workspace-custom")
INPUTS = ("Dockerfile", "requirements.lock", "models.lock.json", "THIRD_PARTY.md",
          "examples/workload.py", "examples/requirements.lock", "examples/data/train.txt",
          "examples/data/eval.txt", "examples/data/prompt.txt", "examples/data/image.json",
          "custom/Dockerfile", "custom/run.py")
SHA = r"[0-9a-f]{40}"
DIGEST = r"sha256:[0-9a-f]{64}"
LIMIT = 2 * 1024 * 1024
DEADLINE = time.monotonic() + 28 * 60
# Do not inherit tokens, proxy settings, Docker overrides, Git config or helpers.
ENV = {"PATH": os.environ.get("PATH", os.defpath), "LANG": "C.UTF-8",
       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}

# The check runs with no network, credentials, GPU or writable root filesystem.
IMAGE_CHECK = r'''
from importlib import metadata
from pathlib import Path
import shutil
import subprocess
import sys
import torch, transformers, diffusers, safetensors, venv
assert torch.__version__.split('+')[0] == '2.8.0'
assert torch.version.cuda == '12.8'
assert metadata.version('nvidia-cudnn-cu12') == '9.10.2.21'
assert metadata.distribution('nvidia-cudnn-cu12').locate_file(
    'nvidia_cudnn_cu12-9.10.2.21.dist-info/licenses/License.txt').stat().st_size
for line in Path('/opt/fluxyard/requirements.lock').read_text().splitlines():
    if line and not line.startswith('#'):
        name, version = line.split()[0].split('==')
        assert metadata.version(name) == version
for package in ('torch', 'transformers', 'diffusers', 'nvidia-cudnn-cu12'):
    distribution = metadata.distribution(package)
    notices = [p for p in distribution.files or () if 'license' in p.name.lower()]
    assert notices and all(distribution.locate_file(p).is_file() for p in notices)
    assert any(distribution.locate_file(p).stat().st_size for p in notices)
for package in ('openssh-sftp-server', 'tmux', 'curl', 'coreutils'):
    assert (Path('/usr/share/doc') / package / 'copyright').stat().st_size
for tool in ('bash', 'curl', 'tmux', 'sha256sum'):
    assert shutil.which(tool)
assert Path('/usr/lib/openssh/sftp-server').is_file()
assert Path('/opt/fluxyard/THIRD_PARTY.md').stat().st_size
assert Path('/opt/fluxyard/examples/workload.py').is_file()
subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True, timeout=45)
print('image-validation-ok')
'''


class Refusal(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


def command(args, data=b"", timeout=30, limit=LIMIT, reason="command-failed", cleanup=False):
    """Bound all streams, including a child that stalls or never closes stdout."""
    expires = time.monotonic() + timeout
    if not cleanup:
        expires = min(expires, DEADLINE)
    output = bytearray()
    total = 0
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=ENV, start_new_session=True)
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            if data:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            position = 0
            while selector.get_map():
                remaining = expires - time.monotonic()
                require(remaining > 0, reason)
                for key, _ in selector.select(min(remaining, 0.5)):
                    stream = key.fileobj
                    if stream is process.stdin:
                        try:
                            position += os.write(stream.fileno(), data[position:position + 65536])
                        except BrokenPipeError:
                            position = len(data)
                        if position == len(data):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        block = os.read(stream.fileno(), 65536)
                        if not block:
                            selector.unregister(stream)
                        total += len(block)
                        require(total <= limit, reason)
                        if stream is process.stdout:
                            output.extend(block)
            require(process.wait(timeout=max(0.01, expires - time.monotonic())) == 0, reason)
        return bytes(output)
    except subprocess.TimeoutExpired:
        raise Refusal(reason) from None
    finally:
        # Also kill descendants retaining pipes after the command exits.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def request(url, authorization, reason="registry-response"):
    require(url.startswith(("https://api.github.com/", "https://ghcr.io/")), reason)
    require("\n" not in authorization and "\r" not in authorization, reason)
    headers = ("Authorization: " + authorization + "\nAccept: application/vnd.oci.image.manifest.v1+json, "
               "application/vnd.docker.distribution.manifest.v2+json, application/vnd.github+json\n").encode()
    raw = command(["curl", "--disable", "--silent", "--show-error", "--include", "--proto", "=https",
                   "--noproxy", "*", "--connect-timeout", "10", "--max-time", "30", "--max-redirs", "0",
                   "--max-filesize", str(LIMIT), "--header", "@-", url], headers, timeout=35, reason=reason)
    head, separator, body = raw.partition(b"\r\n\r\n")
    require(separator and len(head) <= 16384, reason)
    lines = head.decode("ascii").split("\r\n")
    require(re.fullmatch(r"HTTP/(?:1\.[01]|2|3) [0-9]{3}(?: .*)?", lines[0]), reason)
    status = int(lines[0].split()[1])
    require(not 300 <= status < 400, reason)
    parsed = {}
    for line in lines[1:]:
        key, separator, value = line.partition(":")
        require(separator and key.lower() not in parsed, reason)
        parsed[key.lower()] = value.strip()
    return status, parsed, body


def github(path, token):
    status, _, body = request("https://api.github.com/" + path, "Bearer " + token, "source-revision")
    require(status == 200, "source-revision")
    return json.loads(body)


def current_main(sha, token):
    require(github_object_sha("heads/main", token) == sha, "source-revision")


def github_object_sha(ref, token):
    obj = github("repos/" + REPO + "/git/ref/" + ref, token)["object"]
    for _ in range(4):
        if obj["type"] == "commit":
            require(re.fullmatch(SHA, obj["sha"]), "source-revision")
            return obj["sha"]
        require(obj["type"] == "tag" and re.fullmatch(SHA, obj["sha"]), "source-revision")
        obj = github("repos/" + REPO + "/git/tags/" + obj["sha"], token)["object"]
    raise Refusal("source-revision")


def registry(name, reference, token, actor):
    credentials = base64.b64encode((actor + ":" + token).encode()).decode()
    scope = quote("repository:fluxyard-inc/" + name + ":pull", safe="")
    status, _, body = request("https://ghcr.io/token?service=ghcr.io&scope=" + scope, "Basic " + credentials)
    require(status == 200, "registry-authentication")
    bearer = json.loads(body)["token"]
    require(isinstance(bearer, str) and 0 < len(bearer) <= 16384, "registry-authentication")
    return request("https://ghcr.io/v2/fluxyard-inc/" + name + "/manifests/" + reference, "Bearer " + bearer)


def absent(name, tag, token, actor):
    status, _, body = registry(name, tag, token, actor)
    require(status == 404, "tag-exists-or-unavailable")
    errors = json.loads(body).get("errors", [])
    require(errors and all(e.get("code") in ("MANIFEST_UNKNOWN", "NAME_UNKNOWN") for e in errors),
            "tag-exists-or-unavailable")


def manifest(name, tag, image_id, token, actor):
    status, headers, body = registry(name, tag, token, actor)
    require(status == 200, "published-manifest-unverified")
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    require(headers.get("docker-content-digest") == digest, "published-manifest-unverified")
    value = json.loads(body)
    require(value.get("schemaVersion") == 2 and value.get("mediaType") in
            ("application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json")
            and value.get("config", {}).get("digest") == image_id, "published-manifest-unverified")
    return digest


def main():
    summary = Path(os.environ["GITHUB_STEP_SUMMARY"])
    summary.write_text("## Image publication\n\n", encoding="utf-8")

    def record(text):
        with summary.open("a", encoding="utf-8") as stream:
            stream.write(text + "\n")
        print(text, flush=True)

    try:
        sha = os.environ.get("GITHUB_SHA", "")
        token = os.environ.pop("GITHUB_TOKEN", "")
        actor = os.environ.get("GITHUB_ACTOR", "")
        require(re.fullmatch(SHA, sha) and token and len(token) <= 16384 and
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}(?:\[bot\])?", actor), "event-contract")
        require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_REPOSITORY") == REPO
                and os.environ.get("GITHUB_WORKFLOW_SHA") == sha, "source-revision")
        event_path = Path(os.environ["GITHUB_EVENT_PATH"])
        require(event_path.stat().st_size <= LIMIT, "event-contract")
        event = json.loads(event_path.read_bytes())
        require(event["repository"]["full_name"] == REPO, "event-contract")
        event_name = os.environ.get("GITHUB_EVENT_NAME")
        ref = os.environ.get("GITHUB_REF", "")
        require(os.environ.get("GITHUB_WORKFLOW_REF") == REPO + "/.github/workflows/publish.yml@" + ref,
                "source-revision")
        release_ref = None
        if event_name == "workflow_dispatch":
            require(ref == "refs/heads/main" and event["inputs"]["expected_sha"] == sha and
                    os.environ.get("EXPECTED_SHA") == sha, "source-revision")
        elif event_name == "release":
            release = event["release"]
            require(event["action"] == "published" and release["draft"] is False and
                    ref == "refs/tags/" + release["tag_name"], "event-contract")
            release_ref = "tags/" + quote(release["tag_name"], safe="")
        else:
            raise Refusal("event-contract")
        require(command(["git", "rev-parse", "HEAD"]).decode().strip() == sha and
                not command(["git", "status", "--porcelain", "--untracked-files=all"]), "source-revision")
        def validate_remote():
            current_main(sha, token)
            if release_ref:
                require(github_object_sha(release_ref, token) == sha, "source-revision")

        validate_remote()
        run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
        require(re.fullmatch(r"[0-9]{1,20}", run_id) and attempt == "1", "event-contract")
        record("source: `" + sha + "`; run: " + SOURCE + "/actions/runs/" + run_id)
        archive = command(["git", "archive", "--format=tar", sha, "--", *INPUTS])
        record("reviewed-context-sha256: `" + hashlib.sha256(archive).hexdigest() + "`")
        recipe = command(["git", "show", sha + ":Dockerfile"]).decode()
        base = re.search(r"^FROM (docker.io/pytorch/pytorch@sha256:[0-9a-f]{64})$", recipe, re.M)
        require(base is not None, "immutable-inputs")
        record("base: `" + base[1] + "`")
        for name in ("requirements.lock", "examples/requirements.lock", "models.lock.json"):
            content = command(["git", "show", sha + ":" + name])
            record(name + " sha256: `" + hashlib.sha256(content).hexdigest() + "`")
        tag = "pilot-" + sha
        for name in NAMES:
            absent(name, tag, token, actor)
        with tempfile.TemporaryDirectory(prefix="fluxyard-publisher-") as temporary:
            directory = Path(temporary)
            ENV["HOME"] = temporary
            authenticated, anonymous = directory / "authenticated", directory / "anonymous"
            for config in (authenticated, anonymous):
                config.mkdir(mode=0o700)
                (config / "config.json").write_text(json.dumps({"auths": {"ghcr.io": {}, "https://index.docker.io/v1/": {}}}))
                (config / "config.json").chmod(0o600)
            docker = ["docker", "--config", str(authenticated)]
            command(docker + ["login", "ghcr.io", "--username", actor, "--password-stdin"],
                    (token + "\n").encode(), reason="registry-login")
            published = {}
            for name in NAMES:
                image = "ghcr.io/fluxyard-inc/" + name + ":" + tag
                build = docker + ["build", "--platform", "linux/amd64", "--provenance=false", "--label",
                                  "org.opencontainers.image.revision=" + sha, "-t", image]
                if name == "workspace-custom":
                    build += ["-f", "custom/Dockerfile", "--build-arg",
                              "WORKSPACE_IMAGE=ghcr.io/fluxyard-inc/workspace@" + published["workspace"]]
                command(build + ["-"], archive, timeout=900, limit=8 * LIMIT, reason="image-build")
                inspection = json.loads(command(docker + ["image", "inspect", image]))
                require(len(inspection) == 1, "image-validation")
                value = inspection[0]
                labels = value["Config"].get("Labels", {})
                require(value["Os"] == "linux" and value["Architecture"] == "amd64" and
                        labels.get("org.opencontainers.image.source") == SOURCE and
                        labels.get("org.opencontainers.image.revision") == sha and
                        not value["Config"].get("Volumes") and re.fullmatch(DIGEST, value["Id"]), "image-validation")
                container = command(docker + ["create", "--network=none", "--read-only", "--user=65532:65532",
                    "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=2g", "--pids-limit=64",
                    "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864", "--workdir=/tmp", "--no-healthcheck",
                    "--label=io.fluxyard.publisher=" + sha, "--entrypoint=python", image, "-I", "-c", IMAGE_CHECK],
                    reason="image-validation").decode().strip()
                require(re.fullmatch(r"[0-9a-f]{64}", container), "image-validation")
                try:
                    checked = command(docker + ["start", "--attach", container], timeout=90, reason="image-validation")
                    require(checked.endswith(b"image-validation-ok\n"), "image-validation")
                finally:
                    command(docker + ["rm", "--force", container], timeout=15, reason="validation-cleanup", cleanup=True)
                validate_remote()
                absent(name, tag, token, actor)
                record(name + ": push-started; tag `" + tag + "`; inspect this tag before any retry")
                command(docker + ["push", image], timeout=600, limit=8 * LIMIT, reason="push-outcome-unknown")
                digest = manifest(name, tag, value["Id"], token, actor)
                published[name] = digest
                record(name + ": published `ghcr.io/fluxyard-inc/" + name + "@" + digest + "`")
            for name in NAMES:
                status, _, body = request("https://api.github.com/orgs/Fluxyard-Inc/packages/container/" + name,
                                          "Bearer " + token, "package-visibility-unverified")
                require(status == 200 and json.loads(body).get("visibility") == "public", "public-visibility-pending")
            for name, digest in published.items():
                command(["docker", "--config", str(anonymous), "pull", "--platform", "linux/amd64",
                         "ghcr.io/fluxyard-inc/" + name + "@" + digest], timeout=600, limit=8 * LIMIT,
                        reason="anonymous-pull-unverified")
                record(name + ": anonymous exact-digest pull verified")
        record("result: published-and-anonymously-pullable; not GPU acceptance or catalog activation")
        return 0
    except Refusal as error:
        record("result: stopped; reason: " + str(error))
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        record("result: stopped; reason: invalid-input-or-response")
    return 1


if __name__ == "__main__":
    sys.exit(main())
