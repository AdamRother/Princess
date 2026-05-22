"""
Stage 2 — Script brief generator.

Pulls a topic row from the Google Sheet, fetches reference transcripts,
and loads voice context — then prints everything formatted for Claude Code
to use directly in chat to write the full script and metadata.

Usage:
  python script_writer.py --row 3
  python script_writer.py --row 3 --minutes 45
  python script_writer.py --row 3 --sheet-id <override>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from utils.config import load_config
from utils.cache import load_transcript, write_transcript
from utils.seo import youtube_autocomplete

BASE_DIR = Path(__file__).parent
CONTEXT_DIR = BASE_DIR / "context"


def _extract_video_id(url: str) -> str | None:
    for pattern in [
        r"v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"embed/([A-Za-z0-9_-]{11})",
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def _fetch_transcript(url: str) -> dict | None:
    video_id = _extract_video_id(url)
    if not video_id:
        return None

    cached = load_transcript(video_id)
    if cached:
        return {"id": video_id, "title": "", "channel": "", "text": cached}

    print(f"    Fetching transcript: {video_id}...", end=" ", flush=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--write-auto-sub", "--sub-lang", "en",
                    "--sub-format", "vtt",
                    "--skip-download",
                    "--quiet", "--no-warnings",
                    "--print", "%(title)s\t%(uploader)s",
                    "--output", f"{tmpdir}/%(id)s",
                    url,
                ],
                capture_output=True, text=True, timeout=60,
            )
            title, channel = "", ""
            if result.stdout.strip():
                parts = result.stdout.strip().split("\t", 1)
                title = parts[0] if parts else ""
                channel = parts[1] if len(parts) > 1 else ""

            vtt_files = list(Path(tmpdir).glob(f"{video_id}*.vtt"))
            if not vtt_files:
                print("no captions")
                return None

            plain = _parse_vtt(vtt_files[0].read_text(encoding="utf-8"))
            if len(plain) < 200:
                print("too short")
                return None

            write_transcript(video_id, plain)
            print(f"{len(plain.split()):,} words")
            return {"id": video_id, "title": title, "channel": channel, "text": plain}

        except subprocess.TimeoutExpired:
            print("timeout")
            return None
        except Exception as e:
            print(f"error: {e}")
            return None


def _parse_vtt(vtt_text: str) -> str:
    seen, result = set(), []
    for line in vtt_text.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line or line.startswith("NOTE"):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return " ".join(result)


def _load_context() -> dict[str, str]:
    files = {
        "voice_and_tone": "voice-and-tone.md",
        "stories_bank": "stories-bank.md",
        "audience_persona": "audience-persona.md",
        "do_and_dont": "do-and-dont.md",
        "opening_styles": "opening-styles.md",
    }
    ctx = {}
    for key, filename in files.items():
        path = CONTEXT_DIR / filename
        text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
        if not text:
            print(f"  WARNING: context/{filename} is empty — fill it in for better scripts")
        ctx[key] = text
    return ctx


def main():
    parser = argparse.ArgumentParser(description="Stage 2: Prepare script brief for Claude Code")
    parser.add_argument("--row", type=int, required=True, help="Row number from Topics tab (1 = first data row)")
    parser.add_argument("--minutes", type=int, default=30, help="Target script length in minutes (default: 30)")
    parser.add_argument("--sheet-id", default=None, help="Override Google Sheet ID")
    args = parser.parse_args()

    print("=" * 60)
    print("  Sales YT — Script Brief Generator")
    print("=" * 60)

    try:
        cfg = load_config()
    except Exception as e:
        print(f"\nConfig error: {e}")
        sys.exit(1)

    sheet_id = args.sheet_id or cfg.target_sheet_id

    # ── Pull row from Sheet ────────────────────────────────────
    print(f"\n[1/3] Fetching row {args.row} from Google Sheet...")
    from utils.google_workspace import get_sheets_client, ensure_sheet
    gc = get_sheets_client(cfg.client_secrets_path)
    spreadsheet = ensure_sheet(gc, sheet_id)
    ws = spreadsheet.worksheet("Topics")
    headers = ws.row_values(1)
    row_data = ws.row_values(args.row + 1)
    row = dict(zip(headers, row_data))

    topic          = row.get("Topic", "")
    source_url     = row.get("Source URL", "")
    source_title   = row.get("Source video title", "")
    source_channel = row.get("Source channel", "")
    source_views   = row.get("Source views", "0")
    outlier_score  = row.get("Outlier score", "")
    trend          = row.get("Trend", "")
    search_vol     = row.get("Search volume est.", "")
    why_fits       = row.get("Why this fits", "")
    suggestions_raw = row.get("Keyword richness", "")

    print(f"  Topic: {topic}")
    print(f"  Source: {source_channel} — {source_views} views ({outlier_score}x)")

    # ── Fetch reference transcripts ────────────────────────────
    print(f"\n[2/3] Fetching reference transcripts...")
    n_refs = cfg.settings.get("script", {}).get("reference_videos_per_topic", 5)
    ref_urls = [source_url] if source_url else []
    suggestions = youtube_autocomplete(topic)
    for s in suggestions[:4]:
        ref_urls.append(f"ytsearch3:{s}")
        if len(ref_urls) >= n_refs:
            break

    transcripts = []
    for url in ref_urls:
        t = _fetch_transcript(url)
        if t:
            transcripts.append(t)
        if len(transcripts) >= n_refs:
            break
    print(f"  Got {len(transcripts)} transcripts")

    # ── Load voice context ─────────────────────────────────────
    print(f"\n[3/3] Loading voice context...")
    ctx = _load_context()

    # ── Print brief for Claude Code ────────────────────────────
    target_words = args.minutes * 150
    transcripts_block = ""
    for i, t in enumerate(transcripts, 1):
        label = f"{t.get('title', '')} — {t.get('channel', '')}" if t.get("title") else f"Reference {i}"
        transcripts_block += f"\n### Reference {i}: {label}\n"
        transcripts_block += t["text"][:3000]
        transcripts_block += "\n"

    print("\n" + "=" * 60)
    print("  SCRIPT BRIEF — paste below into Claude Code chat")
    print("=" * 60)

    brief = f"""
