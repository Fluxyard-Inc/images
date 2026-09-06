# fluxyard images

Public container recipes and portable GPU examples maintained by Fluxyard Inc.
for fluxyard. This repository does not contain the Control Plane or Worker.

Status: bounded publication automation is included; no image is published yet.
This repository supplies no managed-workspace, GPU, network or storage acceptance.
Local tags and image IDs below are not published registry manifest digests.

## Publication contract (#3)

First publication is an explicit manual dispatch with a full source SHA.
Subsequent publication may also follow an explicitly published GitHub Release.
Ordinary PRs, main pushes and schedules never build or push images. Each event
uses one Linux amd64 job capped at 30 minutes, serialized across both triggers,
without a matrix, automatic retry, cache upload or artifact upload. Never cancel
an active publisher just because another request arrives; stale queued sources
must fail before publication. This is separate from the private product's CI.

Only this repository's reviewed current main is eligible. Match event SHA,
workflow SHA, checkout and remote main; a manual dispatch additionally matches
its expected SHA, and a release matches its actual tag target. Recheck before
publishing after a build. Source changes follow the internal exact-commit review
and direct-main policy below; a PR is not required. The first hosted publication occurs
after these local checks; its success is image-build evidence, not GPU acceptance.

Targets are `ghcr.io/fluxyard-inc/workspace` and
`ghcr.io/fluxyard-inc/workspace-custom`, tagged `pilot-<full-source-sha>` only.
Never overwrite a tag or publish `latest`. Check both tags before effects and
each again before its push; distinguish an authenticated missing manifest from
authentication, rate-limit, network or server failures. These checks are not an
atomic registry immutability guarantee. Stop on uncertainty or partial publication
and inspect the recorded outcome before any retry; do not rebuild successful tags.

Build the reviewed recipes with immutable inputs. Inspect actual image source/
revision labels and required tools/dependencies, and retain distribution notices.
The custom image must derive from the newly published curated manifest digest,
not a local ID or mutable tag. Record source, input pins, run and manifest digests
in the workflow summary and normal logs, including partial success before a later failure.
Public package visibility is a separate first-publication setting; a private
package is not anonymous-pull success. Require fresh credential-free exact-digest
pulls before catalog activation; do not weaken that check to make a run green.

Use only the job's short-lived `GITHUB_TOKEN`, with contents read/packages write.
Keep credentials out of command arguments, build inputs, image layers, output
and test fixtures. Bound subprocess/API time, capture and cleanup, reject unsafe
redirects, and use private temporary client configuration. Never export ambient
Docker/CLI credentials. Publication does not activate templates or deploy fluxyard.

Test the publisher's command boundary with synthetic event/registry/Docker
outcomes for exact revision, duplicate/changed tags, partial failure and secret-safe
refusal. Replace only those true external boundaries; no private product fixture
export or new test framework. Real first publication and anonymous pulls remain
required evidence. Missing or skipped GPU/root gates never establish acceptance.

### Running the publisher

After the exact commit's local checks and both internal reviews pass, push it
normally to main. First publication uses Actions -> Publish pilot images ->
Run workflow, main, with that full commit in `expected_sha`. Subsequent explicit
GitHub Releases at current main may trigger the same job. A release for an
already published source stops at the existing tag; it is not a rebuild request.

Run `python3 -B tests/test_publish.py` and `actionlint .github/workflows/publish.yml`
locally before delivery. The checks use real temporary Git repositories and
inert registry/Docker commands, not real credentials, builds or GPU workloads.
The first actual hosted publication supplies the image-build evidence.

The workflow summary records each successful push immediately. If it stops at
`public-visibility-pending`, both images may already exist privately: make their
packages public through GitHub's documented package settings, then independently
verify the recorded exact digests with a fresh credential-free client. Do not
rerun publication to change visibility. Any unknown push outcome needs registry
inspection before another attempt; no automated retries or successful-tag rebuilds.

Limits: 28 minutes for the publisher inside the 30-minute job; 30 seconds per HTTP
request, 15 minutes per build, 10 minutes per push/pull, and 90 seconds for each
CPU-only image check, all within that total. Combined command capture is 2 MiB
(16 MiB for build/push/pull); reviewed build context and event input are each
capped at 2 MiB. Exceeding a bound stops publication. Validation containers are
removed by exact returned ID with a separate 15-second cleanup allowance, and
temporary client configuration is removed on normal success or failure. The
disposable hosted runner owns build layers; no shared Docker pruning is used.

## Build recipes

The curated Linux amd64 image pins PyTorch 2.8.0 / CUDA 12.8 / cuDNN 9 by its
upstream manifest digest. Ubuntu packages use a dated signed snapshot; Python
wheels are version/hash-pinned in [requirements.lock](requirements.lock).
Pins support reproducible inputs, not a vulnerability-free guarantee.

Build from a reviewed, clean checkout at the repository root. Use a fresh Docker
client configuration with an explicit credential-free `auths` entry and unset
Docker's environment auth override. An empty directory alone can auto-select a
system credential helper:

```sh
image_client_config=$(mktemp -d)
printf '%s\n' '{"auths":{"https://index.docker.io/v1/":{}}}' > "$image_client_config/config.json"
unset DOCKER_AUTH_CONFIG
image_source_revision=$(git rev-parse HEAD)
docker --config "$image_client_config" build --platform linux/amd64 \
  --label "org.opencontainers.image.revision=$image_source_revision" \
  -t fluxyard-workspace:local .
```

