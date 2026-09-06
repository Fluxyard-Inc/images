"""Publisher CLI checks; git is real, registry and Docker commands are inert."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PUBLISHER = Path(__file__).resolve().parents[1] / "scripts/publish.py"
STUB = r'''#!/usr/bin/python3
import hashlib, io, json, os, pathlib, sys, tarfile, time
root = pathlib.Path(__file__).resolve().parent
path = root / "state.json"
state = json.loads(path.read_text())
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
data = sys.stdin.buffer.read()
assert not any("synthetic-job-token" in a or "synthetic-registry-token" in a for a in args)
assert "GITHUB_TOKEN" not in os.environ and "DOCKER_AUTH_CONFIG" not in os.environ
assert "AWS_SECRET_ACCESS_KEY" not in os.environ and "HTTP_PROXY" not in os.environ
state.setdefault("calls", []).append([tool] + args)
def save(): path.write_text(json.dumps(state))
def manifest_body(kind):
    return json.dumps({"schemaVersion": 2, "mediaType": state.get("media_type", "application/vnd.oci.image.manifest.v1+json"), "config": {"digest": "sha256:" + kind * 64}, "layers": []}).encode()
def response(status, value, digest=None):
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    print("HTTP/1.1 " + str(status) + " Fixture\r")
    if digest: print("Docker-Content-Digest: " + digest + "\r")
    print("\r")
    sys.stdout.flush(); sys.stdout.buffer.write(body)
    save(); sys.exit()
if tool == "curl":
    assert args[:1] == ["--disable"] and "--location" not in args
    assert "--max-time" in args and args[args.index("--header") + 1] == "@-"
    assert data.startswith(b"Authorization: ")
    if state.get("response_flood"):
        save(); sys.stdout.buffer.write(b"x" * (3 * 1024 * 1024)); sys.exit()
    if state.get("hang"):
        save(); time.sleep(45); sys.exit()
    url = args[-1]
    if "api.github.com" in url:
        if "/packages/container/" in url:
            response(200, {"visibility": state.get("visibility", "public")})
        revision = state["sha"]
        if state.get("stale") or state.get("stale_after_build") and state.get("built"):
            revision = "f" * 40
        if "/git/ref/tags/" in url and (state.get("wrong_tag") or state.get("wrong_tag_after_build") and state.get("built")):
            revision = "e" * 40
        response(200, {"object": {"type": "commit", "sha": revision}})
    if "/token?" in url:
        response(200, {"token": "synthetic-registry-token"})
    name = "workspace-custom" if "/workspace-custom/" in url else "workspace"
    if name not in state.get("published", []):
        status = state.get("tag_status", 404)
        if state.get("tag_race") and state.get("built"): status = 200
        response(status, {"errors": [{"code": state.get("missing_code", "MANIFEST_UNKNOWN")}]})
    config = state.get("manifest_config") or ("d" if name.endswith("custom") else "c")
    body = manifest_body(config)
    if state.get("remote_other_layers"):
        changed = json.loads(body)
        changed["layers"] = [{"digest": "sha256:" + "f" * 64}]
        body = json.dumps(changed).encode()
    response(200, body, "sha256:" + ("f" * 64 if state.get("bad_manifest_digest") else hashlib.sha256(body).hexdigest()))
if tool == "docker":
    while args[0] == "--config": args = args[2:]
    if args[0] == "login":
        assert data == b"synthetic-job-token\n"
        config = pathlib.Path(sys.argv[sys.argv.index("--config") + 1])
        assert config.stat().st_mode & 0o077 == 0
        assert json.loads((config / "config.json").read_text()) == {"auths": {"ghcr.io": {}, "https://index.docker.io/v1/": {}}}
        state["private_config"] = str(config)
    elif args[0] == "build":
        assert "--provenance=false" in args
        archive = tarfile.open(fileobj=io.BytesIO(data))
        names = archive.getnames()
        assert "Dockerfile" in names and "THIRD_PARTY.md" in names
        assert not any(n.startswith(".git") or "private" in n for n in names)
        assert "unrelated.txt" not in names
        assert not any(b"synthetic-job-token" in archive.extractfile(m).read() for m in archive if m.isfile())
        state["built"] = True
        if "custom/Dockerfile" in args:
            base = next(a for a in args if a.startswith("WORKSPACE_IMAGE="))
            assert base.startswith("WORKSPACE_IMAGE=ghcr.io/fluxyard-inc/workspace@sha256:")
            assert "workspace" in state.get("published", [])
    elif args[:2] == ["image", "inspect"]:
        kind = "d" if "workspace-custom" in args[-1] else "c"
        labels = {"org.opencontainers.image.source": "https://github.com/Fluxyard-Inc/images", "org.opencontainers.image.revision": state["sha"]}
        if state.get("bad_label"): labels["org.opencontainers.image.revision"] = "f" * 40
        identity = "sha256:" + (hashlib.sha256(manifest_body(kind)).hexdigest() if state.get("modern_store") else kind * 64)
        value = {"Id": identity, "Os": "linux", "Architecture": "amd64", "Config": {"Labels": labels}}
        if state.get("modern_store"):
            value["Descriptor"] = {"digest": identity, "mediaType": state.get("media_type", "application/vnd.oci.image.manifest.v1+json"),
                                   "annotations": {"config.digest": "sha256:" + kind * 64}}
        if state.get("unrelated_inspect_id"): value["Id"] = "sha256:" + "f" * 64
        if state.get("missing_config_digest"): value["Descriptor"]["annotations"] = {}
        if state.get("bad_config_digest"): value["Descriptor"]["annotations"]["config.digest"] = "not-a-digest"
        if state.get("null_descriptor"): value["Descriptor"] = None
        if state.get("empty_descriptor"): value["Descriptor"] = {}
        if state.get("invalid_legacy_id"): value["Id"] = "not-an-image-id"
        if state.get("oversized_inspect"): value["padding"] = "x" * (2 * 1024 * 1024)
        print(json.dumps([value]))
    elif args[0] == "create":
        assert "--network=none" in args and "--read-only" in args and "--user=65532:65532" in args
        print("e" * 64)
        state["active_container"] = "e" * 64
    elif args[0] == "start":
        if state.get("bad_image"): save(); sys.exit(1)
        print("image-validation-ok")
    elif args[0] == "rm":
        assert args == ["rm", "--force", "e" * 64]
        state.pop("active_container", None)
    elif args[0] == "push":
        name = "workspace-custom" if "workspace-custom:" in args[-1] else "workspace"
        if name.endswith("custom") and state.get("fail_custom"):
            save(); print("synthetic-job-token", file=sys.stderr); sys.exit(1)
        state.setdefault("published", []).append(name)
    elif args[0] == "pull":
        assert "@sha256:" in args[-1]
        config = pathlib.Path(sys.argv[sys.argv.index("--config") + 1])
        assert str(config) != state["private_config"]
        assert json.loads((config / "config.json").read_text()) == {"auths": {"ghcr.io": {}, "https://index.docker.io/v1/": {}}}
        if state.get("anonymous_failure"): save(); sys.exit(1)
    else: raise AssertionError(args)
    save(); sys.exit()
raise AssertionError(tool)
'''


class PublisherCLI(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for name, content in {
            "Dockerfile": "FROM docker.io/pytorch/pytorch@sha256:" + "a" * 64 + "\n",
            "custom/Dockerfile": "ARG WORKSPACE_IMAGE\nFROM ${WORKSPACE_IMAGE}\n",
            "custom/run.py": "print('custom')\n",
            "examples/workload.py": "print('work')\n",
            "examples/requirements.lock": "example==1 --hash=sha256:" + "b" * 64 + "\n",
            "examples/data/train.txt": "Synthetic training text.\n",
            "examples/data/eval.txt": "Synthetic evaluation text.\n",
            "examples/data/prompt.txt": "Synthetic prompt.\n",
            "examples/data/image.json": '{"seed":23,"steps":100}\n',
            "requirements.lock": "example==1 --hash=sha256:" + "b" * 64 + "\n",
            "models.lock.json": '{"models": []}\n',
            "THIRD_PARTY.md": "Synthetic notice fixture.\n",
            "unrelated.txt": "Not an approved build input.\n",
        }.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        self.sha = self.git("rev-parse", "HEAD").strip()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        for name in ("curl", "docker"):
            path = self.tools / name
            path.write_text(STUB)
            path.chmod(0o755)
        self.state = {"sha": self.sha}
        self.event = {"repository": {"full_name": "Fluxyard-Inc/images"}, "inputs": {"expected_sha": self.sha}}
        self.env = {
            "PATH": str(self.tools) + os.pathsep + os.defpath,
            "HOME": str(self.root), "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "Fluxyard-Inc/images", "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_SHA": self.sha, "GITHUB_WORKFLOW_SHA": self.sha,
            "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_REF": "Fluxyard-Inc/images/.github/workflows/publish.yml@refs/heads/main",
            "GITHUB_WORKSPACE": str(self.repo), "GITHUB_EVENT_PATH": str(self.root / "event.json"),
            "GITHUB_STEP_SUMMARY": str(self.root / "summary.md"), "GITHUB_RUN_ID": "12345",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_ACTOR": "fixture", "EXPECTED_SHA": self.sha,
            "GITHUB_TOKEN": "synthetic-job-token", "DOCKER_AUTH_CONFIG": "synthetic-ambient-auth",
            "AWS_SECRET_ACCESS_KEY": "synthetic-ambient-key", "HTTP_PROXY": "http://127.0.0.1:9",
        }

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.DEVNULL, text=True)

    def publish(self, timeout=15):
        (self.tools / "state.json").write_text(json.dumps(self.state))
        Path(self.env["GITHUB_EVENT_PATH"]).write_text(json.dumps(self.event))
        result = subprocess.run([sys.executable, "-B", str(PUBLISHER)], cwd=self.repo, env=self.env, capture_output=True, timeout=timeout)
        summary = Path(self.env["GITHUB_STEP_SUMMARY"])
        self.assertTrue(summary.is_file(), "publisher must provide its bounded outcome receipt")
        self.assertNotIn(b"synthetic-job-token", result.stdout + result.stderr + summary.read_bytes())
        self.assertEqual(result.stdout.decode(), summary.read_text().removeprefix("## Image publication\n\n"),
                         "normal logs must preserve only the safe receipt, including partial failures")
        self.state = json.loads((self.tools / "state.json").read_text())
        if "private_config" in self.state:
            self.assertFalse(Path(self.state["private_config"]).exists(), "private client configuration must be removed")
        self.assertNotIn("active_container", self.state)
        return result.returncode, summary.read_text()

    def test_refuses_stale_source_before_docker(self):
        self.state["stale"] = True
        status, summary = self.publish()
        self.assertEqual(status, 1)
        self.assertIn("source-revision", summary)
        self.assertFalse(any(c[0] == "docker" for c in self.state.get("calls", [])))

    def test_records_curated_digest_before_custom_failure(self):
        self.state["fail_custom"] = True
        status, summary = self.publish()
        self.assertEqual(status, 1)
        self.assertIn("published", summary)
        self.assertIn("sha256:", summary)
        self.assertIn("push-outcome-unknown", summary)
        self.assertEqual(self.state["published"], ["workspace"])

    def test_publication_then_anonymous_pulls(self):
        status, summary = self.publish()
        self.assertEqual(status, 0, summary)
        self.assertEqual(self.state["published"], ["workspace", "workspace-custom"])
        self.assertEqual(summary.count("anonymous exact-digest pull verified"), 2)
        self.assertIn("not GPU acceptance or catalog activation", summary)

    def test_manifest_image_id_is_not_treated_as_config_digest(self):
        for media_type in ("application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"):
            with self.subTest(media_type=media_type):
                self.state = {"sha": self.sha, "modern_store": True, "media_type": media_type}
                status, summary = self.publish()
                self.assertEqual(status, 0, summary)
                self.assertEqual(self.state["published"], ["workspace", "workspace-custom"])
                self.assertEqual(summary.count("anonymous exact-digest pull verified"), 2)

    def test_invalid_inspect_identity_prevents_push(self):
        for key in ("missing_config_digest", "bad_config_digest", "null_descriptor",
                    "empty_descriptor", "unrelated_inspect_id", "oversized_inspect", "invalid_legacy_id"):
            with self.subTest(failure=key):
                self.state = {"sha": self.sha, "modern_store": key != "invalid_legacy_id", key: True}
                status, _ = self.publish()
                self.assertEqual(status, 1)
                self.assertFalse("published" in self.state, "invalid build evidence must stop before any push")
        self.state = {"sha": self.sha, "modern_store": True, "media_type": "application/vnd.oci.image.index.v1+json"}
        status, _ = self.publish()
        self.assertEqual(status, 1)
        self.assertFalse("published" in self.state)

    def test_private_packages_record_both_digests_without_claiming_anonymous_success(self):
        self.state["visibility"] = "private"
        status, summary = self.publish()
        self.assertEqual(status, 1)
        self.assertEqual(self.state["published"], ["workspace", "workspace-custom"])
        self.assertEqual(summary.count(": published `ghcr.io/"), 2)
        self.assertIn("public-visibility-pending", summary)
        self.assertNotIn("anonymous exact-digest pull verified", summary)

    def test_rejects_existing_or_uncertain_tags_before_docker(self):
        for code in (200, 301, 401, 403, 429, 500):
            with self.subTest(status=code):
                self.state = {"sha": self.sha, "tag_status": code}
                status, _ = self.publish()
                self.assertEqual(status, 1)
                self.assertFalse(any(c[0] == "docker" for c in self.state.get("calls", [])))
        self.state = {"sha": self.sha, "missing_code": "UNAUTHORIZED"}
        status, _ = self.publish()
        self.assertEqual(status, 1)
        self.assertFalse(any(c[0] == "docker" for c in self.state.get("calls", [])))

    def test_rejects_changed_or_unverifiable_published_manifest(self):
        for alteration in ({"manifest_config": "f"}, {"bad_manifest_digest": True},
                           {"modern_store": True, "remote_other_layers": True}):
            with self.subTest(alteration=alteration):
                self.state = {"sha": self.sha, **alteration}
                status, summary = self.publish()
                self.assertEqual(status, 1)
                self.assertIn("published-manifest-unverified", summary)
                self.assertEqual(self.state["published"], ["workspace"])
                self.assertNotIn("workspace-custom: published", summary)

    def test_rechecks_source_and_tag_after_build_and_rejects_invalid_image(self):
        for key in ("stale_after_build", "tag_race", "bad_label", "bad_image"):
            with self.subTest(failure=key):
                self.state = {"sha": self.sha, key: True}
                status, _ = self.publish()
                self.assertEqual(status, 1)
                self.assertNotIn("published", self.state)

    def test_manual_revision_and_workflow_identity_are_required(self):
        for key in ("EXPECTED_SHA", "GITHUB_WORKFLOW_SHA", "GITHUB_SHA", "GITHUB_REF", "GITHUB_WORKFLOW_REF"):
            with self.subTest(variable=key):
                previous = self.env[key]
                self.env[key] = "not-the-reviewed-source"
                self.state = {"sha": self.sha}
                status, _ = self.publish()
                self.assertEqual(status, 1)
                self.assertFalse(any(c[0] == "docker" for c in self.state.get("calls", [])))
                self.env[key] = previous

    def test_release_requires_published_event_and_exact_tag_target(self):
        self.env["GITHUB_EVENT_NAME"] = "release"
        self.env["GITHUB_REF"] = "refs/tags/pilot-test"
        self.env["GITHUB_WORKFLOW_REF"] = "Fluxyard-Inc/images/.github/workflows/publish.yml@refs/tags/pilot-test"
        self.event = {"repository": {"full_name": "Fluxyard-Inc/images"}, "action": "published",
                      "release": {"draft": False, "tag_name": "pilot-test"}}
        self.state["wrong_tag"] = True
        status, _ = self.publish()
        self.assertEqual(status, 1)
        self.assertFalse(any(c[0] == "docker" for c in self.state.get("calls", [])))
        self.state = {"sha": self.sha}
        self.event["action"] = "created"
        status, _ = self.publish()
        self.assertEqual(status, 1)
        self.event["action"] = "published"
        self.state = {"sha": self.sha, "wrong_tag_after_build": True}
        status, _ = self.publish()
        self.assertEqual(status, 1)
        self.assertNotIn("published", self.state)
        self.state = {"sha": self.sha}
        status, summary = self.publish()
        self.assertEqual(status, 0, summary)

    def test_unknown_anonymous_result_is_not_success(self):
        self.state["anonymous_failure"] = True
        status, summary = self.publish()
        self.assertEqual(status, 1)
        self.assertEqual(len(self.state["published"]), 2)
        self.assertIn("anonymous-pull-unverified", summary)

    def test_response_flood_is_bounded(self):
        self.state["response_flood"] = True
        status, summary = self.publish()
        self.assertEqual(status, 1)
        self.assertLess(len(summary), 2048)
        self.assertFalse(any(c[0] == "docker" for c in self.state.get("calls", [])))

    def test_stalled_external_process_is_killed(self):
        self.state["hang"] = True
        status, summary = self.publish(timeout=42)
        self.assertEqual(status, 1)
        self.assertIn("source-revision", summary)
        self.assertFalse(any(c[0] == "docker" for c in self.state.get("calls", [])))


if __name__ == "__main__":
    unittest.main()