---SCRIPT BRIEF---

**Topic:** {topic}
**Source video:** [{source_title}]({source_url})
**Source channel:** {source_channel} | {source_views} views | {outlier_score}x channel median
**Trend:** {trend} | Search volume: {search_vol}/100
**Why this fits:** {why_fits}
**Target length:** {args.minutes} minutes (~{target_words:,} words at 150 wpm)

---VOICE CONTEXT---

**Voice and tone:**
{ctx['voice_and_tone']}

**Stories bank:**
{ctx['stories_bank']}

**Audience persona:**
{ctx['audience_persona']}

**Do and don't:**
{ctx['do_and_dont']}

**Opening styles:**
{ctx['opening_styles']}

---REFERENCE TRANSCRIPTS---
{transcripts_block}
---END BRIEF---

Now write the full script. Use the voice context above — tone, stories, audience language.
Target {args.minutes} minutes (~{target_words:,} words).

**SCRIPT STRUCTURE (follow exactly):**

**Part 1 — HOOK (0–8 seconds)**
Pattern interrupt or bold claim. No "welcome back", no intro. Break scroll immediately.

**Part 2 — ANTI-HOOK (8–15 seconds)**
Acknowledge skepticism. "You've probably heard X — I thought so too until..."

**Part 3 — PROMISE (15–30 seconds)**
Specific concrete transformation. Not vague tips — exact measurable outcome.

**Part 4 — PREVIEW + OPEN LOOPS (30–60 seconds)**
Name 3–5 things covered. Plant 2–3 open loops (unresolved stories/questions to close later).

**Part 5 — CORE CONTENT (60–80% of runtime)**
Deliver the substance. Engagement shift every 45–90 seconds — use: story pivot, stat drop, viewer challenge, perspective flip ("from the prospect's side..."), failure pivot, or callback.
Place a VALUE BOMB at the 60–70% mark: single strongest insight where retention dips.

**Part 6 — OBJECTION HANDLING (2–3 min)**
Address the "yeah but" the viewer is thinking right now.

**Part 7 — SOFT CTA (final 60 seconds)**
Never beg for subscribe. Tease the next video, connect it to what was just learned.
Mark [PAUSE] for natural beats. Mark [B-ROLL: description] where visuals would help.

---METADATA---

After the script, generate:

**TITLES — 5 variants** (50–60 chars each, primary keyword in first 5 words):
- Variant 1: Number-led ("5 Reasons...", "3 Steps...")
- Variant 2: Myth-bust ("Stop Doing X — Here's What Works")
- Variant 3: Identity + outcome ("High-Ticket Closers: How to Hit $30K/Month")
- Variant 4: Curiosity gap ("The One Thing Costing You $20K Months")
- Variant 5: Transformation ("I Changed This and Tripled My Close Rate")
Note: thumbnail and title carry DIFFERENT information — never repeat.

**DESCRIPTION** (250–350 words):
- First 150 chars: primary keyword within first 25 words (this is the search snippet shown in results)
- Chapter timestamps matching the script sections
- Keyword used 2–4 times naturally
- CTA at the middle and end
- 3–5 hashtags at the bottom

**TAGS** (12 tags):
- Tag 1: exact primary keyword
- Tags 2–5: long-tail variations
- Tags 6–9: broader category terms
- Tags 10–12: channel/niche brand tags

**THUMBNAIL BRIEF** (1 paragraph):
Shot type, facial expression, 3–4 word bold text overlay (mobile-readable), background, color palette, emotion conveyed. Must show different information than the title.

**ANGLE USED:** [which of the 12 lenses: skill-level / identity / outcome / myth-busting / story-led / comparison / behind-the-scenes / failure-mistake / speed-simplicity / contrarian-timing / psychology-root-cause / system-framework]

**FOLLOW-UP ANGLES:** [2–3 companion video ideas on this same topic using different lenses — gives the channel a content series from one source video]
"""

    print(brief)
    print("=" * 60)
    print(f"\nCopy the brief above and paste it here in Claude Code chat.")
    print(f"Claude Code will write the full {args.minutes}-min script directly.\n")


if __name__ == "__main__":
    main()