The build downloads substantial CUDA dependencies. Check available disk space
first; do not prune unrelated images. It installs Bash, coreutils, curl, tmux,
OpenSSH's SFTP subsystem, Python, PyTorch, Transformers and Diffusers. It does not
start an SSH daemon or expose a service. The default user is UID/GID 65532.

The managed workspace must supply its writable quota-bound `/workspace`, fixed
non-root/read-only policy, exact GPU assignment and authenticated native access.
Those controls are not established by this Dockerfile. Keep required image code
under `/opt`, because managed scratch masks files baked beneath `/workspace`.
Do not disable certificate verification or add private registry/model tokens.

## Three portable examples

[examples/workload.py](examples/workload.py) supports training, inference and
unconditional 32x32 DDPM image generation, not a browser application or public
inference API. The input corpus and prompt are synthetic example text.
[models.lock.json](models.lock.json) records the immutable public model revisions
and their upstream-declared licenses. Models are downloaded when a command runs;
the recipe does not bake their weights into the image. CUDA is explicit, with
no silent CPU fallback. Use `--device cpu` for a deliberately non-GPU run.

Inside a compatible workspace, create the writable virtual environment and run
the examples using the files baked into the image:

```sh
python -m venv --system-site-packages /workspace/venv
/workspace/venv/bin/python -m pip install --ignore-installed --no-deps \
  --require-hashes -r /opt/fluxyard/examples/requirements.lock
/workspace/venv/bin/python /opt/fluxyard/examples/workload.py training \
  --device cuda --data /opt/fluxyard/examples/data \
  --output /workspace/training --steps 2
/workspace/venv/bin/python /opt/fluxyard/examples/workload.py inference \
  --device cuda --input /opt/fluxyard/examples/data/prompt.txt \
  --output /workspace/inference
/workspace/venv/bin/python /opt/fluxyard/examples/workload.py image_generation \
  --device cuda --input /opt/fluxyard/examples/data/image.json \
  --output /workspace/image
```

For editable code or inputs, transfer `examples/` to a temporary name beneath
`/workspace` using your provider's authenticated SSH/SFTP configuration. Verify
important byte hashes, rename it to `/workspace/project`, then substitute that
path for `/opt/fluxyard/examples` above. Preserve host-key verification. These
examples neither provision a rental nor supply connection credentials.

Training writes `checkpoint.pt` and `result.json`; inference writes
`result.json`; image generation writes `image.png` and `result.json`. Retrieve
them with SFTP and verify recorded hashes before releasing the workspace.
Decode the PNG and inspect the recorded evaluation/output, not just GPU memory.

Interrupted transfers can leave partial files. Resume only when the source is
unchanged and the partial prefix matches; otherwise restart the transfer.
On a fresh rental, upload the saved checkpoint and identical project/input
files, verify them, recreate the venv and add
`--resume /workspace/training/checkpoint.pt` to the training command. `--steps 2`
means two additional steps. The checkpoint includes model, optimizer, RNG and
step state. Budget space for both the old and replacement checkpoint.

Release deletes workspace data; these examples provide no archive or recovery
guarantee. Disconnecting SSH is not release, and idle/disconnected rentals may
remain billable. Use explicit provider release controls after saving outputs.

## Custom compatibility fixture

[custom/Dockerfile](custom/Dockerfile) bakes [custom/run.py](custom/run.py)
independently. It deliberately declares root, conflicting entrypoint/working
directory, failing healthcheck and unusual stop-signal metadata to test managed
profile overrides. **Do not deploy its default startup as an ordinary service.**
It is not a recommended root-container recipe. Normal derived images should
retain `USER 65532:65532` and compatible startup metadata.

For a local recipe build, using the same repository-root context:

```sh
docker --config "$image_client_config" build --platform linux/amd64 \
  --label "org.opencontainers.image.revision=$image_source_revision" \
  --build-arg WORKSPACE_IMAGE=fluxyard-workspace:local \
  -f custom/Dockerfile -t fluxyard-workspace-custom:local .
```

A release build must replace that local base reference with the reviewed public
manifest digest. In a managed workspace that enforces the fixed overrides,
`python /opt/project/run.py --device cuda` writes `/workspace/custom-result.json`;
retrieve it before release. No privileged mode, extra mounts or public ports
are justified by a compatibility failure.

## Source review

While this repository has no external collaborators, focused commits may be
pushed directly to main after independent internal specification and standards
reviews and relevant checks pass at the exact candidate SHA. Record that SHA
and the review/check results on the associated issue. PRs are optional here;
revisit mandatory PRs when external collaborators join. Do not force-push or
reuse reviews after changing the candidate. This exception does not alter the
private fluxyard repository's PR workflow. A source push does not authorize or
trigger image publication, deployment or additional CI runs.

## Provenance and third-party components

This repository is the canonical source for these recipes and examples. Review
changes here; record the clean source commit, build inputs and resulting registry
manifest digest together. Both recipes identify this repository with the OCI
source label. The bounded publisher above has owner approval; additional targets,
triggers or deployment still require separate approval. Source inspection does not audit cached
image layers or establish deployment compatibility.

No project-wide source license has been selected. Public visibility is not a
blanket open-source license grant. Upstream PyTorch/CUDA, Ubuntu, Python packages
and downloaded models retain their own terms and notices; model declarations
do not license the whole image. Preserve upstream notices during distribution.
Consult the pinned model cards linked in `models.lock.json` for limitations:
DistilGPT2 is not a factual or safety-tuned assistant, and the small DDPM example
does not demonstrate high-resolution or prompt-conditioned image quality.
