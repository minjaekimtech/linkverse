"""Safely collect one YouTube channel into an isolated local output folder.

This script intentionally does not use pipeline.collect or QuotaTracker so it
cannot write to pipeline/raw or pipeline/artifacts. It makes one request each
to channels.list, playlistItems.list, and videos.list (when videos exist).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "local_test_output"
BASE_URL = "https://www.googleapis.com/youtube/v3"
MAX_VIDEOS = 50
CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


class SafeCollectionError(RuntimeError):
    """An error message safe to display without response data or credentials."""


def parse_channel(value: str) -> tuple[str, str]:
    """Return the channels.list lookup parameter for one ID or channel URL."""
    candidate = value.strip()
    if CHANNEL_ID_RE.fullmatch(candidate):
        return "id", candidate

    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
    }:
        raise SafeCollectionError("input must be one YouTube channel ID or channel URL")

    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) == 2 and parts[0] == "channel" and CHANNEL_ID_RE.fullmatch(parts[1]):
        return "id", parts[1]
    if len(parts) == 1 and parts[0].startswith("@") and len(parts[0]) > 1:
        return "forHandle", parts[0][1:]
    if len(parts) == 2 and parts[0] == "user" and parts[1]:
        return "forUsername", parts[1]

    raise SafeCollectionError(
        "unsupported channel URL; use /channel/UC..., /@handle, or /user/name"
    )


def api_get(endpoint: str, api_key: str, params: dict[str, str | int]) -> dict:
    """Perform one GET and raise only sanitized errors."""
    query = urllib.parse.urlencode({**params, "key": api_key})
    request = urllib.request.Request(
        f"{BASE_URL}/{endpoint}?{query}", headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SafeCollectionError(f"{endpoint}.list HTTP_ERROR_{exc.code}") from None
    except urllib.error.URLError:
        raise SafeCollectionError(f"{endpoint}.list NETWORK_ERROR") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise SafeCollectionError(f"{endpoint}.list INVALID_RESPONSE") from None


def collect(channel_input: str, api_key: str) -> tuple[dict, dict[str, int]]:
    lookup_name, lookup_value = parse_channel(channel_input)
    calls = {"channels.list": 0, "playlistItems.list": 0, "videos.list": 0}

    calls["channels.list"] += 1
    channel_data = api_get(
        "channels",
        api_key,
        {
            "part": "snippet,statistics,contentDetails",
            lookup_name: lookup_value,
            "maxResults": 1,
        },
    )
    items = channel_data.get("items", [])
    if not items:
        raise SafeCollectionError("CHANNEL_NOT_FOUND")

    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    uploads_id = (
        item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    )
    channel_id = item.get("id")
    if not channel_id or not uploads_id:
        raise SafeCollectionError("CHANNEL_UPLOADS_NOT_AVAILABLE")

    calls["playlistItems.list"] += 1
    playlist_data = api_get(
        "playlistItems",
        api_key,
        {
            "part": "contentDetails",
            "playlistId": uploads_id,
            "maxResults": MAX_VIDEOS,
        },
    )
    video_ids = [
        entry.get("contentDetails", {}).get("videoId")
        for entry in playlist_data.get("items", [])
    ]
    video_ids = [video_id for video_id in video_ids if video_id]

    videos = []
    if video_ids:
        calls["videos.list"] += 1
        video_data = api_get(
            "videos",
            api_key,
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(video_ids),
                "maxResults": MAX_VIDEOS,
            },
        )
        for video in video_data.get("items", []):
            video_snippet = video.get("snippet", {})
            video_statistics = video.get("statistics", {})
            thumbnails = video_snippet.get("thumbnails", {})
            thumbnail = (
                thumbnails.get("high")
                or thumbnails.get("medium")
                or thumbnails.get("default")
                or {}
            )
            videos.append(
                {
                    "video_id": video.get("id"),
                    "title": video_snippet.get("title"),
                    "description": video_snippet.get("description"),
                    "published_at": video_snippet.get("publishedAt"),
                    "tags": video_snippet.get("tags", []),
                    "view_count": int(video_statistics.get("viewCount", 0)),
                    "like_count": int(video_statistics["likeCount"])
                    if "likeCount" in video_statistics
                    else None,
                    "comment_count": int(video_statistics["commentCount"])
                    if "commentCount" in video_statistics
                    else None,
                    "duration": video.get("contentDetails", {}).get("duration"),
                    "thumbnail_url": thumbnail.get("url"),
                }
            )

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "channels": [
            {
                "channel_id": channel_id,
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "country": snippet.get("country"),
                "published_at": snippet.get("publishedAt"),
                "subscriber_count": int(statistics.get("subscriberCount", 0))
                if not statistics.get("hiddenSubscriberCount")
                else None,
                "view_count_total": int(statistics.get("viewCount", 0)),
                "video_count_total": int(statistics.get("videoCount", 0)),
                "uploads_playlist_id": uploads_id,
                "videos": videos,
            }
        ],
        "api_usage": {
            "calls": calls,
            "estimated_quota_units": sum(calls.values()),
        },
    }
    return result, calls


def save_result(result: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    channel_id = result["channels"][0]["channel_id"]
    output_path = OUTPUT_DIR / f"channel_{channel_id}_{timestamp}.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect one YouTube channel into local_test_output only."
    )
    parser.add_argument("channel", help="one channel ID or supported YouTube channel URL")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("KEY_NOT_CONFIGURED", file=sys.stderr)
        return 1

    try:
        result, calls = collect(args.channel, api_key)
        output_path = save_result(result)
    except SafeCollectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("SUCCESS")
    print(f"output: {output_path.relative_to(PROJECT_ROOT)}")
    print(f"API calls: {sum(calls.values())}; estimated quota units: {sum(calls.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
