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

Do not remove or relabel upstream proprietary notices. A new base, package or
model version requires reviewing its accompanying terms again before publication.
