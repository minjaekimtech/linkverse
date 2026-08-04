import json
import tempfile
import unittest
from pathlib import Path

from pipeline.resonance_single_channel import (
    LocalResonanceError,
    build_proxy_vector,
    build_result,
    load_config,
    validate_input_path,
    validate_payload,
)


DIMENSION_KEYS = [
    "perspective_ratio",
    "stabilization_demand",
    "motion_complexity",
    "scene_extremity",
    "gear_visibility",
    "narrative_pace",
    "scene_diversity",
    "slow_motion_demand",
]


def sample_payload(video_count: int = 10) -> dict:
    videos = []
    for index in range(video_count):
        videos.append(
            {
                "video_id": f"video-{index}",
                "title": "POV travel action camera highlight",
                "description": "Running mountain vlog with slow motion scenes",
                "tags": ["gimbal", "adventure"],
                "published_at": f"2026-01-{index + 1:02d}T00:00:00Z",
            }
        )
    return {"channels": [{"channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw", "videos": videos}]}


class ResonanceSingleChannelTests(unittest.TestCase):
    def test_proxy_vector_is_eight_bounded_values(self):
        channel = validate_payload(sample_payload())["channels"][0]
        vector, matches = build_proxy_vector(channel["videos"][:8], DIMENSION_KEYS)
        self.assertEqual(len(vector), 8)
        self.assertTrue(all(0 <= value <= 1 for value in vector))
        self.assertIn("pov", matches["perspective_ratio"])
        self.assertGreater(vector[0], 0)

    def test_result_has_required_metadata_and_all_products(self):
        products = [
            {"id": "camera-a", "name": "Camera A", "vector": [0.5] * 8},
            {"id": "camera-b", "name": "Camera B", "vector": [1.0] * 8},
        ]
        result = build_result(sample_payload(), "channel_test.json", DIMENSION_KEYS, products)
        self.assertEqual(result["method"], "metadata_proxy_local_test")
        self.assertIs(result["production_comparable"], False)
        self.assertIsNone(result["vision_backend"])
        self.assertIs(result["thumbnail_images_analyzed"], False)
        self.assertEqual(result["recent_video_count"], 8)
        self.assertEqual(set(result["products"]), {"camera-a", "camera-b"})
        self.assertEqual(
            len(result["products"]["camera-a"]["dimension_contributions"]), 8
        )

    def test_rejects_multiple_channels(self):
        payload = sample_payload()
        payload["channels"].append(dict(payload["channels"][0]))
        with self.assertRaisesRegex(LocalResonanceError, "exactly one channel"):
            validate_payload(payload)

    def test_rejects_non_channel_filename_and_outside_path(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            output_dir = root / "local_test_output"
            output_dir.mkdir()
            wrong_name = output_dir / "other.json"
            wrong_name.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(LocalResonanceError, r"channel_\*\.json"):
                validate_input_path(wrong_name, output_dir)

            outside = root / "channel_outside.json"
            outside.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(LocalResonanceError, "local_test_output"):
                validate_input_path(outside, output_dir)

    def test_config_validation_uses_eight_dimensions_and_product_vectors(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            dimensions_path = root / "dimensions.yaml"
            products_path = root / "products.yaml"
            dimensions_path.write_text(
                "dimensions:\n"
                + "".join(
                    f"  - key: {key}\n    index: {index}\n"
                    for index, key in enumerate(DIMENSION_KEYS)
                ),
                encoding="utf-8",
            )
            products_path.write_text(
                "products:\n  - id: camera\n    vector: [1, 1, 1, 1, 1, 1, 1, 1]\n",
                encoding="utf-8",
            )
            keys, products = load_config(dimensions_path, products_path)
            self.assertEqual(keys, DIMENSION_KEYS)
            self.assertEqual(len(products), 1)


if __name__ == "__main__":
    unittest.main()
