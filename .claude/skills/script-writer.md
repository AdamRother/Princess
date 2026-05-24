# Skill: /script-writer

Writes a full long-form YouTube script for Princess Bonhomme (@BehindtheSale) using her Pain Discovery Framework, real stories, and exact voice.

## When to invoke

User says `/script-writer`, "write a script", "script row X", replies with a tab + row number after `/topic-research`, or gives a topic directly.

---

## Steps — run in order

### 1. Parse the topic

**From a sheet row:** Identify tab and row number ("Trending row 5" → Trending Now tab, row 5). Pull from the Google Sheet (`TARGET_SHEET_ID`):
- **Idea** (col B) — suggested title
- **Proof** (col C) — source video URL
- **Why it works** (col E) — performance analysis
- **Keywords** (col F) — autocomplete keywords
- The 10 angle variants beneath it

Ask: "Which angle are you going with, or should I pick the strongest one?"

**From a direct topic:** Use the topic as given. Ask for a preferred angle if not specified.

---

### 2. Research and model the source transcript (PRIMARY structural driver)

**The scraped transcript IS the structural blueprint.** Do not use a generic template — model the actual video.

#### Step A — Read the source transcript

Each research run saves a transcript per candidate video at `output/raw/transcripts/{video_id}.txt` — where `{video_id}` is the `v=` parameter from the source URL (e.g. URL `?v=DrE9HdnMDJs` → file `output/raw/transcripts/DrE9HdnMDJs.txt`).

**Read this file before writing anything.** Then extract:

| Element | What to identify |
|---------|-----------------|
| **Hook type** | How does the video open — social proof clips, direct confrontation, scenario drop, result-first? |
| **Frame-setting** | How does the speaker address the audience in the first 60 sec? What belief do they challenge? |
| **Teaching structure** | Does it use a named framework with numbered steps? Micro-skills list? Live demo? Story sequence? |
| **Pacing pattern** | Short punchy sections or long builds? Where do they pause and let things land? |
| **Live demonstration** | Does the source video demo something in real-time with a person? If yes, build an equivalent in Princess's script. |
| **Core insight position** | Where in the video does the single most important idea land — early, middle, or late? |
| **Close structure** | Does it end with a personal story, an identity reframe, a challenge, or a direct CTA? |

Model the script on THIS structure, adapted to Princess's voice and frameworks. The source video proved this structure works with this audience — don't discard it for a generic template.

#### Step B — If no local transcript exists

Try yt-dlp as fallback:
```
yt-dlp --write-auto-sub --skip-download --sub-lang en -o "output/transcripts/%(id)s" <url>
```
If still unavailable, use the 7-part structure in Step 4 below as fallback only.

The `output/current_script.md` file is the output location for the finished script — it is not a structural template. Only use its structure as reference when no transcript was available for the source video.

#### Step C — Supplemental research

- Use YouTube Data API to pull the video's full description — often contains framework names and key language.
- If the topic maps to one of her named frameworks (Pain Discovery Framework, Motivation Matrix, The Unsell), pull those details from `context/voice-and-tone.md` — these replace or supplement what the source video teaches.

---

### 3. Load ALL context files (non-negotiable — read every one before writing)

- `context/voice-and-tone.md` — her framework, phrases, analogies, tone rules
- `context/stories-bank.md` — her real stories. **Never invent a story she hasn't told.**
- `context/audience-persona.md` — who she's talking to, what they believe wrong
- `context/do-and-dont.md` — hard rules that override everything else
- `context/opening-styles.md` — her actual opening patterns

If any file is empty, flag it: "Your [file] is empty — script will be generic until you fill it in."

---

### 4. Write the script

**Target length:** 30 minutes default (≈4,500 words). Range: 10–60 min.

**Primary structure source: the scraped transcript (Step 2A).** Identify the source video's actual structure — how it opens, what teaching method it uses, where the core insight lands, how it closes — and mirror that. Do not default to the 7-part template below when a transcript exists.

**7-part structure below = fallback only.** Use it when no transcript was available for the source video.

---

#### 7-PART FALLBACK STRUCTURE (use only when no source transcript is available)

**PART 1 — HOOK (0–8 sec)**

The first words are content. Never a greeting, never "Welcome back," never her name.

