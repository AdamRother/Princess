"""YouTube Data API v3 client with built-in quota tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

QUOTA_COSTS = {
    "search.list": 100,
    "channels.list": 1,
    "playlistItems.list": 1,
    "videos.list": 1,
}
QUOTA_WARN = 8000
QUOTA_HARD_LIMIT = 9500

_quota_used: int = 0


class QuotaExhaustedError(Exception):
    pass


def check_quota(operation: str) -> None:
    global _quota_used
    cost = QUOTA_COSTS.get(operation, 1)
    if _quota_used + cost > QUOTA_HARD_LIMIT:
        raise QuotaExhaustedError(
            f"Quota limit reached ({_quota_used}/{QUOTA_HARD_LIMIT} units used). "
            f"Re-run tomorrow after the daily quota resets at midnight Pacific."
        )
    _quota_used += cost
    if _quota_used >= QUOTA_WARN:
        print(f"  [quota] WARNING: {_quota_used} units used today. Approaching limit.")


def get_quota_used() -> int:
    return _quota_used


@dataclass
class ChannelMeta:
    id: str
    title: str
    custom_url: str = ""
    subscriber_count: int = 0
    video_count: int = 0
    view_count: int = 0
    country: str = ""
    uploads_playlist_id: str = ""


@dataclass
class VideoStats:
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0


@dataclass
class VideoDetail:
    id: str
    title: str
    published_at: str
    duration_seconds: int
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    description: str = ""
    tags: list[str] = field(default_factory=list)
    thumbnail_url: str = ""


def build_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key)


def search_channels(client, query: str, max_results: int = 25) -> list[str]:
    """Search for channels matching query. Costs 100 units."""
    check_quota("search.list")
    resp = client.search().list(
        q=query,
        type="channel",
        maxResults=max_results,
        order="relevance",
        part="id",
    ).execute()
    return [item["id"]["channelId"] for item in resp.get("items", [])]


def get_channel_metadata(client, channel_ids: list[str]) -> list[ChannelMeta]:
    """Fetch metadata for a list of channel IDs, batched in 50. Costs 1 unit per batch."""
    results = []
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i + 50]
        check_quota("channels.list")
        resp = client.channels().list(
            id=",".join(batch),
            part="snippet,statistics,contentDetails",
            maxResults=50,
        ).execute()
        for item in resp.get("items", []):
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {}).get("relatedPlaylists", {})
            results.append(ChannelMeta(
                id=item["id"],
                title=item["snippet"].get("title", ""),
                custom_url=item["snippet"].get("customUrl", ""),
                subscriber_count=int(stats.get("subscriberCount", 0)),
                video_count=int(stats.get("videoCount", 0)),
                view_count=int(stats.get("viewCount", 0)),
                country=item["snippet"].get("country", ""),
                uploads_playlist_id=content.get("uploads", ""),
            ))
    return results


def list_playlist_items(
    client,
    playlist_id: str,
    stop_at_ids: set[str] | None = None,
    max_items: int = 100,
) -> list[str]:
    """
    Paginate through a playlist and return video IDs.
    Stops early if any returned ID is already in stop_at_ids (cache hit).
    Costs 1 unit per page request.
    """
    video_ids = []
    page_token = None
    stop_at_ids = stop_at_ids or set()

    while len(video_ids) < max_items:
        check_quota("playlistItems.list")
        kwargs = dict(
            playlistId=playlist_id,
            part="contentDetails",
            maxResults=50,
        )
        if page_token:
            kwargs["pageToken"] = page_token
        resp = client.playlistItems().list(**kwargs).execute()

        for item in resp.get("items", []):
            vid_id = item["contentDetails"]["videoId"]
            if vid_id in stop_at_ids:
                return video_ids
            video_ids.append(vid_id)
            if len(video_ids) >= max_items:
                return video_ids

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def get_video_details(client, video_ids: list[str]) -> list[VideoDetail]:
    """Full metadata fetch for video IDs, batched in 50. Costs 1 unit per batch."""
    results = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        check_quota("videos.list")
        resp = client.videos().list(
            id=",".join(batch),
            part="snippet,contentDetails,statistics",
            maxResults=50,
        ).execute()
        for item in resp.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            duration_raw = item.get("contentDetails", {}).get("duration", "PT0S")
            # Skip live streams
            if snippet.get("liveBroadcastContent", "none") != "none":
                continue
            results.append(VideoDetail(
                id=item["id"],
                title=snippet.get("title", ""),
                published_at=snippet.get("publishedAt", ""),
                duration_seconds=parse_duration_seconds(duration_raw),
                view_count=int(stats.get("viewCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                comment_count=int(stats.get("commentCount", 0)),
                description=snippet.get("description", "")[:500],
                tags=snippet.get("tags", []),
                thumbnail_url=(snippet.get("thumbnails", {}).get("high", {}).get("url", "")),
            ))
    return results


def refresh_video_stats(client, video_ids: list[str]) -> dict[str, VideoStats]:
    """Stats-only refresh for cached videos, batched in 50. Costs 1 unit per batch."""
    results = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        check_quota("videos.list")
        resp = client.videos().list(
            id=",".join(batch),
            part="statistics",
            maxResults=50,
        ).execute()
        for item in resp.get("items", []):
            stats = item.get("statistics", {})
            results[item["id"]] = VideoStats(
                view_count=int(stats.get("viewCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                comment_count=int(stats.get("commentCount", 0)),
            )
    return results


def parse_duration_seconds(iso_duration: str) -> int:
    """Parse ISO 8601 duration (PT4M23S) to integer seconds."""
    pattern = re.compile(
        r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?"
    )
    m = pattern.match(iso_duration)
    if not m:
        return 0
    h = int(m.group("h") or 0)
    mn = int(m.group("m") or 0)
    s = int(m.group("s") or 0)
    return h * 3600 + mn * 60 + s


def assign_tier(subscriber_count: int, settings: dict) -> str:
    thresholds = settings.get("tiers", {})
    aspirational_min = thresholds.get("aspirational_min", 100000)
    peer_upper_min = thresholds.get("peer_upper_min", 10000)
    peer_lower_min = thresholds.get("peer_lower_min", 1000)
    if subscriber_count >= aspirational_min:
        return "aspirational"
    if subscriber_count >= peer_upper_min:
        return "peer-upper"
    if subscriber_count >= peer_lower_min:
        return "peer-lower"
    return "emerging"
