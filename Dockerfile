# Official PyTorch 2.8.0 / CUDA 12.8 / cuDNN 9, Linux amd64 manifest.
FROM docker.io/pytorch/pytorch@sha256:417bd75df6365104c283ea4c1651fb3530d9eb5a4c2fafa51943cff2a94e6385

LABEL org.opencontainers.image.source="https://github.com/Fluxyard-Inc/images"

USER root
# The immutable, signed Ubuntu snapshot also locks transitive apt inputs.
RUN rm -f /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources && \
    printf '%s\n' \
      'deb https://snapshot.ubuntu.com/ubuntu/20260901T000000Z jammy main universe' \
      'deb https://snapshot.ubuntu.com/ubuntu/20260901T000000Z jammy-updates main universe' \
      'deb https://snapshot.ubuntu.com/ubuntu/20260901T000000Z jammy-security main universe' \
      > /etc/apt/sources.list && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      openssh-sftp-server tmux curl coreutils && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 65532 workspace && \
    useradd --uid 65532 --gid 65532 --no-create-home --home-dir /workspace --shell /bin/bash workspace

COPY requirements.lock /opt/fluxyard/requirements.lock
RUN python -m pip install --no-cache-dir --disable-pip-version-check --no-deps \
      --require-hashes -r /opt/fluxyard/requirements.lock && python -m pip check

ENV HOME=/workspace \
    XDG_CACHE_HOME=/workspace/.cache \
    XDG_CONFIG_HOME=/workspace/.config \
    TMPDIR=/workspace/tmp \
    PIP_CACHE_DIR=/workspace/.cache/pip \
    HF_HOME=/workspace/.cache/huggingface \
    TORCH_HOME=/workspace/.cache/torch \
    TRITON_CACHE_DIR=/workspace/.cache/triton \
    HF_HUB_DISABLE_XET=1 \
    HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

COPY examples /opt/fluxyard/examples

# Runtime mounts empty quota scratch here with volume-nocopy. Bake code under
# /opt/fluxyard or transfer it with SFTP; never put required image files here.
WORKDIR /workspace
USER 65532:65532
ENTRYPOINT []
CMD ["/bin/bash"]
