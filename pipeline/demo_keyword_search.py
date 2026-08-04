"""Small, isolated YouTube keyword-cache generator for the local demo.

No command runs unless invoked explicitly. Outputs are restricted to
local_test_output/demo_keyword_search and production pipeline paths are never used.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pipeline.demo_keyword_scoring import deduplicate_channels, score_channel

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(__file__).resolve().parent / "config" / "demo_search.yaml"
OUTPUT = ROOT / "local_test_output" / "demo_keyword_search"
BASE_URL = "https://www.googleapis.com/youtube/v3"


class DemoSearchError(RuntimeError):
    pass


def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def api_get(endpoint: str, key: str, params: dict) -> dict:
    query = urllib.parse.urlencode({**params, "key": key})
    try:
        with urllib.request.urlopen(f"{BASE_URL}/{endpoint}?{query}", timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise DemoSearchError(f"{endpoint}.list HTTP_ERROR_{exc.code}") from None
    except urllib.error.URLError:
        raise DemoSearchError(f"{endpoint}.list NETWORK_ERROR") from None


def collect_domain(domain: str, key: str, requester=api_get) -> dict:
    config = load_config()
    if domain not in config["domains"]:
        raise DemoSearchError("UNSUPPORTED_DOMAIN")
    limits, terms = config["limits"], config["domains"][domain]["terms"]
    candidate_ids, per_term = [], []
    calls = {"search.list": 0, "channels.list": 0, "playlistItems.list": 0, "videos.list": 0}
    for term in terms:
        data = requester("search", key, {"part": "snippet", "type": "channel", "q": term,
                                          "maxResults": limits["search_results_per_term"]})
        calls["search.list"] += 1
        ids = [item.get("snippet", {}).get("channelId") for item in data.get("items", [])]
        ids = [value for value in ids if value][:limits["accepted_channels_per_term"]]
        candidate_ids.extend(ids)
        per_term.append({"term": term, "candidateCount": len(ids)})
    ids = list(dict.fromkeys(candidate_ids))[:limits["max_channels_per_domain"]]
    channels = []
    if ids:
        details = requester("channels", key, {"part": "snippet,statistics,contentDetails", "id": ",".join(ids)})
        calls["channels.list"] += 1
        for item in details.get("items", []):
            sn, stats = item.get("snippet", {}), item.get("statistics", {})
            playlist = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            videos = []
            if playlist:
                listing = requester("playlistItems", key, {"part": "contentDetails", "playlistId": playlist,
                                                            "maxResults": limits["recent_videos_per_channel"]})
                calls["playlistItems.list"] += 1
                video_ids = [x.get("contentDetails", {}).get("videoId") for x in listing.get("items", [])]
                video_ids = [x for x in video_ids if x]
                if video_ids:
                    payload = requester("videos", key, {"part": "snippet,statistics,contentDetails", "id": ",".join(video_ids)})
                    calls["videos.list"] += 1
                    for video in payload.get("items", []):
                        vs, st = video.get("snippet", {}), video.get("statistics", {})
                        videos.append({"video_id": video.get("id"), "title": vs.get("title", ""),
                            "description": vs.get("description", ""), "tags": vs.get("tags", []),
                            "published_at": vs.get("publishedAt"), "view_count": int(st.get("viewCount", 0)),
                            "like_count": int(st["likeCount"]) if "likeCount" in st else None,
                            "comment_count": int(st["commentCount"]) if "commentCount" in st else None})
            channels.append({"channel_id": item.get("id"), "title": sn.get("title", ""),
                "description": sn.get("description", ""), "country": sn.get("country"),
                "contentLanguage": sn.get("defaultLanguage") or sn.get("defaultAudioLanguage"),
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "view_count_total": int(stats.get("viewCount", 0)), "videos": videos})
    fetched_at = datetime.now(timezone.utc).isoformat()
    scored = [score_channel(ch, fetched_at, terms) for ch in deduplicate_channels(channels)]
    quota = calls["search.list"] * 100 + sum(value for name, value in calls.items() if name != "search.list")
    return {"domain": domain, "fetchedAt": fetched_at, "sourceMode": "live", "method": "keyword_metadata_demo",
            "productionComparable": False, "termStats": per_term, "apiUsage": {"calls": calls, "estimatedQuotaUnits": quota},
            "creators": scored}


def latest_cache(domain: str) -> Path:
    files = sorted(OUTPUT.glob(f"{domain}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise DemoSearchError("CACHE_NOT_FOUND")
    return files[0]


def save_cache(payload: dict) -> Path:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = OUTPUT / f"{payload['domain']}_{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["warm-cache", "live"])
    parser.add_argument("domain", choices=["sunscreen", "soccer_equipment"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("KEY_NOT_CONFIGURED")
        return 1
    try:
        payload = collect_domain(args.domain, key)
        path = save_cache(payload)
        print(f"SUCCESS {path.relative_to(ROOT)}")
    except DemoSearchError as exc:
        if args.mode == "live":
            try:
                print(f"CACHE_FALLBACK {latest_cache(args.domain).relative_to(ROOT)}")
                return 0
            except DemoSearchError:
                pass
        print(f"ERROR {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