Choose the opening style from `context/opening-styles.md` that fits the topic's emotional register:
- **Emotional anchor** — drop into a specific, charged moment (a line someone said, a thing that happened). Let tension sit. Best for mindset/identity/turning-point content.
- **Name the lie first** — state the wrong belief flat, then pull the rug out. Best for contrarian/framework content.
- **Result-first reveal** — lead with the outcome, then undercut the expected story. Best for income proof content.
- **Direct confrontation** — name what they're doing wrong, warm but zero softening. Best for "why you're failing" content.
- **Scenario** — put them in a moment they've lived. Best for tactical/how-to content.

The hook is 2–4 short sentences max. Build the moment, let it land, pivot. No warm-up.

---

**PART 2 — ANTI-HOOK (8–15 sec)**

Immediately undercut what the viewer expects. Tell them what this is NOT first.

Always frame against "word tracks," scripts, objection handling tactics, or hustle-harder thinking — whichever fits the topic. Then state what this IS, anchored in a specific credibility number ($3.4M, nursing student origin, $475 month, students doing $150k+/month collectively).

Pattern:
> "This is not [what they expect]. My friend, [call out the wrong belief]. What I AM going to share is [the real thing], and I built it after going from [specific before-state] to [specific after-state]."

---

**PART 3 — PROMISE (15–30 sec)**

One clear statement. What will they walk away with that they don't have now? Specific outcome, not vague. 2–3 sentences max.

End with an energizing phrase that signals we're going in: "Let's get into it," "Let's go," "Here's how this works."

---

**PART 4 — PREVIEW + OPEN LOOPS (30–60 sec)**

List 3–4 bullets on what the video covers. Each one is an open loop — a promise you will close inside the core content. Label them explicitly in the script draft as `[open loop 1]`, `[open loop 2]`, etc. so they're easy to track.

At least one open loop should be a story ("There's a specific call I'll tell you about..."). This is the highest-retention device — tease it here, pay it off in core content.

Format:
> "Here's what we're covering: First — [point 1]. [open loop 1] Second — [point 2]. Third — [story tease]. [open loop 2] Fourth — [point 3, usually the value bomb setup]. [open loop 3]"

End with a single short momentum phrase: "Let's go." / "Let's start at the beginning." / "Here's the first thing."

---

**PART 5 — CORE CONTENT (the body)**

3–5 named sections. Each section follows this internal structure:

