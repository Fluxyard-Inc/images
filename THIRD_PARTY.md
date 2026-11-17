# Third-party software in fluxyard images

These images contain third-party software under its own terms. This document is
an inventory guide, not a replacement license, additional grant or statement of
NVIDIA or other upstream endorsement. No project-wide source license is granted.

- The immutable PyTorch base is identified in `Dockerfile`. PyTorch and bundled
  Python distributions retain their LICENSE/NOTICE files in their installed
  distribution metadata under `/opt/conda/lib/python3.11/site-packages` and in
  the upstream conda package metadata. Preserve those files when deriving images.
- CUDA and NVIDIA libraries remain subject to their accompanying terms. The
  current base contains `nvidia-cudnn-cu12` version `9.10.2.21`; its accompanying
  license is `nvidia_cudnn_cu12-9.10.2.21.dist-info/licenses/License.txt` beneath
  that Python directory. Consult the terms accompanying the actual package,
  not another version's web documentation or a model's license label.
- Added Python package versions and wheel hashes are in `requirements.lock`.
  Transformers and Diffusers retain their Apache license and any accompanying
  notices in their installed distribution metadata. Other packages retain their
  respective terms; the publisher checks notice presence, not legal compliance.
- Ubuntu package copyright/license information, including the installed
  OpenSSH SFTP server, tmux, curl and coreutils, remains in `/usr/share/doc`.
- Models are not included in the image. The examples download the immutable
  revisions in `models.lock.json`; their linked model cards describe separate
  terms and limitations. Model permissions do not license the rest of the image.
- The generation command adds Accelerate, psutil, SentencePiece, protobuf,
  ImageIO and imageio-ffmpeg at the versions/hashes in `requirements.lock`.
  Preserve their installed license notices. SentencePiece's wheel omits standalone
  license files; its upstream release license and bundled third-party notices
  are copied into `/opt/fluxyard/licenses/sentencepiece`, with provenance in
  [licenses/sentencepiece/README.md](licenses/sentencepiece/README.md).
  The imageio-ffmpeg Linux wheel
  includes a compiled FFmpeg executable and its accompanying license material;
  that executable has its own build configuration and terms, separate from
  ImageIO's Python wrapper. Do not strip it or its notices from derived images.
- Z-Image-Turbo declares Apache-2.0 in its pinned model card. LTX 0.9.6 distilled
  2B uses the separately linked **LTX-Video Open Weights License 0.X**, with use
  and redistribution conditions and an additional commercial-license provision
  for organizations at or above its stated USD 10 million annual revenue threshold.
  The pinned 0.9.5 configuration/text-encoder repository also includes Open RAIL-M
  terms. These are not Apache grants. Review the exact accompanying terms before
  deploying or redistributing the models; this inventory is not a determination
  that a particular use is authorized. The downloader retains their license files
  in the workspace cache and records the exact model references in each report.

Do not remove or relabel upstream proprietary notices. A new base, package or
model version requires reviewing its accompanying terms again before publication.
