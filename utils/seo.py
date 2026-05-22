"""Free SEO enrichment: YouTube autocomplete + Google Trends via pytrends."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

import requests


@dataclass
class TrendsResult:
    search_volume_proxy: float = 0.0
    trend_direction: str = "stable"
    related_top: list[str] = field(default_factory=list)
    related_rising: list[str] = field(default_factory=list)


_trends_session_blocked = False  # once True, skip all pytrends calls for this run


class TrendsRateLimitError(Exception):
    pass


def youtube_autocomplete(query: str, locale: str = "en") -> list[str]:
    """
    Hit YouTube's public suggest endpoint — no auth needed.
    Returns list of autocomplete suggestion strings.
    """
    url = "https://suggestqueries.google.com/complete/search"
    params = {"client": "youtube", "ds": "yt", "q": query, "hl": locale}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        # Response is JSONP: window.google.ac.h([...]) or raw JSON array
        text = resp.text
        # Strip JSONP wrapper if present
        if text.startswith("window."):
            text = text[text.index("(") + 1:text.rindex(")")]
        import json
        data = json.loads(text)
        suggestions = [item[0] for item in data[1] if isinstance(item, list) and item]
        return suggestions
    except Exception:
        return []


def get_trends_data(
    keyword: str,
    lookback_months: int = 12,
    geo: str = "",
) -> TrendsResult:
    """
    Fetch search volume proxy and trend direction via pytrends.
    Raises TrendsRateLimitError on 429.
    """
    from pytrends.request import TrendReq
    from pytrends.exceptions import TooManyRequestsError

    try:
        pt = TrendReq(hl="en-US", tz=360)
        timeframe = f"today {lookback_months}-m"
        pt.build_payload([keyword], cat=0, timeframe=timeframe, geo=geo)
        iot = pt.interest_over_time()

        if iot.empty or keyword not in iot.columns:
            return TrendsResult()

        series = iot[keyword].dropna()
        if len(series) == 0:
            return TrendsResult()

        search_volume_proxy = float(series.mean())

        # Trend direction: compare last 3 months vs prior 3 months
        n = len(series)
        if n >= 6:
            last3 = series.iloc[-3:].mean()
            prior3 = series.iloc[-6:-3].mean()
            if prior3 > 0:
                ratio = last3 / prior3
                if ratio > 1.15:
                    trend_direction = "rising"
                elif ratio < 0.85:
                    trend_direction = "declining"
                else:
                    trend_direction = "stable"
            else:
                trend_direction = "stable"
        else:
            trend_direction = "stable"

        # Related queries
        related_top = []
        related_rising = []
        try:
            rq = pt.related_queries()
            if keyword in rq:
                top_df = rq[keyword].get("top")
                rising_df = rq[keyword].get("rising")
                if top_df is not None and not top_df.empty:
                    related_top = top_df["query"].head(5).tolist()
                if rising_df is not None and not rising_df.empty:
                    related_rising = rising_df["query"].head(5).tolist()
        except Exception:
            pass

        return TrendsResult(
            search_volume_proxy=search_volume_proxy,
            trend_direction=trend_direction,
            related_top=related_top,
            related_rising=related_rising,
        )

    except TooManyRequestsError:
        raise TrendsRateLimitError("pytrends rate limited (429)")
    except Exception:
        return TrendsResult()


def enrich_anchor(
    anchor_title: str,
    cfg_seo: dict,
    sleep_range: tuple[float, float] = (1.5, 2.5),
) -> dict:
    """
    Enrich a single anchor title with autocomplete + trends data.
    Returns dict with seo fields merged in.
    """
    locale = cfg_seo.get("autocomplete_locale", "en")
    lookback = cfg_seo.get("trends_lookback_months", 12)
    geo = cfg_seo.get("trends_region", "")

    # Extract a 2-4 word topic seed from the title.
    # Strip creator names, numbers, filler, and punctuation — keep the core concept.
    import re as _re
    _noise = _re.compile(
        r'\b(andy elliott|jeremy miner|cole gordon|patrick dang|brian choi|nepq|'
        r'remote closing academy|iman gadzhi|7th level|closer cartel|'
        r'how i|how to|why|what|the|a|an|and|or|in|on|at|by|for|with|'
        r'\d+k|\$\d+|2024|2025|2026|live|part|ep|episode)\b|\W+',
        _re.IGNORECASE,
    )
    _CORE_SALES_PHRASES = [
        "cold calling", "cold call", "discovery call", "sales call",
        "objection handling", "objections", "sales script", "sales scripts",
        "high ticket sales", "remote closing", "appointment setting",
        "closing techniques", "sales mindset", "sales tips", "sales training",
        "prospecting", "lead generation", "commission sales", "sales framework",
        "close rate", "tonality", "sales coaching",
    ]
    t_lower = anchor_title.lower()
    seed = ""
    for phrase in _CORE_SALES_PHRASES:
        if phrase in t_lower:
            seed = phrase
            break
    if not seed:
        # Fallback: strip noise, take first 4 meaningful words
        words = [w for w in _noise.sub(' ', anchor_title).split() if len(w) > 3]
        seed = " ".join(words[:4]) if words else anchor_title[:40]

    suggestions = youtube_autocomplete(seed, locale=locale)

    # pytrends call with rate limit handling
    global _trends_session_blocked
    trends = TrendsResult()
    if not _trends_session_blocked:
        for attempt in range(2):
            try:
                time.sleep(random.uniform(*sleep_range))
                trends = get_trends_data(seed, lookback_months=lookback, geo=geo)
                break
            except TrendsRateLimitError:
                if attempt == 0:
                    print("  [seo] Rate limited by pytrends — waiting 15s...")
                    time.sleep(15)
                else:
                    print("  [seo] Rate limit persisted — skipping trends for remainder of run.")
                    _trends_session_blocked = True

    return {
        "autocomplete_suggestions": suggestions,
        "keyword_richness": len(suggestions),
        "search_volume_proxy": trends.search_volume_proxy,
        "trend_direction": trends.trend_direction,
        "related_top": trends.related_top,
        "related_rising": trends.related_rising,
    }
