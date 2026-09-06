"""Small portable examples, not a fluxyard workflow or mandatory result format."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import time


MODEL = "distilbert/distilgpt2"
REVISION = "2290a62682d06624634c1f46a6ad5be0f47f38aa"
IMAGE_MODEL = "google/ddpm-cifar10-32"
IMAGE_REVISION = "267b167dc01f0e4e61923ea244e8b988f84deb80"


def training(args, torch):
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(23)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, revision=REVISION, use_safetensors=True, trust_remote_code=False
    ).to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
    corpus = [(args.data / name).read_bytes() for name in ("train.txt", "eval.txt")]
    data_hash = hashlib.sha256(b"\x00".join(corpus)).hexdigest()
    tokens = [
        tokenizer(text.decode("utf-8"), return_tensors="pt", truncation=True, max_length=64)
        .input_ids.to(args.device)
        for text in corpus
    ]
    if min(t.shape[1] for t in tokens) < 2:
        raise ValueError("train.txt and eval.txt must each contain at least two tokens")
    step = 0
    if args.resume:
        # This example never enables arbitrary pickle execution for a checkpoint.
        saved = torch.load(args.resume, map_location="cpu", weights_only=True)
        if saved["model_revision"] != REVISION or saved["data_sha256"] != data_hash:
            raise ValueError("checkpoint model revision or input data differs")
        model.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        torch.set_rng_state(saved["torch_rng"])
        if args.device == "cuda" and saved["cuda_rng"]:
            torch.cuda.set_rng_state_all(saved["cuda_rng"])
        step = saved["step"]
    initial_step = step
    model.train()
    for _ in range(args.steps):
        optimizer.zero_grad(set_to_none=True)
        loss = model(tokens[0], labels=tokens[0]).loss
        loss.backward()
        optimizer.step()
        step += 1
    model.eval()
    with torch.no_grad():
        eval_loss = model(tokens[1], labels=tokens[1]).loss.item()
    if not math.isfinite(eval_loss):
        raise ValueError("evaluation was not finite")
    checkpoint = args.output / "checkpoint.pt"
    temporary = checkpoint.with_suffix(".partial")
    torch.save(
        {
            "model_id": MODEL,
            "model_revision": REVISION,
            "data_sha256": data_hash,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "torch_rng": torch.get_rng_state(),
            "cuda_rng": torch.cuda.get_rng_state_all() if args.device == "cuda" else [],
            "step": step,
        },
        temporary,
    )
    temporary.replace(checkpoint)
    return {
        "model": MODEL, "revision": REVISION, "initial_step": initial_step,
        "step": step, "eval_loss": eval_loss, "data_sha256": data_hash,
        "checkpoint_sha256": file_sha256(checkpoint),
    }


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inference(args, torch):
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, revision=REVISION, use_safetensors=True, trust_remote_code=False
    ).to(args.device).eval()
    inputs = tokenizer(
        args.input.read_text(), return_tensors="pt", truncation=True, max_length=128
    ).to(args.device)
    if inputs.input_ids.shape[1] == 0:
        raise ValueError("prompt must not be empty")
    with torch.inference_mode():
        output = model.generate(
            **inputs, max_new_tokens=32, do_sample=False, pad_token_id=tokenizer.eos_token_id
        )
    return {
        "model": MODEL, "revision": REVISION,
        "input_sha256": file_sha256(args.input),
        "generated_tokens": output.shape[1] - inputs.input_ids.shape[1],
        "text": tokenizer.decode(output[0], skip_special_tokens=True),
    }


def image_generation(args, torch):
    from diffusers import DDPMPipeline, DDPMScheduler, UNet2DModel

    settings = json.loads(args.input.read_text())
    if set(settings) != {"seed", "steps"}:
        raise ValueError("image input must contain exactly seed and steps")
    seed, steps = settings["seed"], settings["steps"]
    if type(seed) is not int or not 0 <= seed < 2**32 or type(steps) is not int or not 1 <= steps <= 1000:
        raise ValueError("seed must be a uint32 and steps must be in 1..1000")
    # This immutable upstream repository uses the original flat layout. Load
    # maintained library components explicitly, never its modeling_ddpm.py.
    unet = UNet2DModel.from_pretrained(
        IMAGE_MODEL, revision=IMAGE_REVISION, use_safetensors=True, low_cpu_mem_usage=False
    )
    scheduler = DDPMScheduler.from_pretrained(IMAGE_MODEL, revision=IMAGE_REVISION)
    pipeline = DDPMPipeline(unet=unet, scheduler=scheduler).to(args.device)
    image = pipeline(
        batch_size=1, num_inference_steps=steps,
        generator=torch.Generator(device=args.device).manual_seed(seed),
    ).images[0]
    destination = args.output / "image.png"
    image.save(destination)
    return {
        "model": IMAGE_MODEL, "revision": IMAGE_REVISION,
        "input_sha256": file_sha256(args.input), "image_sha256": file_sha256(destination),
        "width": image.width, "height": image.height, "seed": seed, "steps": steps,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="use_case", required=True)
    for name in ("training", "image_generation", "inference"):
        command = commands.add_parser(name)
        command.add_argument("--device", choices=("cpu", "cuda"), required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "training":
            command.add_argument("--data", type=Path, required=True)
            command.add_argument("--steps", type=int, default=2, help="additional steps, including after resume")
            command.add_argument("--resume", type=Path)
        else:
            command.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    if args.use_case == "training" and not 1 <= args.steps <= 10000:
        parser.error("--steps must be in 1..10000")
    import torch

    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA was requested but is unavailable; no CPU fallback")
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.use_case == "training":
        result = training(args, torch)
    elif args.use_case == "inference":
        result = inference(args, torch)
    else:
        result = image_generation(args, torch)
    result.update(device=args.device, elapsed_seconds=round(time.monotonic() - started, 3))
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
