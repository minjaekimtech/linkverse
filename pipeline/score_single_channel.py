"""Compute an isolated heuristic Potential P score for one local collection.

Only JSON files directly inside ``local_test_output`` are accepted. This
module reuses pure feature/scoring functions but never calls either pipeline
stage's ``run()`` function, so production artifacts are not read or written.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.features import (
    _iso8601_duration_to_seconds,
    _parse_iso,
    apply_season_adjustment,
    compute_channel_features,
    compute_relative_velocity,
    compute_season_coefs,
)
from pipeline.score import heuristic_potential_score


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "local_test_output"
REQUIRED_CHANNEL_FIELDS = {
    "channel_id",
    "published_at",
    "subscriber_count",
    "view_count_total",
    "videos",
}
REQUIRED_VIDEO_FIELDS = {
    "video_id",
    "published_at",
    "view_count",
    "like_count",
    "comment_count",
    "duration",
}


class LocalScoreError(ValueError):
    """A validation error safe to display without source-record contents."""


def validate_input_path(path: Path, output_dir: Path = OUTPUT_DIR) -> Path:
    """Require one existing JSON file directly inside the isolated folder."""
    resolved_output = output_dir.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_output:
        raise LocalScoreError("input must be directly inside local_test_output")
    if resolved_path.suffix.lower() != ".json":
        raise LocalScoreError("input must be a JSON file")
    if not resolved_path.is_file():
        raise LocalScoreError("input JSON file does not exist")
    return resolved_path


def _require_fields(record: dict, required: set[str], record_type: str) -> None:
    missing = sorted(required - record.keys())
    if missing:
        raise LocalScoreError(
            f"{record_type} is missing required fields: {', '.join(missing)}"
        )


def validate_payload(payload: object) -> dict:
    """Validate the minimum shape and types needed by the reused functions."""
    if not isinstance(payload, dict):
        raise LocalScoreError("input JSON root must be an object")

    fetched_at = payload.get("fetched_at")
    if not isinstance(fetched_at, str):
        raise LocalScoreError("fetched_at must be an ISO-8601 string")
    try:
        _parse_iso(fetched_at)
    except (TypeError, ValueError):
        raise LocalScoreError("fetched_at must be a valid ISO-8601 timestamp") from None

    channels = payload.get("channels")
    if not isinstance(channels, list) or len(channels) != 1:
        raise LocalScoreError("input JSON must contain exactly one channel")
    channel = channels[0]
    if not isinstance(channel, dict):
        raise LocalScoreError("channel must be an object")
    _require_fields(channel, REQUIRED_CHANNEL_FIELDS, "channel")

    channel_id = channel.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id.startswith("UC"):
        raise LocalScoreError("channel_id must be a YouTube channel ID")
    if channel.get("published_at") is not None:
        try:
            _parse_iso(channel["published_at"])
        except (TypeError, ValueError):
            raise LocalScoreError("channel published_at is invalid") from None

    for field in ("subscriber_count", "view_count_total"):
        value = channel.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise LocalScoreError(f"channel {field} must be a non-negative integer or null")

    videos = channel.get("videos")
    if not isinstance(videos, list) or not videos:
        raise LocalScoreError("channel must contain at least one video")
    for index, video in enumerate(videos):
        if not isinstance(video, dict):
            raise LocalScoreError(f"video at index {index} must be an object")
        _require_fields(video, REQUIRED_VIDEO_FIELDS, f"video at index {index}")
        try:
            _parse_iso(video["published_at"])
        except (TypeError, ValueError, AttributeError):
            raise LocalScoreError(f"video at index {index} has invalid published_at") from None
        for field in ("view_count", "like_count", "comment_count"):
            value = video.get(field)
            if field != "view_count" and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LocalScoreError(
                    f"video at index {index} has invalid {field}"
                )

    return payload


def load_payload(input_path: Path) -> dict:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise LocalScoreError("input is not a readable UTF-8 JSON file") from None
    return validate_payload(payload)


def build_result(payload: dict, source_name: str) -> dict:
    """Compute derived features and heuristic P entirely in memory."""
    working = copy.deepcopy(payload)
    fetched_at = _parse_iso(working["fetched_at"])
    channel = working["channels"][0]

    for video in channel["videos"]:
        video["duration_seconds"] = _iso8601_duration_to_seconds(video.get("duration"))
    compute_relative_velocity(channel["videos"], fetched_at)
    channel["features"] = compute_channel_features(channel, fetched_at)
    season_coefs = compute_season_coefs([channel])
    apply_season_adjustment([channel], season_coefs)

    potential = heuristic_potential_score(channel["features"])
    if not math.isfinite(potential):
        raise LocalScoreError("calculated Potential P is not finite")

    vertical = channel.get("vertical", "unclassified")
    season_meta = season_coefs.get(vertical) or next(iter(season_coefs.values()), None)
    return {
        "method": "heuristic_local_test",
        "production_comparable": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": source_name,
        "channel_id": channel["channel_id"],
        "potential_p": round(potential, 6),
        "features": channel["features"],
        "seasonality": {
            "vertical": vertical,
            "single_channel_estimate": True,
            "insufficient_sample": season_meta.get("insufficient_sample", True)
            if season_meta
            else True,
            "sample_size": season_meta.get("sample_size", 0) if season_meta else 0,
        },
    }


def save_result(result: dict, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = output_dir / f"potential_{result['channel_id']}_{timestamp}.json"
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute isolated heuristic Potential P for one local channel JSON."
    )
    parser.add_argument("input_json", type=Path, help="one JSON file in local_test_output")
    args = parser.parse_args()

    try:
        input_path = validate_input_path(args.input_json)
        payload = load_payload(input_path)
        result = build_result(payload, input_path.name)
        output_path = save_result(result)
    except LocalScoreError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("SUCCESS")
    print(f"output: {output_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
