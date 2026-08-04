import json
import tempfile
import unittest
from pathlib import Path

from pipeline.score_single_channel import (
    LocalScoreError,
    build_result,
    load_payload,
    validate_input_path,
    validate_payload,
)


def sample_payload() -> dict:
    videos = []
    for index, day in enumerate((1, 8, 15, 22, 29, 36), start=1):
        videos.append(
            {
                "video_id": f"video-{index}",
                "published_at": f"2026-01-{day:02d}T00:00:00Z"
                if day <= 29
                else "2026-02-05T00:00:00Z",
                "view_count": index * 100,
                "like_count": index * 10,
                "comment_count": index,
                "duration": "PT1M",
            }
        )
    return {
        "fetched_at": "2026-05-01T00:00:00Z",
        "channels": [
            {
                "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "published_at": "2020-01-01T00:00:00Z",
                "subscriber_count": 1000,
                "view_count_total": 10000,
                "videos": videos,
            }
        ],
    }


class ScoreSingleChannelTests(unittest.TestCase):
    def test_build_result_has_required_local_metadata(self):
        result = build_result(validate_payload(sample_payload()), "channel.json")
        self.assertEqual(result["method"], "heuristic_local_test")
        self.assertIs(result["production_comparable"], False)
        self.assertGreaterEqual(result["potential_p"], 0)
        self.assertLessEqual(result["potential_p"], 100)
        self.assertIn("publish_cadence_30d", result["features"])

    def test_rejects_multiple_channels(self):
        payload = sample_payload()
        payload["channels"].append(dict(payload["channels"][0]))
        with self.assertRaisesRegex(LocalScoreError, "exactly one channel"):
            validate_payload(payload)

    def test_rejects_input_outside_output_directory(self):
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            output_dir = root / "local_test_output"
            output_dir.mkdir()
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(LocalScoreError, "local_test_output"):
                validate_input_path(outside, output_dir)

    def test_loads_one_valid_json_inside_output_directory(self):
        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "local_test_output"
            output_dir.mkdir()
            input_path = output_dir / "channel.json"
            input_path.write_text(json.dumps(sample_payload()), encoding="utf-8")
            resolved = validate_input_path(input_path, output_dir)
            loaded = load_payload(resolved)
            self.assertEqual(len(loaded["channels"]), 1)


if __name__ == "__main__":
    unittest.main()
