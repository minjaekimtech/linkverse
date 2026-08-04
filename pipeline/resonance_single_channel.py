"""Compute metadata-only proxy Resonance R for one isolated channel JSON.

The proxy uses explicit keyword rules over the eight most recent videos'
titles, descriptions, and tags. It does not analyze images, call a vision
backend, access production artifacts, or make network requests.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pipeline.score import cosine_similarity_with_contributions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "local_test_output"
DIMENSIONS_PATH = PROJECT_ROOT / "pipeline" / "config" / "dimensions.yaml"
PRODUCTS_PATH = PROJECT_ROOT / "pipeline" / "config" / "products.yaml"
RECENT_VIDEO_LIMIT = 8

# Each dimension is scored as min(unique matched keywords / 3, 1). These are
# deliberately simple, auditable metadata rules—not a substitute for vision.
KEYWORD_RULES: dict[str, tuple[str, ...]] = {
    "perspective_ratio": (
        "pov", "first person", "first-person", "1인칭", "브이로그", "vlog",
        "wearable", "chest mount", "helmet cam", "selfie", "셀카", "고프로",
    ),
    "stabilization_demand": (
        "stabilization", "stabilized", "steady", "running", "run", "러닝",
        "cycling", "bike", "biking", "자전거", "ski", "skiing", "스키",
        "snowboard", "surf", "서핑", "skate", "짐벌", "gimbal",
    ),
    "motion_complexity": (
        "tracking shot", "follow cam", "action", "액션", "parkour", "파쿠르",
        "drone", "드론", "race", "racing", "레이싱", "motocross", "dance",
        "댄스", "chase", "stunt", "스턴트",
    ),
    "scene_extremity": (
        "extreme", "익스트림", "cliff", "절벽", "underwater", "수중", "diving",
        "다이빙", "skydiving", "스카이다이빙", "mountain", "등산", "off-road",
        "오프로드", "storm", "폭풍", "snowboard", "motocross",
    ),
    "gear_visibility": (
        "camera", "카메라", "gopro", "고프로", "insta360", "action cam",
        "액션캠", "lens", "렌즈", "tripod", "삼각대", "gimbal", "짐벌",
        "camera review", "camera test", "unboxing", "언박싱",
    ),
    "narrative_pace": (
        "highlight", "하이라이트", "fast cut", "quick cut", "montage", "몽타주",
        "shorts", "쇼츠", "challenge", "챌린지", "race", "racing", "액션",
        "trailer", "teaser", "티저",
    ),
    "scene_diversity": (
        "travel", "여행", "road trip", "로드트립", "world", "세계", "tour",
        "투어", "adventure", "모험", "city", "도시", "beach", "해변",
        "mountain", "산", "vlog", "브이로그",
    ),
    "slow_motion_demand": (
        "slow motion", "slow-motion", "slowmo", "slo-mo", "슬로모션", "슬로우",
        "120fps", "240fps", "high speed", "고속촬영", "replay", "리플레이",
        "bullet time", "불릿타임",
    ),
}


class LocalResonanceError(ValueError):
    """A validation error safe to print without source-record contents."""


def validate_input_path(path: Path, output_dir: Path = OUTPUT_DIR) -> Path:
    resolved_output = output_dir.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_output:
        raise LocalResonanceError("input must be directly inside local_test_output")
    if not resolved_path.is_file():
        raise LocalResonanceError("input JSON file does not exist")
    if not (resolved_path.name.startswith("channel_") and resolved_path.suffix.lower() == ".json"):
        raise LocalResonanceError("input must be one channel_*.json file")
    return resolved_path


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise LocalResonanceError(f"{label} must be an ISO-8601 string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise LocalResonanceError(f"{label} must be a valid ISO-8601 timestamp") from None


def validate_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise LocalResonanceError("input JSON root must be an object")
    channels = payload.get("channels")
    if not isinstance(channels, list) or len(channels) != 1:
        raise LocalResonanceError("input JSON must contain exactly one channel")
    channel = channels[0]
    if not isinstance(channel, dict):
        raise LocalResonanceError("channel must be an object")
    channel_id = channel.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id.startswith("UC"):
        raise LocalResonanceError("channel_id must be a YouTube channel ID")
    videos = channel.get("videos")
    if not isinstance(videos, list) or not videos:
        raise LocalResonanceError("channel must contain at least one video")
    for index, video in enumerate(videos):
        if not isinstance(video, dict):
            raise LocalResonanceError(f"video at index {index} must be an object")
        _parse_timestamp(video.get("published_at"), f"video at index {index} published_at")
        if not isinstance(video.get("title"), str):
            raise LocalResonanceError(f"video at index {index} title must be a string")
        description = video.get("description")
        if description is not None and not isinstance(description, str):
            raise LocalResonanceError(f"video at index {index} description must be a string or null")
        tags = video.get("tags")
        if tags is not None and (
            not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags)
        ):
            raise LocalResonanceError(f"video at index {index} tags must be strings")
    return payload


def load_payload(input_path: Path) -> dict:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise LocalResonanceError("input is not a readable UTF-8 JSON file") from None
    return validate_payload(payload)


def select_recent_videos(channel: dict) -> list[dict]:
    return sorted(
        channel["videos"],
        key=lambda video: _parse_timestamp(video["published_at"], "video published_at"),
        reverse=True,
    )[:RECENT_VIDEO_LIMIT]


def _video_metadata_text(video: dict) -> str:
    # Only the three explicitly authorized metadata fields are included.
    parts = [video["title"], video.get("description") or ""]
    parts.extend(video.get("tags") or [])
    return "\n".join(parts).casefold()


def build_proxy_vector(videos: list[dict], dimension_keys: list[str]) -> tuple[list[float], dict[str, list[str]]]:
    combined_text = "\n".join(_video_metadata_text(video) for video in videos)
    vector = []
    matches: dict[str, list[str]] = {}
    for key in dimension_keys:
        if key not in KEYWORD_RULES:
            raise LocalResonanceError(f"no keyword rule defined for dimension: {key}")
        matched = sorted({keyword for keyword in KEYWORD_RULES[key] if keyword.casefold() in combined_text})
        matches[key] = matched
        vector.append(min(len(matched) / 3.0, 1.0))
    return vector, matches


def load_config(
    dimensions_path: Path = DIMENSIONS_PATH,
    products_path: Path = PRODUCTS_PATH,
) -> tuple[list[str], list[dict]]:
    try:
        dimensions_data = yaml.safe_load(dimensions_path.read_text(encoding="utf-8"))
        products_data = yaml.safe_load(products_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        raise LocalResonanceError("camera configuration is unreadable") from None

    dimensions = dimensions_data.get("dimensions") if isinstance(dimensions_data, dict) else None
    products = products_data.get("products") if isinstance(products_data, dict) else None
    if not isinstance(dimensions, list) or len(dimensions) != 8:
        raise LocalResonanceError("dimensions config must define exactly eight dimensions")
    dimensions = sorted(dimensions, key=lambda dimension: dimension.get("index", -1))
    dimension_keys = [dimension.get("key") for dimension in dimensions]
    if any(not isinstance(key, str) for key in dimension_keys) or len(set(dimension_keys)) != 8:
        raise LocalResonanceError("dimension keys must be eight unique strings")
    if not isinstance(products, list) or not products:
        raise LocalResonanceError("products config must contain products")
    for product in products:
        if not isinstance(product, dict) or not isinstance(product.get("id"), str):
            raise LocalResonanceError("each product must have an ID")
        vector = product.get("vector")
        if not isinstance(vector, list) or len(vector) != 8 or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector
        ):
            raise LocalResonanceError(f"product {product.get('id')} must have an eight-number vector")
    return dimension_keys, products


def build_result(payload: dict, source_name: str, dimension_keys: list[str], products: list[dict]) -> dict:
    channel = payload["channels"][0]
    videos = select_recent_videos(channel)
    proxy_vector, keyword_matches = build_proxy_vector(videos, dimension_keys)

    product_scores = {}
    for product in products:
        cosine, contributions = cosine_similarity_with_contributions(proxy_vector, product["vector"])
        product_scores[product["id"]] = {
            "product_name": product.get("name"),
            "test_resonance_r": round(cosine * 100, 6),
            "dimension_contributions": [
                {
                    "dimension": key,
                    "value": round(contribution * 100, 6),
                }
                for key, contribution in zip(dimension_keys, contributions)
            ],
        }

    return {
        "method": "metadata_proxy_local_test",
        "production_comparable": False,
        "vision_backend": None,
        "thumbnail_images_analyzed": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": source_name,
        "channel_id": channel["channel_id"],
        "recent_video_count": len(videos),
        "source_video_ids": [video.get("video_id") for video in videos],
        "proxy_vector": {
            "dimension_order": dimension_keys,
            "values": proxy_vector,
            "matched_keywords": keyword_matches,
            "normalization": "min(unique_keyword_matches / 3, 1)",
        },
        "products": product_scores,
    }


def save_result(result: dict, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = output_dir / f"resonance_{result['channel_id']}_{timestamp}.json"
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute metadata-only proxy Resonance R for one local channel JSON."
    )
    parser.add_argument("input_json", type=Path, help="one channel_*.json in local_test_output")
    args = parser.parse_args()

    try:
        input_path = validate_input_path(args.input_json)
        payload = load_payload(input_path)
        dimension_keys, products = load_config()
        result = build_result(payload, input_path.name, dimension_keys, products)
        output_path = save_result(result)
    except LocalResonanceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("SUCCESS")
    print(f"output: {output_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
