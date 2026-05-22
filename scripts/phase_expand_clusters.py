"""
Topical Authority Cluster Expansion.

Takes the top ranked topics from the SEO-enriched results and expands each one
into a full content cluster: 1 pillar + 12 angle spokes + keyword-specific spokes
from autocomplete suggestions.

Math: 20 core topics × ~15 videos = 300 videos minimum.
With subtopic drilling across the full 100 topics = 500-1,000+ video ideas.

Writes a "Content Clusters" tab to the Google Sheet.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from utils.config import Config, load_config
from utils.cache import load_run_artifact, get_latest_run_artifact
from utils.google_workspace import (
    get_sheets_client, ensure_sheet, write_clusters_tab, get_sheet_url,
)

# Niche-specific identity terms — used to personalise angle titles
IDENTITIES = ["High-Ticket Closer", "Appointment Setter", "Remote Closer", "Sales Rep"]
PRIMARY_IDENTITY = "Sales Coach"

# CTR-optimized templates for keyword spokes (rotated by index)
KEYWORD_SPOKE_TEMPLATES = [
    "My Exact {suggestion_tc} (Step-by-Step Breakdown)",
    "The {suggestion_tc} That Actually Works in 2025",
    "How to Master {suggestion_tc} (No Fluff)",
    "{suggestion_tc}: What Top 1% Closers Do Differently",
    "The Only {suggestion_tc} Guide You'll Ever Need",
    "Why Your {suggestion_tc} Isn't Working (And the Fix)",
    "{suggestion_tc}: The Framework That Doubled My Close Rate",
    "The Truth About {suggestion_tc} (From a Real Closer)",
]

# The 12 angle lenses with title templates
# {topic} = the core topic, {identity} = primary identity
ANGLE_LENSES = [
    {
        "lens": "Skill Level — Beginner",
        "template": "The Beginner's Guide to {topic} (Start Here)",
        "keyword_suffix": "for beginners",
        "priority": "High",
        "why": "Captures top-of-funnel search volume; easiest entry point for new closers.",
    },
    {
        "lens": "Skill Level — Advanced",
        "template": "Advanced {topic}: What Top 1% Closers Do Differently",
        "keyword_suffix": "advanced",
        "priority": "Medium",
        "why": "Differentiates from beginner content; attracts experienced practitioners.",
    },
    {
        "lens": "Identity",
        "template": "How {identity}s Master {topic} (Step-by-Step)",
        "keyword_suffix": "for closers",
        "priority": "High",
        "why": "Identity-targeted content converts better; exact match for core audience.",
    },
    {
        "lens": "Outcome",
        "template": "The {topic} Framework That Doubled My Close Rate",
        "keyword_suffix": "close rate",
        "priority": "High",
        "why": "Outcome-focused hook; clear promise drives CTR and subscriber intent.",
    },
    {
        "lens": "Myth-Busting",
        "template": "Stop Doing This With {topic} — Here's What Actually Works",
        "keyword_suffix": "mistakes",
        "priority": "High",
        "why": "Contrarian hook is the #1 CTR driver in this niche; proven by Brian Choi, Jeremy Miner.",
    },
    {
        "lens": "Story-Led",
        "template": "The {topic} Lesson That Cost Me a $20K Deal",
        "keyword_suffix": "story",
        "priority": "High",
        "why": "Personal story + dollar amount = trust + curiosity; highest engagement format.",
    },
    {
        "lens": "Live Demonstration",
        "template": "Watch Me Handle {topic} LIVE on a Real Sales Call",
        "keyword_suffix": "live roleplay",
        "priority": "High",
        "why": "Live demos are the #1 outlier format for peer-tier channels (38K+ views on cold call videos).",
    },
    {
        "lens": "Failure / Mistake",
        "template": "5 {topic} Mistakes That Are Killing Your Close Rate",
        "keyword_suffix": "mistakes to avoid",
        "priority": "Medium",
        "why": "Failure content builds deep trust; numbers in title increase CTR 20-30%.",
    },
    {
        "lens": "Speed / Simplicity",
        "template": "Master {topic} in 10 Minutes (The Simple Method)",
        "keyword_suffix": "simple",
        "priority": "Medium",
        "why": "Time-bound promise reduces friction; works well as a short-form companion.",
    },
    {
        "lens": "Psychology / Root Cause",
        "template": "The Psychology Behind {topic} (Why Prospects Really React This Way)",
        "keyword_suffix": "psychology",
        "priority": "Medium",
        "why": "Positions creator as deeper thinker; high comment engagement from practitioners.",
    },
    {
        "lens": "System / Framework",
        "template": "My Exact {topic} System: Full Walkthrough for Any Sales Call",
        "keyword_suffix": "framework system",
        "priority": "High",
        "why": "Framework videos signal authority; highest shareability in professional communities.",
    },
    {
        "lens": "Comparison",
        "template": "{topic}: What Works at $5K vs. $50K Offers (Big Difference)",
        "keyword_suffix": "high ticket vs low ticket",
        "priority": "Medium",
        "why": "Comparison format answers a real decision the audience faces; strong suggested traffic.",
    },
]

# Niche-specific subtopic expansions — drills one level deeper on common topics
NICHE_SUBTOPICS: dict[str, list[str]] = {
    "objection": [
        "I need to think about it",
        "it's too expensive",
        "I need to talk to my spouse",
        "send me more info",
        "I need to think about it objection",
        "price objection high ticket",
        "not interested objection cold call",
        "I already have someone objection",
    ],
    "closing": [
        "one call close",
        "how to ask for the sale",
        "closing without being pushy",
        "closing on discovery calls",
        "closing warm leads",
        "closing cold traffic",
        "trial close techniques",
        "assumptive close",
    ],
    "appointment setting": [
        "appointment setter interview",
        "appointment setter script",
        "how to book more appointments",
        "appointment setter income",
        "setter to closer",
        "appointment setting cold DM",
        "appointment setting cold call",
        "appointment setter for coaches",
    ],
    "cold call": [
        "cold call opener",
        "cold call script high ticket",
        "cold call objections",
        "cold calling tips 2025",
        "best time to cold call",
        "cold call to appointment",
        "cold call roleplay",
        "100 cold calls a day",
    ],
    "discovery call": [
        "discovery call framework",
        "discovery call questions",
        "discovery call script",
        "how to run a discovery call",
        "discovery call to close",
        "discovery call mistakes",
        "qualifying on discovery calls",
    ],
    "follow up": [
        "how to follow up after a sales call",
        "follow up without being annoying",
        "follow up sequence high ticket",
        "ghosted after sales call",
        "follow up text vs email",
        "how many times to follow up",
    ],
    "trust": [
        "how to build rapport on sales calls",
        "building trust with strangers",
        "trust signals in sales",
        "social proof in sales",
        "trust before the pitch",
    ],
    "mindset": [
        "sales rejection mindset",
        "fear of selling high ticket",
        "closer identity",
        "handling sales slumps",
        "detachment from outcome",
        "abundance mindset sales",
    ],
    "income": [
        "how much do remote closers make",
        "high ticket closer income 2025",
        "commission only sales income",
        "how to get your first closer client",
        "OTE remote closing",
    ],
    "script": [
        "sales call script high ticket",
        "NEPQ script",
        "spin selling script",
        "not using a script in sales",
        "tonality in sales calls",
    ],
}


def _clean_topic(raw_title: str) -> str:
    """Extract a clean core topic string from a raw video title."""
    # Remove hashtags, emojis, and trailing fluff
    cleaned = re.sub(r"#\S+", "", raw_title)
    cleaned = re.sub(r"[^\x00-\x7F]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Truncate if too long
    if len(cleaned) > 60:
        cleaned = cleaned[:57] + "..."
    return cleaned


def _title_case_topic(topic: str) -> str:
    """Convert a topic string to title-case for use in templates."""
    skip = {"a", "an", "the", "and", "but", "or", "for", "nor", "on", "at", "to", "by", "in", "of", "with"}
    words = topic.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in skip:
            result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)


def _find_niche_subtopics(topic: str) -> list[str]:
    """Return relevant niche subtopics if the topic matches a known category."""
    topic_lower = topic.lower()
    for key, subtopics in NICHE_SUBTOPICS.items():
        if key in topic_lower:
            return subtopics
    return []


def _generate_cluster(cluster_id: int, anchor: dict) -> list[dict]:
    """
    Expand one anchor topic into a full content cluster.
    Returns a list of row dicts for the sheet.
    """
    raw_title = anchor.get("topic", anchor.get("title", ""))
    core_topic = _clean_topic(raw_title)
    topic_tc = _title_case_topic(core_topic)
    suggestions = anchor.get("autocomplete_suggestions", [])
    source_views = anchor.get("source_views", anchor.get("view_count", 0))
    source_channel = anchor.get("source_channel", anchor.get("channel_name", ""))
    outlier = anchor.get("outlier_score", 1.0)

    # Base fields shared by every row in this cluster
    base = {
        "cluster_id": cluster_id,
        "core_topic": core_topic,
        "source_channel": source_channel,
        "source_views": source_views,
    }

    rows = []

    # 1. PILLAR — ultimate guide / full course
    rows.append({
        **base,
        "video_type": "Pillar",
        "angle_lens": "Ultimate Guide",
        "suggested_title": f"The Complete {topic_tc} Guide (Everything You Need to Know)",
        "target_keyword": core_topic.lower(),
        "why_this_works": (
            f"Full-course pillar — highest shareability and watch-time in niche. "
            f"Modeled from {source_channel}'s {source_views:,}-view video on this exact topic ({outlier:.1f}x outlier)."
        ),
        "priority": "High",
    })

    # 2. TWELVE angle spokes
    for lens in ANGLE_LENSES:
        title = lens["template"].format(topic=topic_tc, identity=PRIMARY_IDENTITY)
        keyword = f"{core_topic.lower()} {lens['keyword_suffix']}".strip()
        rows.append({
            **base,
            "video_type": "Spoke — Angle",
            "angle_lens": lens["lens"],
            "suggested_title": title,
            "target_keyword": keyword,
            "why_this_works": lens["why"],
            "priority": lens["priority"],
        })

    # 3. KEYWORD spokes from autocomplete — rotate CTR-optimized templates
    kw_count = 0
    for suggestion in suggestions[:8]:
        if suggestion.lower() == core_topic.lower():
            continue
        suggestion_tc = _title_case_topic(suggestion)
        template = KEYWORD_SPOKE_TEMPLATES[kw_count % len(KEYWORD_SPOKE_TEMPLATES)]
        rows.append({
            **base,
            "video_type": "Spoke — Keyword",
            "angle_lens": "Search Demand",
            "suggested_title": template.format(suggestion_tc=suggestion_tc),
            "target_keyword": suggestion.lower(),
            "why_this_works": (
                f"Exact-match autocomplete keyword — high search intent, already proven demand. "
                f"Targets a specific search query within the '{core_topic.lower()}' cluster."
            ),
            "priority": "Medium",
        })
        kw_count += 1

    # 4. NICHE SUBTOPIC spokes — drill one level deeper on specific scenarios
    subtopics = _find_niche_subtopics(core_topic)
    for sub in subtopics[:6]:
        sub_tc = _title_case_topic(sub)
        rows.append({
            **base,
            "video_type": "Spoke — Subtopic",
            "angle_lens": "Specific Scenario",
            "suggested_title": f"How to Handle \"{sub_tc}\" (Word-for-Word Script)",
            "target_keyword": sub.lower(),
            "why_this_works": (
                "Long-tail keyword targeting a precise objection/scenario. "
                "High buyer intent — viewer is in a live sales situation when they search this. "
                "Cross-links back to the pillar."
            ),
            "priority": "High",
        })

    return rows


def run(
    cfg: Config,
    run_id: str | None = None,
    top_n_clusters: int = 25,
) -> str:
    """
    Expand top N topics into content clusters and write to Google Sheet.
    Returns the sheet URL.
    """
    # Load SEO-enriched data
    if run_id:
        result = load_run_artifact(run_id, "seo_enriched")
    else:
        result = None
        found = get_latest_run_artifact("seo_enriched")
        if found:
            run_id, result = found

    if not result:
        print("[Cluster Expansion] No seo_enriched artifact found. Run Phase 5 first.")
        return ""

    anchors = result.get("anchors", [])
    if not anchors:
        print("[Cluster Expansion] No anchors found.")
        return ""

    # Sort by view count (primary), then composite score as tiebreaker
    anchors.sort(
        key=lambda a: (a.get("source_views", a.get("view_count", 0)), a.get("composite_score", 0)),
        reverse=True,
    )
    top_anchors = anchors[:top_n_clusters]

    print(f"\n[Cluster Expansion] Expanding {len(top_anchors)} core topics into content clusters...")

    all_rows = []
    for i, anchor in enumerate(top_anchors, 1):
        cluster_rows = _generate_cluster(i, anchor)
        all_rows.extend(cluster_rows)
        topic = anchor.get("topic", "")[:50]
        print(f"  [{i}/{len(top_anchors)}] {topic} → {len(cluster_rows)} videos")

    total = len(all_rows)
    print(f"\n  Total video ideas generated: {total}")
    print(f"  ({len(top_anchors)} clusters × ~{total // len(top_anchors)} videos each)")

    # Write to Google Sheet — Content Clusters tab
    print(f"\n  Writing to Google Sheet...")
    gc = get_sheets_client(cfg.client_secrets_path)
    spreadsheet = ensure_sheet(gc, cfg.target_sheet_id)
    write_clusters_tab(spreadsheet, all_rows, overwrite=True)

    url = get_sheet_url(spreadsheet)
    print(f"  Written {total} rows to 'Content Clusters' tab")
    return url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Expand top topics into content clusters")
    parser.add_argument("--run-id", help="Specific run ID to load seo_enriched from")
    parser.add_argument("--top-n", type=int, default=25, help="Number of core topics to expand (default: 25)")
    args = parser.parse_args()
    cfg = load_config()
    url = run(cfg, run_id=args.run_id, top_n_clusters=args.top_n)
    if url:
        print(f"\n  Sheet: {url}")
