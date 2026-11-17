#!/usr/bin/env python3
"""Generate a prompted PNG or short MP4 inside an allocated GPU workspace."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
LTX_SIGMAS = (1.0, 0.9937, 0.9875, 0.9812, 0.975, 0.9094, 0.725, 0.4219)
LTX_CONFIG_FILES = (
    "model_index.json", "scheduler/scheduler_config.json", "transformer/config.json",
    "vae/config.json", "text_encoder/config.json", "text_encoder/model.safetensors.index.json",
    *(f"text_encoder/model-{i:05}-of-00004.safetensors" for i in range(1, 5)),
    "tokenizer/added_tokens.json", "tokenizer/special_tokens_map.json",
    "tokenizer/spiece.model", "tokenizer/tokenizer_config.json",
    "README.md", "ltx-video-2b-v0.9.5.license.txt",
)
IMAGE_FILES = (
    "model_index.json", "scheduler/*.json", "text_encoder/*.json",
    "text_encoder/*.safetensors", "tokenizer/*.json", "tokenizer/*.txt",
    "transformer/*.json", "transformer/*.safetensors", "vae/*.json",
    "vae/*.safetensors", "README.md", "LICENSE*",
)


def model_pins():
    models = json.loads((ROOT / "models.lock.json").read_text())["models"]
    return {model["generation_role"]: model for model in models if "generation_role" in model}


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(mode, offline=False):
    # Never use a cached personal token or execute downloaded model Python.
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import hf_hub_download, snapshot_download

    pins = model_pins()
    common = dict(token=False, local_files_only=offline)
    if mode == "image":
        model = pins["image"]
        return {"model": snapshot_download(
            repo_id=model["model_id"], revision=model["revision"],
            allow_patterns=list(IMAGE_FILES), max_workers=2, **common,
        )}
    config, checkpoint = pins["video_config"], pins["video"]
    config_path = snapshot_download(
        repo_id=config["model_id"], revision=config["revision"],
        allow_patterns=list(LTX_CONFIG_FILES), max_workers=2, **common,
    )
    checkpoint_path = hf_hub_download(
        repo_id=checkpoint["model_id"], revision=checkpoint["revision"],
        filename=checkpoint["filename"], **common,
    )
    hf_hub_download(
        repo_id=checkpoint["model_id"], revision=checkpoint["revision"],
        filename=checkpoint["license_filename"], **common,
    )
    if file_sha256(Path(checkpoint_path)) != checkpoint["sha256"]:
        raise ValueError("the downloaded video checkpoint does not match its pinned SHA256")
    return {"model": checkpoint_path, "config": config_path}


def distilled_scheduler(scheduler):
    from diffusers import FlowMatchEulerDiscreteScheduler

    class DistilledLTXScheduler(FlowMatchEulerDiscreteScheduler):
        """Bind the checkpoint's eight sigmas without rewriting pipeline code.

        Diffusers 0.36's plain LTX pipelines supply uniform sigmas themselves;
        passing custom timesteps as well is rejected. The checkpoint requires
        the fixed distilled schedule and stochastic sampling instead.
        """

        def set_timesteps(self, num_inference_steps=None, device=None, sigmas=None,
                          mu=None, timesteps=None):
            if timesteps is not None or num_inference_steps not in (None, 8):
                raise ValueError("the distilled LTX model requires its fixed eight-step schedule")
            if sigmas is not None and len(sigmas) != 8:
                raise ValueError("the distilled LTX model requires eight sigmas")
            return super().set_timesteps(sigmas=list(LTX_SIGMAS), device=device)

    return DistilledLTXScheduler.from_config(
        scheduler.config, shift=1.0, use_dynamic_shifting=False, shift_terminal=None,
        stochastic_sampling=True, use_karras_sigmas=False, use_exponential_sigmas=False,
        use_beta_sigmas=False, invert_sigmas=False,
    )


def gpu(torch):
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("generation requires exactly one visible CUDA GPU; no CPU fallback")
    properties = torch.cuda.get_device_properties(0)
    # CUDA can report slightly less usable memory than the board's 24-GiB label.
    if properties.total_memory < 23 * 1024**3 or not torch.cuda.is_bf16_supported():
        raise ValueError("the demo preset requires a 24-GiB-class GPU with bfloat16 support")
    return {"type": "cuda", "index": 0, "name": properties.name,
            "total_memory_bytes": properties.total_memory}


def build_pipeline(mode, paths, image_to_video, torch):
    from diffusers import LTXImageToVideoPipeline, LTXPipeline, ZImagePipeline

    options = dict(torch_dtype=torch.bfloat16, local_files_only=True)
    if mode == "image":
        pipeline = ZImagePipeline.from_pretrained(paths["model"], use_safetensors=True, **options)
    else:
        kind = LTXImageToVideoPipeline if image_to_video else LTXPipeline
        pipeline = kind.from_single_file(paths["model"], config=paths["config"], **options)
        pipeline.scheduler = distilled_scheduler(pipeline.scheduler)
        pipeline.vae.enable_tiling()
    pipeline.enable_model_cpu_offload(gpu_id=0)
    return pipeline


def settings(args):
    if args.mode == "image":
        return dict(width=1024, height=1024, num_inference_steps=9, guidance_scale=0.0)
    return dict(width=768, height=512, num_frames=args.frames, frame_rate=24,
                num_inference_steps=8, guidance_scale=1.0, decode_timestep=0.05,
                decode_noise_scale=0.025)


def generate(args):
    # The directory is the unit of output ownership. Never overwrite a prior run,
    # even when it was interrupted before writing a complete report.
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    started = time.monotonic()
    import torch

    device = gpu(torch)
    download_started = time.monotonic()
    paths = download(args.mode, args.offline)
    downloaded = time.monotonic()
    pipeline = build_pipeline(args.mode, paths, args.image is not None, torch)
    loaded = time.monotonic()
    call = settings(args)
    input_hash = None
    if args.image is not None:
        from PIL import Image, ImageOps

        input_hash = file_sha256(args.image)
        with Image.open(args.image) as image:
            call["image"] = ImageOps.fit(
                image.convert("RGB"), (call["width"], call["height"]),
                method=Image.Resampling.LANCZOS,
            )
    # The stochastic scheduler uses the global RNG in addition to the pipeline's
    # explicit generator. Record the seed; do not promise cross-device bit parity.
    torch.manual_seed(args.seed)
    generator = torch.Generator(device="cuda").manual_seed(args.seed)
    torch.cuda.synchronize()
    prepared = time.monotonic()
    torch.cuda.reset_peak_memory_stats()
    with torch.inference_mode():
        result = pipeline(prompt=args.prompt, generator=generator, **call)
    torch.cuda.synchronize()
    inferred = time.monotonic()
    artifact = args.output / ("image.png" if args.mode == "image" else "video.mp4")
    if args.mode == "image":
        result.images[0].save(artifact)
    else:
        from diffusers.utils import export_to_video

        export_to_video(result.frames[0], str(artifact), fps=24)
    pins = model_pins()
    report = {
        "schema": 1, "mode": args.mode, "prompt": args.prompt, "seed": args.seed,
        "models": [pins[args.mode]] + ([pins["video_config"]] if args.mode == "video" else []),
        "runner_sha256": file_sha256(Path(__file__)), "device": device,
        "settings": settings(args), "input_image_sha256": input_hash,
        "video_sigmas": list(LTX_SIGMAS) if args.mode == "video" else None,
        "seconds": {"prepare": round(prepared - started, 3),
                    "cache_or_download": round(downloaded - download_started, 3),
                    "model_load": round(loaded - downloaded, 3),
                    "generate": round(inferred - prepared, 3),
                    "save": round(time.monotonic() - inferred, 3),
                    "total": round(time.monotonic() - started, 3)},
        "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(),
        "artifact": {"filename": artifact.name, "sha256": file_sha256(artifact),
                     "bytes": artifact.stat().st_size},
        "timing_note": "Process timings only; these are not rental billing or final session cost.",
    }
    # result.json is a completion marker; a failed run may retain an incomplete
    # artifact but never a success report. Use a new directory for a retry.
    temporary = args.output / "result.json.partial"
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(args.output / "result.json")
    print(json.dumps(report))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    prefetch = commands.add_parser("download", help="cache the pinned weights before the demo")
    prefetch.add_argument("--mode", dest="download_mode", choices=("image", "video", "all"), required=True)
    for mode in ("image", "video"):
        command = commands.add_parser(mode)
        command.add_argument("--prompt", required=True, help="literal text prompt (quote it in your shell)")
        command.add_argument("--output", type=Path, required=True, help="a new output directory")
        command.add_argument("--seed", type=int, default=23)
        command.add_argument("--offline", action="store_true", help="require previously cached pinned models")
        command.set_defaults(image=None)
        if mode == "video":
            command.add_argument("--image", type=Path, help="optional local source image; center-cropped to 768x512")
            command.add_argument("--frames", type=int, choices=(33, 65, 97), default=65)
    args = parser.parse_args(argv)
    if args.mode != "download":
        if not args.prompt.strip() or len(args.prompt) > 4000:
            parser.error("--prompt must contain 1..4000 characters with non-whitespace text")
        if not 0 <= args.seed < 2**32:
            parser.error("--seed must be a uint32")
        if args.output.exists() or args.output.is_symlink():
            parser.error("--output must name a new directory; existing runs are never overwritten")
        if args.image is not None and not args.image.is_file():
            parser.error("--image must name an existing local image file")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.mode == "download":
            modes = ("image", "video") if args.download_mode == "all" else (args.download_mode,)
            for mode in modes:
                print(f"Caching pinned {mode} models...", file=sys.stderr)
                download(mode)
                print(f"Pinned {mode} models cached.", file=sys.stderr)
        else:
            generate(args)
    except (ValueError, OSError, RuntimeError, ImportError) as error:
        print(f"fluxyard-generate: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