1. **The concept** — state it flat, no hedging. Short declarative sentences. "Most salespeople do X. Here's why that's wrong."
2. **The story or example** — pull from `context/stories-bank.md`. Use her real stories. Do not invent. If no exact story fits, use the closest one and adapt the frame — never fabricate a new experience.
3. **The framework application** — connect the concept to her named frameworks from `context/voice-and-tone.md`. When the topic is about discovery, discovery questioning, or objection elimination: use the Pain Discovery Framework (Phase 1 / Phase 2 / Phase 3, Truth #1, Truth #2). When the topic is about buyer types: use the Motivation Matrix. When the topic is about handling hesitation at close: use The Unsell.
4. **Close the open loop** — if a section closes a loop from the preview, mark it `[Close loop X]` in the draft.
5. **The "right?" pull-through** — end sections with a rhetorical statement-question to keep the viewer in sync.

**Wrong belief correction (replaces "objection handling"):** At least one section should directly call out a wrong belief the audience holds (from `context/audience-persona.md`). Use "delete that belief immediately" or "make it make sense" framing. This is NOT objection handling — it's the belief correction that eliminates the need for objection handling later.

**The VALUE BOMB** lands at the 65% mark — the single most important insight. It should reframe something the viewer thought they understood. Introduce it with a pattern interrupt: `*[pause]*`, `[pattern interrupt — look directly at camera]`, or a rhythm break. Then say it twice — once plain, once expanded.

---

**PART 6 — VALUE BOMB RECAP + TRANSITION**

Zoom out. Name the old structure vs. the new structure explicitly:

> "You came into this video thinking [wrong belief they had]. The actual [truth] is [reframe]."

Then state the shift as a before/after:

> "Old structure: [what they were doing]. My structure: [what actually works]."

Close with identity language: this is what six-figure closers do. This is available to them right now, on their next call. Short, declarative. No fluff.

---

**PART 7 — SOFT CTA**

**Never desperate. Never "please like and subscribe."**

Structure:
1. **The bridge story** — one of her real stories (parents' attic, $475 month, nursing student, real estate agents) as a 2–3 sentence reminder that she's been where they are. This is the emotional landing before the ask.
2. **The identity close** — who they are becoming, not just what they should do. "If you're sitting where I was sitting..." End on who they're becoming, not what they need to click.
3. **The service-framed subscribe** — tease the next video as the natural next step in learning. "If you want to see this in action..." Subscribe is framed as serving their growth, not her metrics.
4. **The comment prompt** — one specific question tied to the video's content. Not "what did you think?" Give them a real frame: "Drop a comment: which phase is your biggest gap — START, IMPROVE, or CLOSE?" She reads every one.

---

#### VOICE RULES (apply throughout — from `context/do-and-dont.md`)

**Always:**
- Pull only from her real stories (stories-bank.md) — never invent experiences
- Use "you" constantly — speak directly to the viewer, not about them
- Include specific numbers: dollar amounts, timeframes, percentages
- Use her signature phrases naturally — "make it make sense," "my friend," "selling is serving," "say the thing that needs to be said," "delete that belief immediately," "praise God" (when authentic)
- End with identity — who they're becoming, not just what they're doing
- Conviction over polish — every sentence should sound like she believes it

**Never:**
- Start with a greeting, "Welcome back," or her name
- Use "tips and tricks," "hustle harder," "work more"
- Script objection handling tactics — her brand is anti-objection-handling; she eliminates objections through discovery
- Write word-for-word prospect scripts — frameworks only, never lines to parrot
- Hedge ("it depends," "some people say," "you might find")
- Make the CTA desperate

---

#### SCRIPT FORMATTING

Use these markers in the draft so it's easy to track structure:

- `*[pause]*` — deliberate beat before a key point
- `*[look directly at camera]*` — pattern interrupt
- `**bold text**` — emphasis for delivery
- `[open loop X]` / `[Close loop X]` — loop tracking
- `[VALUE BOMB]` — at the 65% mark
- Section headers in `### Section Name` format

---

### 5. SEO Metadata (append at end of script)

**Titles (5 variants):**
- Lead with the benefit or the hook, not the framework name
- Mix formats: result-led, question, number-led, contrarian
- 50–65 characters each
- At least one title should be something the audience Googles (search-intent aligned)

**Description:**
- First 150 chars: hook that stands alone (appears before "Show more")
- Chapter timestamps matching actual script sections
- 1 paragraph per section summarizing the teaching
- End with subscribe CTA + link

**Tags:** 12 total — mix of exact-match phrases, broad category terms, and her name/channel.

**Thumbnail brief:** Main text overlay (3–5 words max), visual concept, expression/emotion. Thumbnail must carry different information than the title — it's a second hook, not a repeat.

**Follow-up angles:** 2 specific video ideas that naturally extend this content.

---

### 6. Write to Google Doc

Create a new Google Doc in `TARGET_DOCS_FOLDER_ID`:
- Name: `[YYYY-MM-DD] {Short Title}` (e.g. `2026-05-21 Complete 2026 Guide`)
- Full script with `##` section headings
- SEO metadata block at the bottom under `## YouTube Metadata`

Return the Doc URL to the user.

---

## Quality check before submitting

Before returning the URL, verify:
- [ ] **If transcript existed:** the script structure mirrors the source video's actual structure (hook type, teaching method, live demo if present, insight position, close style) — not a generic 7-part template
- [ ] **If no transcript:** 7-part fallback structure is used and labeled as such in the script header
- [ ] No placeholders left in the script (`[YOUR STORY]`, `[INSERT]`, `[FILL IN]`)
- [ ] At least 2 real stories from stories-bank.md are woven in
- [ ] All open loops from Part 4 are closed in Part 5
- [ ] "Objection handling" does not appear anywhere as a tactic to teach viewers
- [ ] The value bomb lands at approximately the 65% word count mark
- [ ] The CTA does not contain "please like," "if you don't mind," or any begging language
- [ ] Specific numbers appear at least 4 times (dollar amounts, percentages, timeframes)
- [ ] Her signature phrases appear naturally at least 3 times
