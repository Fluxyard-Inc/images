"""An independently baked custom CUDA project; no Runtime-specific library."""
import argparse
import json
from pathlib import Path
import torch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
args = parser.parse_args()
if args.device == "cuda" and not torch.cuda.is_available():
    parser.error("CUDA was requested but is unavailable")
result = torch.arange(8, device=args.device).square().sum().item()
assert result == 140
Path("/workspace/custom-result.json").write_text(json.dumps({"device": args.device, "sum_of_squares": result}) + "\n")
