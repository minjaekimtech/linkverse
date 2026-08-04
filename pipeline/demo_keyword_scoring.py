"""Pure, metadata-only scoring helpers for the isolated keyword demo."""
from __future__ import annotations

import copy
import math
import re
from datetime import datetime

from pipeline.features import compute_channel_features, compute_relative_velocity
from pipeline.score import heuristic_potential_score


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def metadata_text(channel: dict) -> str:
    parts = [channel.get("title", ""), channel.get("description", "")]
    for video in channel.get("videos", []):
        parts.extend([video.get("title", ""), video.get("description", "")])
        parts.extend(video.get("tags") or [])
    return " ".join(str(part) for part in parts if part).casefold()


def keyword_metrics(channel: dict, keywords: list[str]) -> dict:
    words = [word.casefold() for word in keywords]
    text = metadata_text(channel)
    matched = [word for word in words if word in text]
    videos = channel.get("videos", [])
    matched_videos = sum(
        any(word in metadata_text({"videos": [video]}) for word in words)
        for video in videos
    )
    coverage = len(matched) / len(words) if words else 0
    video_ratio = matched_videos / len(videos) if videos else 0
    occurrences = sum(text.count(word) for word in words)
    density = min(occurrences / max(len(videos), 1) / 3, 1)
    return {
        "score": round(clamp(100 * (0.5 * coverage + 0.3 * video_ratio + 0.2 * density)), 2),
        "matched_keywords": matched,
        "matched_video_count": matched_videos,
    }


def heuristic_p(channel: dict, fetched_at: str) -> float:
    candidate = copy.deepcopy(channel)
    videos = candidate.get("videos", [])
    if not videos:
        return 0.0
    dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    compute_relative_velocity(videos, dt)
    features = compute_channel_features(candidate, dt)
    return round(clamp(float(heuristic_potential_score(features))), 2)


def deduplicate_channels(channels: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result = []
    for channel in channels:
        channel_id = channel.get("channel_id")
        if channel_id and channel_id not in seen:
            seen.add(channel_id)
            result.append(channel)
    return result


def score_channel(channel: dict, fetched_at: str, product_keywords: list[str]) -> dict:
    metrics = keyword_metrics(channel, product_keywords)
    return {
        **channel,
        "P": heuristic_p(channel, fetched_at),
        "productRelevance": metrics["score"],
        "matchedKeywords": metrics["matched_keywords"],
        "matchedVideoCount": metrics["matched_video_count"],
        "potentialMethod": "heuristic_local_test",
        "productionComparable": False,
    }
