"""
Phase 6+7 — Candidate ranking and Google Sheet output.

Computes composite_score for each SEO-enriched anchor, normalizes scores to
0-100, builds the three-tab sheet structure (Topics + Details + Competitors),
and writes to Google Sheets. Returns the Sheet URL.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

from utils.config import Config, load_config, get_setting
from utils.cache import (
    load_run_artifact, get_latest_run_artifact, generate_run_id,
    load_video_cache,
)
from utils.google_workspace import (
    get_sheets_client, ensure_sheet, ensure_docs_folder,
    write_topics_tab, write_details_tab, write_competitors_tab, get_sheet_url,
)


def _composite_score(anchor: dict, top_ids: set[str], cfg: Config) -> float:
    outlier = anchor.get("outlier_score", 1.0)
    tier = anchor.get("source_tier", "emerging")
    primary = anchor.get("primary_competitor", anchor.get("channel_id", "") in top_ids)
    trend = anchor.get("trend_direction", "stable")
    keyword_richness = anchor.get("keyword_richness", 0)
    search_volume = anchor.get("search_volume_proxy", 0.0)

    tier_match_weights = get_setting(cfg, "tier_match_weights", {
        "aspirational": 0.3, "peer-upper": 0.6, "peer-lower": 1.0, "emerging": 0.8,
    })
    primary_boost = get_setting(cfg, "competitors.primary_competitor_boost", 1.25)

    tier_match = tier_match_weights.get(tier, 0.5)
    boost = primary_boost if primary else 1.0
    trend_mod = {"rising": 0.3, "stable": 0.0, "declining": -0.2}.get(trend, 0.0)

    return (
        outlier
        * tier_match
        * boost
        * (1 + trend_mod)
        * (1 + math.log(keyword_richness + 1) * 0.1)
        * (1 + min(search_volume / 100, 1.0) * 0.3)
    )


def _normalize_scores(anchors: list[dict]) -> None:
    """Add score_100 key (0-100) to each anchor via min-max normalization."""
    scores = [a.get("composite_score", 0) for a in anchors]
    min_s = min(scores)
    spread = max(scores) - min_s or 1.0
    for anchor in anchors:
        raw = anchor.get("composite_score", 0)
        anchor["score_100"] = round((raw - min_s) / spread * 100, 1)


_BRAND_STRIP = re.compile(
    r'\b(Andy Elliott|Jeremy Miner|Cole Gordon|Patrick Dang|Brian Choi|NEPQ|'
    r'Remote Closing Academy|7th Level|Iman Gadzhi|Closer Cartel|'
    r'Connor Murray|Science of Scaling|Sales Scripter|Alexis Mai)(?:\'?s)?\b'
    r'|//\s*\w[\w\s]+$',  # also strip "// Channel Name" suffix
    re.IGNORECASE,
)
# Detect titles that are broken after brand stripping
_BROKEN_TITLE = re.compile(
    r"\b(was|at|from|by|with)\s+'s\b"   # orphaned possessive: "I was 's"
    r"|\bat\s+(?:in|from|by|on|the)\b"  # preposition collision: "at in 27 min"
    r"|^\s*'s\b"                          # title starts with orphaned 's
    r"|\bs\s+(?:ex-client|sales|call|closer)\b",  # residual 's' from possessive strip
    re.IGNORECASE,
)
_FILLER = re.compile(r'\s*[\(\[].*?[\)\]]\s*', re.DOTALL)  # remove parentheticals
_TRAILING_PUNCT = re.compile(r'[\s,\-/|…\.]+$')

# YouTube-optimized title formulas per topic.
# Principles applied: keyword-first, specificity with numbers/proof, curiosity gap,
# identity hook, benefit-led, 50-65 chars. Based on MrBeast, Hormozi, Cardone growth strategies.
_TOPIC_TEMPLATES = {
    "cold call": [
        "Cold Calling in 2026: My Exact Script That Books 15+ Meetings a Week",
        "Watch Me Cold Call LIVE When Everyone Hangs Up (Real Calls, No Edits)",
        "Stop Cold Calling Like This — The One Shift That 3x'd My Bookings",
    ],
    "discovery call": [
        "My Exact Discovery Call Script That Closes 60%+ on First Calls",
        "Watch Me Run a Full Discovery Call LIVE (Steal This Word-for-Word)",
        "Why Your Discovery Calls Stall — and the 3-Step Fix That Works",
    ],
    "objection": [
        "Every Sales Objection You'll Ever Face — Handled LIVE (Full Playbook)",
        "Stop Losing Deals to 'I Need to Think About It' — Do This Instead",
        "The Objection Handling Method That Doubled My Close Rate in 90 Days",
    ],
    "script": [
        "Why Sales Scripts Are Killing Your Close Rate (Here's What Works Instead)",
        "The Exact Sales Script I Used to Hit $30k/Month Without Sounding Robotic",
        "I Tested 12 Sales Scripts — Only This One Actually Closes Consistently",
    ],
    "remote closing": [
        "Remote Closing in 2026: My Honest Breakdown After 500+ Calls",
        "How I Became a Remote Closer Making $10k+ Per Month (Exact Roadmap)",
        "The Truth About Remote Closing Jobs Nobody Tells You (Watch Before Applying)",
    ],
    "high ticket": [
        "My Exact Process for Closing $10k–$50k High Ticket Offers on One Call",
        "High Ticket Sales: The 5-Part Call Structure That Closes Without Pressure",
        "Why Most People Fail at High Ticket Sales (And the Fix That Takes One Day)",
    ],
    "mindset": [
        "The One Sales Mindset Shift That Made Me $500k More — Without New Tactics",
        "Why You're Losing Sales in Your Head Before You Even Get on the Call",
        "What Top 1% Closers Believe That Average Reps Never Figure Out",
    ],
    "prospecting": [
        "My Exact Outbound Prospecting System That Books 20+ Calls Per Week",
        "Stop Prospecting Wrong — the Method That Gets Responses in Under 24 Hours",
        "B2B Prospecting in 2026: What's Working, What's Dead, What's Next",
    ],
    "appointment setting": [
        "The Exact Appointment Setting Script That Converts Cold to Booked LIVE",
        "Watch Me Set 5 Appointments in 1 Hour (Real Calls, No Cherry-Picking)",
        "From Setter to $10k Month: The Skills That Actually Get You There",
    ],
    "income": [
        "How Much Money Do Remote Closers Actually Make? (Honest 2026 Breakdown)",
        "How I Went from $0 to $30k/Month in Sales — My Exact Roadmap",
        "The Fastest Path to $10k/Month in Sales Without Cold Email or Cold Calling",
    ],
    "starting over": [
        "If I Were Starting a Sales Career Today, Here's My Exact 90-Day Plan",
        "I'd Skip Everything I Did and Do THIS If I Were Starting Over in Sales",
        "Zero Experience to $10k/Month in Sales: The Roadmap I Wish I Had",
    ],
    "ai": [
        "The AI Sales Stack That's Saving My Team 10+ Hours Every Week",
        "How Top Closers Are Using AI to Prep, Pitch, and Close Faster in 2026",
        "AI Won't Replace Closers — But Closers Using AI Will Replace You",
    ],
    "b2b": [
        "B2B Sales in 2026: The Exact Prospecting and Closing System That Works",
        "How to Close B2B Deals Without Losing to 'We Need to Loop In Legal'",
        "The B2B Sales Process That Cuts Deal Cycles in Half (Step-by-Step)",
    ],
    "close rate": [
        "How I Went from 20% to 60% Close Rate in 90 Days (The Exact Method)",
        "Your Close Rate Is a Lagging Indicator — Fix These 3 Things Instead",
        "The Call Recording Review System That Quietly Doubled My Close Rate",
    ],
    "commission": [
        "How Commission-Only Sales Actually Works — and Why Most People Quit Too Early",
        "I've Paid Out $1M+ in Sales Commissions — Here's What Top Reps Do Differently",
        "Want to Double Your Commission Without Changing Your Offer? Watch This First",
    ],
}


def _extract_topic_key(title: str) -> str:
    """Return the best matching topic key from _TOPIC_TEMPLATES, or '' if none."""
    t = title.lower()
    # Longer / more specific phrases first to avoid false matches
    priority = [
        "cold call", "discovery call", "appointment setting", "remote closing",
        "high ticket", "close rate", "commission", "objection", "script",
        "prospecting", "mindset", "income", "starting over", "ai", "b2b",
    ]
    for key in priority:
        if key in t:
            return key
    return ""


def _suggested_title(anchor: dict) -> str:
    """
    Generate a YouTube-optimized title for the user's channel based on the source topic.

    Strategy: the source video's title is ALREADY proven (high CTR, high views).
    We clean off competitor branding and reframe for our channel voice.
    Templates are only used when the source title is too short or uninformative (<20 chars).
    This ensures every topic row has a UNIQUE idea title.
    """
    source_title = anchor.get("title", anchor.get("topic", "")).strip()

    # Step 1: Clean the source title — remove brands, parentheticals, noise
    cleaned = _BRAND_STRIP.sub("", source_title)
    cleaned = _FILLER.sub(" ", cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = _TRAILING_PUNCT.sub("", cleaned)

    # Fix ALL-CAPS titles → sentence case
    if cleaned == cleaned.upper() and len(cleaned) > 4:
        cleaned = cleaned.capitalize()

    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    # Step 2: Validate the cleaned title isn't broken by the brand strip
    is_broken = (
        _BROKEN_TITLE.search(cleaned) is not None
        or cleaned.strip().startswith("'s")
        or cleaned.strip().lower().startswith("ex-client")
        or cleaned.strip().lower().startswith("s ex-client")
        or len(cleaned) < 15
    )
    if not is_broken:
        # If cleaned title is specific and useful, use it (with length trim)
        # "Specific" = has numbers, dollar amounts, timeframes, or is long enough to have detail
        has_specifics = bool(re.search(
            r'\$|£|\d+[k+]?\b|LIVE|live|exact|watch me|how i|i made|i was|i sucked|i went|my exact',
            cleaned.lower()
        ))
        if len(cleaned) >= 20 and (has_specifics or len(cleaned) >= 40):
            if len(cleaned) > 70:
                trunc = cleaned[:67]
                last_space = trunc.rfind(' ')
                cleaned = (trunc[:last_space] if last_space > 45 else trunc) + "..."
            return cleaned

    # Step 3: Source title too short, broken, or generic — use topic template
    topic_key = _extract_topic_key(source_title)
    if topic_key and topic_key in _TOPIC_TEMPLATES:
        return _TOPIC_TEMPLATES[topic_key][0]

    # Step 4: Last resort — return whatever cleaned version we have
    return cleaned if len(cleaned) > 10 else source_title


def _extract_core(title: str) -> str:
    """Extract the actionable concept from a title for use in variant templates."""
    topic_key = _extract_topic_key(title)

    _CONCEPT_MAP = {
        "cold call": "Cold Calling",
        "discovery call": "Running Discovery Calls",
        "objection": "Objection Handling",
        "script": "Sales Scripts",
        "remote closing": "Remote Closing",
        "high ticket": "High Ticket Closing",
        "mindset": "Sales Mindset",
        "prospecting": "Prospecting",
        "appointment setting": "Appointment Setting",
        "income": "Earning More in Sales",
        "starting over": "Starting a Sales Career",
        "ai": "AI in Sales",
        "b2b": "B2B Sales",
        "close rate": "Close Rate",
        "commission": "Commission",
    }
    if topic_key in _CONCEPT_MAP:
        return _CONCEPT_MAP[topic_key]

    # Generic fallback: strip common prefixes
    stripped = title.strip()
    for prefix in ["How I ", "How to ", "Why ", "What ", "The Truth About ",
                   "Stop ", "I Sucked at ", "I Was "]:
        if stripped.lower().startswith(prefix.lower()):
            stripped = stripped[len(prefix):]
            break
    # Remove brand references
    stripped = _BRAND_STRIP.sub("", stripped).strip()
    return stripped[:50] if stripped else title[:50]


def _build_proof_parts(anchor: dict) -> dict:
    """
    Return proof cell components for the two-line hyperlinked Proof column.
    Returns dict with: line1, line2, url, plain_text.
    line1 = stat line (dark text), line2 = source link (blue hyperlink).
    """
    outlier = anchor.get("outlier_score", 1.0)
    views = anchor.get("source_views", anchor.get("view_count", 0))
    days = int(anchor.get("days_since_publish", anchor.get("age_days", 0)))
    channel = anchor.get("source_channel", anchor.get("channel_name", "unknown"))
    title = (anchor.get("source_title", anchor.get("topic", "")))[:45]

    vid_id = anchor.get("video_id", anchor.get("id", ""))
    url = anchor.get("source_url", "")
    if not url and vid_id:
        url = f"https://www.youtube.com/watch?v={vid_id}"

    emoji = "🔥" if outlier >= 3.0 else ("✅" if outlier >= 1.5 else "📌")
    line1 = f"{emoji} {outlier:.1f}x outlier · {views:,} views · {days:,} days"
    line2 = f"→ {channel} / {title}"

    return {"line1": line1, "line2": line2, "url": url, "plain_text": f"{line1}\n{line2}"}


def _build_search_demand_cell(anchor: dict) -> str:
    """Return two-line search demand cell: trend label + interest score."""
    trend = anchor.get("trend_direction", "stable").lower()
    score = int(round(anchor.get("search_volume_proxy", 0)))
    arrow = {"rising": "↗", "declining": "↘", "stable": "→"}.get(trend, "→")
    label = {"rising": "Rising", "declining": "Declining", "stable": "Steady"}.get(trend, "Steady")
    return f"{arrow} {label}\ninterest {score}"


def _why_it_works(anchor: dict) -> str:
    """Explain specifically why this video performed — what drove the numbers."""
    views = anchor.get("source_views", anchor.get("view_count", 0))
    outlier = anchor.get("outlier_score", 1.0)
    channel = anchor.get("source_channel", anchor.get("channel_name", ""))
    trend = anchor.get("trend_direction", "stable")
    cluster_size = anchor.get("cluster_size", 1)
    keyword_richness = anchor.get("keyword_richness", 0)
    vpd = anchor.get("views_per_day", 0)
    title = anchor.get("source_title", anchor.get("topic", ""))

    parts = []

    # Outlier signal — explain what the number means
    if outlier >= 5.0:
        parts.append(
            f"This video hit {outlier:.1f}x {channel}'s channel median ({views:,} views, {int(vpd):,}/day) — "
            f"a breakout that signals the topic and format connected at a level the channel rarely sees."
        )
    elif outlier >= 2.0:
        parts.append(
            f"At {outlier:.1f}x the channel median, this outperformed most of {channel}'s catalog "
            f"({views:,} views, {int(vpd):,}/day) — the topic clearly has demand above background noise."
        )
    else:
        parts.append(
            f"Steady performer at {views:,} views ({int(vpd):,}/day) — consistent demand "
            f"without a spike, which suggests strong evergreen relevance rather than a trending moment."
        )

    # Pattern + search signal
    signals = []
    if cluster_size >= 4:
        signals.append(
            f"{cluster_size} different creators have covered this same angle and all got traction — "
            f"the format is repeatable, not a one-channel fluke"
        )
    elif cluster_size >= 2:
        signals.append(f"{cluster_size} similar videos found across channels, confirming the topic has broad appeal")

    if keyword_richness >= 8:
        signals.append(
            f"YouTube autocomplete returns {keyword_richness} variants on this topic, "
            f"meaning searchers are already looking for exactly this content"
        )
    elif keyword_richness >= 4:
        signals.append(f"{keyword_richness} autocomplete variants confirm active search demand")

    if trend == "rising":
        signals.append("Google Trends is rising on this topic — the audience is growing, not shrinking 📈")
    elif trend == "declining":
        signals.append("Trends signal is declining — the angle that worked here may need a timely hook to stay relevant ⚠️")

    if signals:
        parts.append(". ".join(signals[:2]) + ".")

    return " ".join(parts)


def _generate_variants(anchor: dict, idea: str) -> list[dict]:
    """
    Generate 10 angle variants using proven YouTube growth formulas.

    Angles are drawn from what the highest-performing creators do:
    MrBeast (specificity + stakes), Hormozi (exact system + income proof),
    Cardone (identity hook), plus SEO pillars for Google + YouTube indexing.
    """
    core = _extract_core(idea)
    outlier = anchor.get("outlier_score", 1.0)
    views = anchor.get("source_views", anchor.get("view_count", 0))
    tier = anchor.get("source_tier", "peer-lower")
    trend = anchor.get("trend_direction", "stable")
    channel = anchor.get("source_channel", anchor.get("channel_name", "a peer channel"))

    trend_ctx = {
        "rising": f"Search interest for {core} is rising — this window is open right now.",
        "stable": f"{core} has stable evergreen demand — safe long-term bet with no urgency cliff.",
        "declining": f"Trend for {core} is softening — this angle needs a fresh hook or a pivot to a rising sub-keyword.",
    }.get(trend, f"{core} shows steady demand.")

    return [
        # 1. INCOME PROOF + STORY
        {
            "angle": "Income Proof + Story",
            "variant_title": f"How I Went from Struggling to $10k/Month Using {core} (Exact Steps)",
            "what_modified": (
                "Lead with a specific income milestone you hit, tie it directly to this topic. "
                "Open with the before (struggling), reveal the one thing that changed it, then teach the system."
            ),
            "why_angle": (
                f"Income-proof titles pull the highest CTR in the sales niche because they pre-qualify the viewer — "
                f"only motivated people click. Tying a real dollar figure to {core} turns an educational video into a "
                f"transformation story, which drives saves (your strongest long-tail signal). "
                f"'Exact Steps' in the title signals the viewer will leave with something they can use today. {trend_ctx}"
            ),
        },
        # 2. LIVE PROOF
        {
            "angle": "Live Proof",
            "variant_title": f"Watch Me {core} LIVE — Real Calls, No Edits, No Cherry-Picking",
            "what_modified": (
                "Film yourself actually doing this skill on a real call or live session. "
                "No cuts, no actors — show the messy reality including objections or pauses."
            ),
            "why_angle": (
                f"Live-format removes the #1 objection to sales education: 'this is just theory.' "
                f"Showing real execution on {core} builds trust faster than any scripted video. "
                f"Watch time spikes because viewers stay to see how it resolves — no-edit framing eliminates skepticism "
                f"and signals authenticity before they've even watched 10 seconds. {trend_ctx}"
            ),
        },
        # 3. HARSH TRUTH
        {
            "angle": "Harsh Truth",
            "variant_title": f"Why 90% of Closers Fail at {core} (And the Fix Nobody Talks About)",
            "what_modified": (
                "Open by naming the most common mistake most people make on this topic, "
                "then pivot to the counterintuitive fix. Don't soften the hook."
            ),
            "why_angle": (
                f"Loss aversion outperforms benefit framing in CTR — fear of being in the 90% beats hope of being in the 10%. "
                f"For {core}, this works especially well because most sales reps already feel they're doing it wrong. "
                f"'Nobody talks about' filters for viewers who've tried the basics and are ready for the real answer, "
                f"which means higher comment engagement and lower skip rate. {trend_ctx}"
            ),
        },
        # 4. STEAL MY SYSTEM
        {
            "angle": "Steal My System",
            "variant_title": f"The Exact {core} Script/Framework I Use on Every Call (Copy This)",
            "what_modified": (
                "Give away your complete working process — word-for-word, step-by-step. "
                "Don't tease it; deliver it fully. The value is in the completeness."
            ),
            "why_angle": (
                f"'Steal/Copy' titles generate the highest save rate of any format in the education niche. "
                f"Saves tell YouTube this video has lasting reference value, which extends distribution weeks after publish. "
                f"For {core} specifically, a word-for-word framework is exactly what searchers are looking for — "
                f"'exact {core.lower()} script' is a high-intent Google and YouTube query. {trend_ctx}"
            ),
        },
        # 5. MYTH BUSTER
        {
            "angle": "Myth Buster",
            "variant_title": f"Stop {core} the Wrong Way — This Is What Top 1% Reps Actually Do",
            "what_modified": (
                "Identify the mainstream advice on this topic and systematically prove it's wrong "
                "or incomplete using your own results. Position the correction as the insider secret."
            ),
            "why_angle": (
                f"Contrarian titles trigger two emotions — disagreement ('they're wrong') or relief ('I knew it') — "
                f"and both drive shares. For {core}, there's enough mainstream advice floating around that a "
                f"myth-busting frame feels credible, not clickbait. 'Top 1%' creates identity aspiration and filters "
                f"for high-value viewers who want to be in that group. {trend_ctx}"
            ),
        },
        # 6. SPECIFIC NUMBERS
        {
            "angle": "Specific Numbers",
            "variant_title": f"5 {core} Mistakes That Are Costing You Deals Right Now",
            "what_modified": (
                "Structure as 5 (or 7, or 3) specific, named mistakes with their exact fix. "
                "Each mistake is a mini-video in itself — title it in chapters so YouTube and Google can index each one."
            ),
            "why_angle": (
                f"Number-based titles outperform vague titles because they set a concrete expectation — "
                f"the viewer knows exactly what they're getting. For {core}, each numbered mistake becomes a "
                f"chapter YouTube can surface independently in search, multiplying your indexing surface. "
                f"List format also retains skimmers who consume in 3-minute blocks and return later. {trend_ctx}"
            ),
        },
        # 7. IDENTITY HOOK
        {
            "angle": "Identity Hook",
            "variant_title": f"If You're a Closer or Setter and You're Not Doing This With {core}, You're Leaving Money",
            "what_modified": (
                "Open by speaking directly to a specific role — closer, setter, founder, SDR. "
                "Name the identity before naming the topic. They should feel personally called out within 3 seconds."
            ),
            "why_angle": (
                f"Identity-first titles drive the highest subscribe-on-click rate because the viewer thinks "
                f"'this channel is built for me.' For {core}, naming a specific role (closer, setter, founder) "
                f"before the topic means only your target audience clicks — lower volume but much higher "
                f"relevance, which trains the algorithm toward your ideal viewer profile. {trend_ctx}"
            ),
        },
        # 8. COMPARISON / VERSUS
        {
            "angle": "Comparison / Versus",
            "variant_title": f"{core}: Old Method vs. What Actually Works in 2026 (Side-by-Side)",
            "what_modified": (
                "Set up a direct comparison — old vs new, wrong vs right, amateur vs pro approach. "
                "Use split-screen or chapter format to make the contrast visual and immediate."
            ),
            "why_angle": (
                f"Versus-format captures two search intents at once — people looking for the old method "
                f"AND people looking for the updated one. For {core}, this is powerful because there's an "
                f"obvious generational shift in what works. The contrast is also highly shareable: "
                f"viewers tag other reps who still use the old approach. {trend_ctx}"
            ),
        },
        # 9. CONFESSION + BEFORE/AFTER
        {
            "angle": "Confession + Before/After",
            "variant_title": f"I Was Terrible at {core} Until I Found This One Thing ($X Later)",
            "what_modified": (
                "Start with your lowest point on this topic — the specific moment you realized you were doing it wrong. "
                "Put a dollar figure or a result ($X, X deals closed, X% rate) in the title as the after proof."
            ),
            "why_angle": (
                f"Before/after with a specific result is the sales niche's version of a transformation story. "
                f"For {core}, a confession disarms the viewer's skepticism before you've said a word — "
                f"it signals you've been where they are, which is the fastest way to build authority. "
                f"Viewers stay because they need to find out 'the one thing,' which drives full-video retention. {trend_ctx}"
            ),
        },
        # 10. COMPLETE GUIDE / PILLAR
        {
            "angle": "Complete Guide (Pillar)",
            "variant_title": f"The Complete {core} Guide for 2026 — Start, Improve, and Close More",
            "what_modified": (
                "Make this the definitive video on the topic — at least 20 minutes, fully chaptered. "
                "Cover beginner, intermediate, and advanced in one video. Pin it, link it everywhere, treat it as your flagship for this keyword."
            ),
            "why_angle": (
                f"A pillar video on {core} ranks in YouTube search AND Google search simultaneously — "
                f"Google surfaces YouTube videos for 'how to [topic]' queries, doubling your distribution. "
                f"Long watch time from a comprehensive guide trains the algorithm that your channel produces "
                f"high-value content. One well-structured pillar can drive consistent traffic for 2+ years "
                f"without any promotion effort. {trend_ctx}"
            ),
        },
    ]


def _build_details_row(
    anchor: dict,
    idea: str,
    proof: str,
    run_id: str,
    topic_num: int,
) -> dict:
    """Compile all analyst metadata for the Details tab (one row per topic)."""
    vid_id = anchor.get("video_id", anchor.get("id", ""))
    url = anchor.get("source_url", "")
    if not url and vid_id:
        url = f"https://www.youtube.com/watch?v={vid_id}"

    return {
        "topic_num": topic_num,
        "idea": idea,
        "source_channel": anchor.get("source_channel", anchor.get("channel_name", "")),
        "source_title": anchor.get("source_title", anchor.get("topic", "")),
        "source_url": url,
        "views_per_day": anchor.get("views_per_day", 0),
        "engagement_rate": anchor.get("engagement_rate", 0),
        "autocomplete_keywords": anchor.get("autocomplete_suggestions", []),
        "related_searches": anchor.get("related_searches", []),
        "publish_date": anchor.get("published_at", anchor.get("publish_date", "")),
        "duration_seconds": anchor.get("duration_seconds", 0),
        "channel_tier": anchor.get("source_tier", anchor.get("tier", "")),
        "primary_competitor": anchor.get("primary_competitor", False),
        "source_tags": anchor.get("tags", []),
        "description_excerpt": str(anchor.get("description", ""))[:200],
        "run_timestamp": run_id,
    }


def _build_competitors_rows(cfg: Config) -> list[dict]:
    """Build rows for the Top 10 Competitors tab from channels.yaml + video cache."""
    import statistics as _stats

    sorted_competitors = sorted(cfg.channels.top_competitors, key=lambda tc: tc.subs, reverse=True)
    for rank_idx, tc in enumerate(sorted_competitors, 1):
        tc.rank = rank_idx

    rows = []
    for tc in sorted_competitors:
        cache = load_video_cache(tc.id)
        videos = (cache or {}).get("videos", [])

        view_counts = [v.get("view_count", 0) for v in videos if v.get("view_count", 0) > 0]
        median_views = int(_stats.median(view_counts)) if view_counts else 0
        recent_views = [v.get("view_count", 0) for v in videos[:10] if v.get("view_count", 0) > 0]
        recent_median = int(_stats.median(recent_views)) if recent_views else 0

        trajectory = "→"
        if median_views > 0:
            ratio = recent_median / median_views
            if ratio > 1.2:
                trajectory = "↑"
            elif ratio < 0.8:
                trajectory = "↓"

        engagement_rates = []
        for v in videos[:30]:
            views = v.get("view_count", 1)
            eng = (v.get("like_count", 0) + v.get("comment_count", 0)) / max(views, 1)
            engagement_rates.append(eng)
        med_eng = _stats.median(engagement_rates) if engagement_rates else 0

        sorted_vids = sorted(videos, key=lambda v: v.get("view_count", 0), reverse=True)
        breakouts = []
        for v in sorted_vids[:3]:
            ch_median = median_views or 1
            outlier = v.get("view_count", 0) / ch_median
            breakouts.append(f"{v.get('title', '')[:40]} — {outlier:.1f}x")

        rows.append({
            "rank": tc.rank,
            "name": tc.name,
            "subs": tc.subs,
            "tier": tc.tier,
            "composite_score": tc.composite_score,
            "uploads_per_month": len(videos) / 24 if videos else 0,
            "median_views": median_views,
            "recent_median_views": recent_median,
            "trajectory": trajectory,
            "engagement_rate": med_eng,
            "breakout_1": breakouts[0] if len(breakouts) > 0 else "",
            "breakout_2": breakouts[1] if len(breakouts) > 1 else "",
            "breakout_3": breakouts[2] if len(breakouts) > 2 else "",
        })
    return rows


def run(
    cfg: Config,
    run_id: str | None = None,
    upstream: list[dict] | None = None,
) -> str:
    """
    Rank anchors, build three-tab sheet data, write to Google Sheet.
    Returns the Sheet URL.
    """
    if upstream is not None:
        anchors = upstream
    else:
        if run_id:
            result = load_run_artifact(run_id, "seo_enriched")
        else:
            result = None
            found = get_latest_run_artifact("seo_enriched")
            if found:
                run_id, result = found

        if not result:
            print("[Phase 6+7] No seo_enriched artifact found. Run Phase 5 first.")
            return ""
        anchors = result.get("anchors", [])

    run_id = run_id or generate_run_id()

    if not anchors:
        print("[Phase 6+7] No anchors to rank.")
        return ""

    top_ids = {tc.id for tc in cfg.channels.top_competitors}
    top_n = get_setting(cfg, "sheet.top_n_candidates", 20)
    sheet_title = get_setting(cfg, "sheet.name", "Sales YT — Topic Research")
    docs_folder_name = get_setting(cfg, "script.google_doc_folder_name", "Sales YT — Scripts")

    print(f"\n[Phase 6+7] Ranking {len(anchors)} candidates...")

    for anchor in anchors:
        anchor["composite_score"] = _composite_score(anchor, top_ids, cfg)

    # Split into trending (≤90 days) and evergreen (>90 days) buckets
    trending_anchors = [a for a in anchors if a.get("recency_bucket") == "trending"]
    evergreen_anchors = [a for a in anchors if a.get("recency_bucket") != "trending"]

    # Each tab targets top_n // 2 topics (default 100 each).
    # If one bucket has fewer candidates than the target, the other doesn't compensate —
    # both tabs are capped independently so counts stay as equal as the data allows.
    per_tab = top_n // 2

    def _rank_bucket(bucket: list[dict], n: int) -> list[dict]:
        bucket.sort(key=lambda a: a["composite_score"], reverse=True)
        top = bucket[:n]
        _normalize_scores(top)
        top.sort(key=lambda a: a.get("score_100", 0), reverse=True)
        return top

    trending_top = _rank_bucket(trending_anchors, per_tab)
    evergreen_top = _rank_bucket(evergreen_anchors, per_tab)

    print(f"  Trending Now: {len(trending_top)} topics  |  Proven Evergreen: {len(evergreen_top)} topics")

    def _build_tab_data(top: list[dict], run_id: str, offset: int = 0):
        rows, variants, details = [], [], []
        for i, anchor in enumerate(top):
            idea = _suggested_title(anchor)
            proof = _build_proof_parts(anchor)
            search_demand = _build_search_demand_cell(anchor)
            why = _why_it_works(anchor)
            score = int(round(anchor.get("score_100", 0)))
            autocomplete = anchor.get("autocomplete_suggestions", [])
            keywords_cell = ", ".join(autocomplete[:5]) if autocomplete else anchor.get("keyword_seed", "")
            rows.append({
                "idea": idea,
                "proof_line1": proof["line1"],
                "proof_line2": proof["line2"],
                "proof_url": proof["url"],
                "search_demand": search_demand,
                "why_it_works": why,
                "keywords": keywords_cell,
                "score": score,
            })
            variants.append(_generate_variants(anchor, idea))
            details.append(_build_details_row(anchor, idea, proof["plain_text"], run_id, offset + i + 1))
        return rows, variants, details

    trending_rows, trending_variants, trending_details = _build_tab_data(trending_top, run_id, 0)
    evergreen_rows, evergreen_variants, evergreen_details = _build_tab_data(evergreen_top, run_id, len(trending_top))
    all_details = trending_details + evergreen_details

    # Connect to Google Sheets
    print(f"  Connecting to Google Sheets...")
    gc = get_sheets_client(cfg.client_secrets_path)
    spreadsheet = ensure_sheet(gc, cfg.target_sheet_id, sheet_title)

    if cfg.target_docs_folder_id == "auto":
        from utils.google_workspace import get_drive_service
        drive_service = get_drive_service(cfg.client_secrets_path)
        ensure_docs_folder(drive_service, cfg.target_docs_folder_id, docs_folder_name)

    # Remove legacy tabs that are no longer part of the design
    from utils.google_workspace import delete_tab_if_exists
    for legacy in ("Topics", "Variants", "Content Clusters", "Details"):
        delete_tab_if_exists(spreadsheet, gc, legacy)

    # Write both topic tabs with identical design
    if trending_rows:
        write_topics_tab(spreadsheet, gc, trending_rows, trending_variants, tab_name="Trending Now")
        print(f"  'Trending Now' tab: {len(trending_rows)} topics × 10 angle variants each")
    if evergreen_rows:
        write_topics_tab(spreadsheet, gc, evergreen_rows, evergreen_variants, tab_name="Proven Evergreen")
        print(f"  'Proven Evergreen' tab: {len(evergreen_rows)} topics × 10 angle variants each")

    if cfg.channels.top_competitors:
        competitor_rows = _build_competitors_rows(cfg)
        write_competitors_tab(spreadsheet, competitor_rows)
        print(f"  Competitors tab: {len(competitor_rows)} rows")

    sheet_url = get_sheet_url(spreadsheet)
    return sheet_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 6+7: Rank candidates and write to sheet")
    parser.add_argument("--run-id", help="Run ID to load seo_enriched artifact from")
    args = parser.parse_args()
    cfg = load_config()
    url = run(cfg, run_id=args.run_id)
    if url:
        print(f"\n  Sheet: {url}")
