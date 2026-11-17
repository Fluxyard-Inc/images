"""CLI/download contract checks: no models, torch installation or GPU required."""

import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("generate", ROOT / "examples/generate.py")
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)


class GenerateCLI(unittest.TestCase):
    def test_help_and_invalid_input_do_not_import_models(self):
        for args, status in ((["--help"], 0), (["image", "--help"], 0),
                             (["image", "--prompt", " ", "--output", "/unused"], 2),
                             (["video", "--prompt", "scene", "--frames", "64", "--output", "/unused"], 2)):
            result = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "examples/generate.py"), *args],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, status, result.stderr.decode())
            self.assertNotIn(b"ModuleNotFoundError", result.stderr)

    def test_prompt_is_literal_and_presets_are_bounded(self):
        prompt = "A robot holding 'hello'; $(touch unexpected); `echo nope`"
        args = generate.parse_args(["video", "--prompt", prompt, "--output", "/unused", "--seed", "42"])
        self.assertEqual(args.prompt, prompt)
        self.assertEqual(args.frames, 65)
        self.assertEqual(generate.settings(args)["num_inference_steps"], 8)
        self.assertEqual(generate.settings(args)["frame_rate"], 24)

    def test_existing_output_and_racing_creation_preserve_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run"
            args = generate.parse_args(["image", "--prompt", "sunset", "--output", str(path)])
            path.mkdir()
            artifact = path / "image.png"
            artifact.write_bytes(b"previous result")
            with self.assertRaises(FileExistsError):
                generate.generate(args)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                generate.parse_args(["image", "--prompt", "sunset", "--output", str(path)])
            self.assertEqual(artifact.read_bytes(), b"previous result")

    def test_bad_seed_and_missing_image_are_rejected_before_work(self):
        for extra in (["--seed", "-1"], ["--seed", str(2**32)], ["--image", "/missing-source.png"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                generate.parse_args(["video", "--prompt", "sunset", "--output", "/unused", *extra])

    def test_image_download_uses_pinned_anonymous_data_only(self):
        hub = SimpleNamespace(snapshot_download=Mock(return_value="/cache/image"), hf_hub_download=Mock())
        with patch.dict(sys.modules, huggingface_hub=hub):
            result = generate.download("image", offline=True)
        self.assertEqual(result, {"model": "/cache/image"})
        request = hub.snapshot_download.call_args.kwargs
        self.assertEqual(request["revision"], generate.model_pins()["image"]["revision"])
        self.assertFalse(request["token"])
        self.assertTrue(request["local_files_only"])
        self.assertNotIn("*.py", request["allow_patterns"])
        self.assertNotIn("*.bin", request["allow_patterns"])
        hub.hf_hub_download.assert_not_called()

    def test_video_download_uses_separate_pinned_config_and_checks_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.safetensors"
            path.write_bytes(b"inert checkpoint fixture")
            hub = SimpleNamespace(snapshot_download=Mock(return_value="/cache/config"),
                                  hf_hub_download=Mock(return_value=str(path)))
            with patch.dict(sys.modules, huggingface_hub=hub), self.assertRaisesRegex(ValueError, "SHA256"):
                generate.download("video")
            pins = generate.model_pins()
            pins["video"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.dict(sys.modules, huggingface_hub=hub), patch.object(generate, "model_pins", return_value=pins):
                result = generate.download("video", offline=True)
            self.assertEqual(result, {"model": str(path), "config": "/cache/config"})
            config_request = hub.snapshot_download.call_args.kwargs
            self.assertEqual(config_request["revision"], pins["video_config"]["revision"])
            self.assertFalse(config_request["token"])
            self.assertTrue(config_request["local_files_only"])
            self.assertNotIn("transformer/diffusion_pytorch_model.safetensors", config_request["allow_patterns"])
            self.assertNotIn("vae/diffusion_pytorch_model.safetensors", config_request["allow_patterns"])
            for call in hub.hf_hub_download.call_args_list[-2:]:
                self.assertEqual(call.kwargs["revision"], pins["video"]["revision"])
                self.assertFalse(call.kwargs["token"])
                self.assertTrue(call.kwargs["local_files_only"])

    def test_gpu_rejects_cpu_multiple_devices_and_small_cards(self):
        cuda = Mock()
        cuda.is_available.return_value = False
        torch = SimpleNamespace(cuda=cuda)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            generate.gpu(torch)
        cuda.is_available.return_value = True
        cuda.device_count.return_value = 2
        with self.assertRaisesRegex(ValueError, "exactly one"):
            generate.gpu(torch)
        cuda.device_count.return_value = 1
        cuda.get_device_properties.return_value = SimpleNamespace(total_memory=8 * 1024**3)
        with self.assertRaisesRegex(ValueError, "24-GiB"):
            generate.gpu(torch)
        cuda.get_device_properties.return_value = SimpleNamespace(total_memory=24 * 1024**3, name="fixture GPU")
        cuda.is_bf16_supported.return_value = True
        self.assertEqual(generate.gpu(torch)["type"], "cuda")


if __name__ == "__main__":
    unittest.main()
