# Script Writing Pipeline

## Overview

Stage 2 of the pipeline. Triggered when user picks a row number from the Google Sheet.

Flow: pull topic row → fetch reference transcripts → load voice context → print formatted brief for Claude Code chat → Claude writes script + metadata in-chat.

---

## Topic angle variations (12 lenses)

Before writing, identify which angle lens the script uses. Each source topic can produce 8–12 distinct videos. The lens changes who the video targets and what hook it uses — not the underlying topic.

| Lens | Example (topic: objection handling) |
|---|---|
| Skill level | "The 3 Objection Types Every New Closer Needs to Know" |
| Identity | "How Setters Handle Objections Before the Call Starts" |
| Outcome | "The Framework That Doubled My Close Rate" |
| Myth-busting | "Stop Rebutting Objections — Here's What Works" |
| Story-led | "The Call That Taught Me Everything About Price Objections" |
| Comparison | "Scripted vs. Conversational Objection Handling" |
| Behind-the-scenes | "Watch Me Handle 5 Real Objections Live" |
| Failure/mistake | "The 5 Mistakes That Cost Me My First 6 Months" |
| Speed/simplicity | "Handle Any Objection in 30 Seconds With This Formula" |
| Contrarian timing | "When NOT to Handle an Objection" |
| Psychology/root cause | "What 'I Need to Think About It' Actually Means" |
| System/framework | "My Full Objection Handling System: Walkthrough" |

**For channels under 10K subs:** prioritize myth-busting, story-led, and psychology lenses. These build trust fastest. Ultimate guides and full courses are the highest-outlier format once you have some audience.

---

## Reference transcript fetching

Command used for each reference URL:
```
yt-dlp --write-auto-sub --sub-lang en --sub-format vtt --skip-download
        --print "%(title)s\t%(uploader)s" --output {tmpdir}/%(id)s {url}
```

Parse the VTT output: strip timestamps, deduplicate lines, join into plain text.
Store to output/raw/transcripts/{video_id}.txt for caching.

---

## Script structure (what Claude is instructed to write)

### Macro structure: PASTOR arc
- **P** — Problem: name the specific familiar pain
- **A** — Amplify: escalate consequences of not solving it
- **S** — Story/Solution: specific case (your story or client's)
- **T** — Transformation: what their life looks like solved
- **O** — Offer: the framework, method, or process
- **R** — Response: soft CTA (subscribe, next video, comment)

### Micro structure: 7-part retention framework

**Part 1 — Hook (0–8 seconds)**
Pattern interrupt or bold claim. No "welcome back." No intro. Lead with something that breaks scroll.

**Part 2 — Anti-hook (8–15 seconds)**
Build trust by acknowledging skepticism. "You've probably heard [X] — I thought so too until..."

**Part 3 — Promise (15–30 seconds)**
Specific transformation. Not vague tips — a concrete, measurable outcome.

**Part 4 — Preview + open loops (30–60 seconds)**
Name the 3–5 things you'll cover. Plant 2–3 open loops that will be closed throughout.

**Part 5 — Core content with pattern interrupts (60–80% of runtime)**
Engagement shift every 45–90 seconds:
- Story pivot, stat reveal, viewer challenge, perspective flip, failure pivot, callback

**Part 6 — Value bomb (at the 60–70% mark)**
Strongest insight placed here — not at the front, not at the end.

**Part 7 — Soft CTA (final 10%)**
Tease the next relevant video. Never beg for subscribe.

### Open loop requirements
- Minimum 2 open loops planted in the first 90 seconds
- Minimum 1 at the midpoint
- All loops must close before the CTA

---

## What's proven to work in this niche (from scraped data)

| Format | Example | Why it works |
|---|---|---|
| Full course / ultimate guide | "How to Sell Anything (Full Sales Course)" — 108K, 56x | High intent search traffic, long watch time |
| Live demonstration | "How to Book A Sales Meeting in 1 Hour (LIVE)" — 38K, 13x | Trust + entertainment, proof over claims |
| Myth-bust | "STOP Using Sales Scripts. Use This Instead" — 18K, 22x | Contrarian hook, curiosity trigger |
| Authority proximity | "I Was Jeremy Miner's #2 Closer" — 19K, 24x | Borrowed credibility, story-led |
| Book/resource synthesis | "I Read 50 Sales Books: The 5 That Made Me GREAT" — 23K, 8x | Research-backed trust |
| Specific skill breakdown | "How To Build Trust With A Complete Stranger" — 51K, 8x | Targets exact problem keyword |

---

## YouTube SEO requirements for every script

### Title (5 variants)
- 50–60 characters, 70 max
- Primary keyword in first 4–5 words
- One CTR pattern per variant: number-led, myth-bust, identity+outcome, curiosity gap, or transformation
- Thumbnail and title must carry different information — never repeat

### Description
- First 150 characters: primary keyword within first 25 words (this is the search snippet)
- 250–350 words total
- Chapter timestamps matching script sections
- 3–5 related keywords naturally worked in
- CTA in the middle and at the end
- 3–5 hashtags at the bottom

### Tags (12 total)
- First tag = exact primary keyword
- 3–4 keyword variations / long-tail
- 2–3 broader category terms
- 1–2 channel brand tags

### Thumbnail brief
- Shot type, facial expression, bold text overlay (3–4 words, mobile-readable)
- High contrast, expressive face, max 3 visual elements
- Must carry different information than the title

### Chapters (for videos 15+ minutes)
- Start at 0:00 with a descriptive name
- Use natural search language in chapter titles — each is a ranking opportunity

---

## Metadata output format

After the script, output:

```
---METADATA---

TITLES (5 variants):
1. [title — primary keyword first 5 words]
2. [title — number-led]
3. [title — myth-bust or contrarian]
4. [title — identity + outcome]
5. [title — curiosity gap]

DESCRIPTION:
[250-350 words: keyword in first 25 words, chapter timestamps, 2 CTAs, hashtags]

TAGS:
[12 tags: exact match first, then variations, then broad category]

THUMBNAIL BRIEF:
[shot, expression, 3-4 word text overlay, background, color, emotion conveyed]

ANGLE USED: [which of the 12 lenses]
FOLLOW-UP ANGLES: [2-3 companion video angles on this same topic]
```
