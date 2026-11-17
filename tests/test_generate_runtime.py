"""Real pinned scheduler math and synthetic MP4 codec; no model weights or GPU."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

import imageio.v2 as imageio
import numpy as np
import torch
from diffusers import FlowMatchEulerDiscreteScheduler


ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("generate", ROOT / "examples/generate.py")
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)


class GenerationRuntime(unittest.TestCase):
    def scheduler(self):
        return generate.distilled_scheduler(FlowMatchEulerDiscreteScheduler(
            shift=3.0, use_dynamic_shifting=True, shift_terminal=0.1,
        ))

    def test_fixed_checkpoint_schedule_replaces_pipeline_uniform_sigmas(self):
        scheduler = self.scheduler()
        scheduler.set_timesteps(8, device="cpu", sigmas=np.linspace(1, 1 / 8, 8), mu=1.5)
        torch.testing.assert_close(scheduler.sigmas, torch.tensor([*generate.LTX_SIGMAS, 0.0]))
        torch.testing.assert_close(scheduler.timesteps, torch.tensor(generate.LTX_SIGMAS) * 1000)
        self.assertTrue(scheduler.config.stochastic_sampling)
        for kwargs in ({"num_inference_steps": 4}, {"sigmas": [1.0, 0.5]}, {"timesteps": [1000, 500]}):
            with self.assertRaises(ValueError):
                scheduler.set_timesteps(**kwargs)

    def test_stochastic_steps_match_native_positive_prediction_formula(self):
        scheduler = self.scheduler()
        scheduler.set_timesteps(8, sigmas=np.linspace(1, 1 / 8, 8))
        sample = torch.tensor([[0.4, -0.2], [0.6, -0.8]])
        prediction = torch.tensor([[0.1, 0.3], [-0.5, 0.7]])
        # Upstream rf.py: x0 = sample - sigma * prediction;
        # next = (1 - next_sigma) * x0 + next_sigma * fresh_noise.
        for index, timestep in enumerate(scheduler.timesteps):
            sigma, next_sigma = scheduler.sigmas[index:index + 2]
            torch.manual_seed(100 + index)
            noise = torch.randn_like(sample)
            expected = (1 - next_sigma) * (sample - sigma * prediction) + next_sigma * noise
            torch.manual_seed(100 + index)
            actual = scheduler.step(prediction, timestep, sample).prev_sample
            torch.testing.assert_close(actual, expected)
            sample = actual

    def test_pinned_pipeline_classes_and_mp4_roundtrip(self):
        from diffusers import LTXImageToVideoPipeline, LTXPipeline, ZImagePipeline
        from diffusers.utils import export_to_video

        self.assertTrue(callable(ZImagePipeline.from_pretrained))
        self.assertTrue(callable(LTXPipeline.from_single_file))
        self.assertTrue(callable(LTXImageToVideoPipeline.from_single_file))
        frames = [np.full((32, 48, 3), value, dtype=np.uint8) for value in (0, 80, 160, 240)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.mp4"
            export_to_video(frames, str(path), fps=24)
            reader = imageio.get_reader(path)
            try:
                self.assertEqual(reader.count_frames(), 4)
                self.assertEqual(reader.get_data(0).shape, (32, 48, 3))
                self.assertEqual(reader.get_meta_data()["fps"], 24)
            finally:
                reader.close()


if __name__ == "__main__":
    unittest.main()
