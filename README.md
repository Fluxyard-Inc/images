# fluxyard images

Public container recipes and portable GPU examples maintained by Fluxyard Inc.
for fluxyard. This repository does not contain the Control Plane or Worker.

Status: both Linux amd64 pilot images have verified anonymous exact-digest pulls
and restricted CPU tool/package/notice checks. Managed-workspace, GPU, network
and storage acceptance, catalog activation and production deployment remain pending.
Local tags and image IDs in build examples are not published manifest digests.

## Published pilot images

The current images were built from source
[`a964291d49e88eb0d242b335ccacdee1bdb356dd`](https://github.com/Fluxyard-Inc/images/commit/a964291d49e88eb0d242b335ccacdee1bdb356dd).
The [2026-11-17 publication run](https://github.com/Fluxyard-Inc/images/actions/runs/44042591153)
passed source/config binding, restricted CPU dependency/tool/notice checks and
anonymous exact-digest pulls for both images. These checks do not establish GPU
generation quality, latency or downstream template activation.

- Curated: `ghcr.io/fluxyard-inc/workspace@sha256:a8217e30fea58ecef8fa0b4959e85a5ba24365238693d3593b6b3098e088c3b2`
- Compatibility fixture: `ghcr.io/fluxyard-inc/workspace-custom@sha256:fc2f96bfe136a14b9070993d7dac8fcb7fb5ca0eb61ac992ee94f931fe8ac857`

The earlier images built from
[`3219f88081071751085a49431c37f0aebe5ade27`](https://github.com/Fluxyard-Inc/images/commit/3219f88081071751085a49431c37f0aebe5ade27)
retain their [2026-09-06 verification receipt](https://github.com/Fluxyard-Inc/images/issues/3#issuecomment-5565419391).
That receipt records recovery after the
[original publication run failed](https://github.com/Fluxyard-Inc/images/actions/runs/34054927017).
Existing deployments retain their selected image until explicitly upgraded.

`workspace-custom` is a deliberately adversarial test fixture, not a normal
renter image. Read [Custom compatibility fixture](#custom-compatibility-fixture)
before using it.

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
Bind digests using the bounded native image inspection response before pushing.
The classic image store exposes the config digest as `Id` without `Descriptor`.
For descriptor-bearing images, require a single-image manifest matching `Id`
and its `config.digest` annotation. The remote config must match; when inspection
supplies a manifest identity, the remote manifest must match that digest too.
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

## Prompted image and video generation

The published curated image above supplies `fluxyard-generate`. Real GPU
qualification is still required before a provider activates it. The source and
restricted CPU image checks do not establish output quality, latency or
managed-workspace compatibility.

Run these commands inside the workspace's authenticated SSH shell. They use the
allocated local GPU and accept your prompt directly; no browser app, public port,
remote inference API or SSH forwarding is needed:

```sh
fluxyard-generate image \
  --prompt 'A small orange robot watering a rooftop garden at sunrise, cinematic lighting' \
  --seed 23 --output /workspace/demo-image

fluxyard-generate video \
  --prompt 'A small orange robot waters a rooftop garden. Water sparkles in the warm sunrise as the camera moves slowly closer.' \
  --image /workspace/demo-image/image.png \
  --seed 23 --output /workspace/demo-video
```

Omit `--image` to generate video from text alone. The image preset produces a
1024×1024 PNG. The video preset produces a silent 768×512 MP4 with 65 frames at
24 fps (about 2.7 seconds). `--frames 33` makes a shorter preview; `--frames 97`
makes about 4 seconds. An input image is converted to RGB and center-cropped to
the video's aspect ratio. Describe both the scene and its motion in the prompt.
Prompts are passed to the model as text, never evaluated as shell commands;
quote them in the shell, as above.

Each run requires a **new** output directory. It writes `image.png` or
`video.mp4`, plus `result.json` only after successful completion. The report
records the prompt, seed, immutable model references, runner hash, settings,
GPU, preparation/generation/save times and output SHA256. Preparation also reports
cache/download and model-load times separately. Keep prompts you do
not wish to share out of shared reports. The seed is recorded for comparison;
results are not promised to be bit-identical across hardware or library builds.
These process timings are **not rental billing**: loading models and idle time
can also be billable. Download artifacts with SFTP before explicitly releasing
the rental; disconnecting SSH does not release it. An interrupted run retains
its directory and possibly a partial artifact; retry into a new directory.

### Model cache and resources

Prefetch the pinned models before presenting a live demo:

```sh
fluxyard-generate download --mode all
fluxyard-generate image --offline \
  --prompt 'A watercolor painting of a lighthouse above a stormy sea' \
  --output /workspace/offline-image
```

`download --mode image` and `download --mode video` cache only that mode. Models
are downloaded anonymously into the normal Hugging Face cache under `/workspace`;
the command neither needs nor uses a personal Hugging Face token. Downloads use
explicit immutable revisions and allowlisted data files. No model repository
Python is downloaded or executed. `--offline` refuses missing cached files.
The first ordinary generation command can also download its models, so its
preparation time includes any missing download and model loading. Prefetching
caches disk files; it does not keep model weights resident in GPU memory.

The current pins need approximately **32.9 GB for image weights and 25.4 GB for
video weights/configuration** in decimal units. Plan for **80 GiB scratch,
32 GiB system RAM and one 24-GiB-class NVIDIA GPU** for the combined demo. These
are qualification targets, not measured minimums. The existing small-model
template's 8-GiB scratch/RAM request is insufficient. The command uses bfloat16,
model CPU offload, and video VAE tiling. It refuses CPU fallback and more than one
visible GPU; it does not grant GPU access or choose the provider's allocation.
GPU admission, memory isolation, scratch quota and network policy remain the
provider's responsibility. Preserve CUDA/PyTorch pins until a separately reviewed
upgrade. Cold download, warm load, GPU generation, quality and peak resource use
must be measured separately on the intended hardware before promising speed.

### Models and compatibility

- Images use [Z-Image-Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo/blob/f332072aa78be7aecdf3ee76d5c247082da564a6/README.md),
  with its Apache-2.0 declaration and nine pipeline steps (eight model evaluations).
- Videos use the official [LTX 0.9.6 distilled 2B checkpoint](https://huggingface.co/Lightricks/LTX-Video/blob/8984fa25007f376c1a299016d0957a37a2f797bb/README.md),
  with pinned 0.9.5 architecture/tokenizer/text-encoder files. The checkpoint has
  a separate [custom license](https://huggingface.co/Lightricks/LTX-Video/blob/8984fa25007f376c1a299016d0957a37a2f797bb/LTX-Video-Open-Weights-License-0.X.txt);
  the configuration repository carries [Open RAIL-M terms](https://huggingface.co/Lightricks/LTX-Video-0.9.5/blob/e58e28c39631af4d1468ee57a853764e11c1d37e/ltx-video-2b-v0.9.5.license.txt).
  Review these terms for the intended use and distribution before publication;
  the LTX weights are not Apache-licensed. See [THIRD_PARTY.md](THIRD_PARTY.md).

The video adapter binds the checkpoint's eight fixed sigmas and stochastic
sampler to Diffusers 0.36's plain text/image-to-video pipelines. Passing custom
timesteps to those pipelines also passes their default sigmas, which is rejected;
the adapter replaces those sigmas at the scheduler boundary instead. It uses
unshifted sigmas and the positive-noise prediction convention, matching the
[upstream stochastic sampler](https://github.com/Lightricks/LTX-Video/blob/50f0aef1297574a4b29acbdb874e3a363a6d5f2e/ltx_video/schedulers/rf.py#L364).
It seeds both the global torch RNG used by the stochastic sampler and the
pipeline generator. This is an explicit compatibility adaptation with focused
CPU scheduler tests; actual checkpoint loading and GPU output remain qualification
requirements. Do not replace the pipeline or scheduler based only on a class
name or lower step count.

Focused source checks, without downloading models or using a GPU:

```sh
timeout 30 python3 -B tests/test_generate.py
timeout 30 python3 -B tests/test_generate_runtime.py
timeout 60 python3 -B tests/test_publish.py
```

The runtime check needs the pinned Python packages and PyTorch 2.8; a CPU-only
PyTorch build suffices for its scheduler and synthetic MP4 round-trip. It is not
a model inference test. The publisher's existing bounded CPU inspection also
checks the command, dependencies, notices and FFmpeg executable. No new CI build
trigger or automatic publication is introduced.

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
