# 04 — Creating your Google Sheet and Doc folder

You have two options. Most people use Option A.

---

## Option A: Let Claude Code create them (recommended)

Leave both IDs as `"auto"` in `secrets.yaml`:

```yaml
target_sheet_id: "auto"
target_docs_folder_id: "auto"
```

On the first run that needs them, Claude Code will:
1. Create a Sheet titled **"Sales YT — Topic Research"** in your Drive root
2. Create a folder titled **"Sales YT — Scripts"** in your Drive root
3. Write both IDs back into `secrets.yaml` automatically
4. Print the URLs in chat so you can open them

You don't have to do anything except authorize OAuth when prompted.

---

## Option B: Create them yourself (if you want them in a specific folder)

### Create the Sheet
1. Go to **https://sheets.google.com**
2. Click the **blank** template
3. Name it whatever you want (suggestion: `Sales YT — Topic Research`)
4. From the URL, copy the long ID between `/d/` and `/edit`:
   ```
   https://docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit
   ```
5. Paste into `config/secrets.yaml`:
   ```yaml
   target_sheet_id: "1AbCdEf...long-id"
   ```

### Create the Doc folder
1. Go to **https://drive.google.com**
2. **New** → **Folder** → name it (suggestion: `Sales YT — Scripts`)
3. Open the folder
4. From the URL, copy the ID after `/folders/`:
   ```
   https://drive.google.com/drive/folders/THIS_IS_THE_FOLDER_ID
   ```
5. Paste into `config/secrets.yaml`:
   ```yaml
   target_docs_folder_id: "1XyZ...folder-id"
   ```

---

## Sheet structure (auto-populated on first run)

The Sheet has **two tabs** — Topics (main) and Top 10 Competitors (dashboard).

### Tab 1: "Topics"

Claude Code writes these columns:

| # | Column | What it shows |
|---|---|---|
| A | Topic | The topic / idea (cluster anchor) |
| B | Source channel | Name of the competitor channel the breakout came from |
| C | Primary competitor | ✓ if source channel is in your top 10 |
| D | Source tier | peer-lower / peer-upper / aspirational / emerging |
| E | Source video title | The actual high-performing video |
| F | Source URL | Link to the source video — click to watch what we're modeling |
| G | Source views | Total views on the source video |
| H | Views/day | Velocity since publish |
| I | Outlier score | Source video views ÷ channel's median (>3 = breakout) |
| J | Engagement % | (likes + comments) ÷ views |
| K | Search volume est. | 0–100 (Google Trends interest score) |
| L | Trend | Rising / Stable / Declining (last 3 months vs prior 3) |
| M | Keyword richness | # of YouTube autocomplete suggestions |
| N | Suggested title | First generated title variant |
| O | Why this fits | One-line rationale |
| P | Difficulty | 1–5 (production effort) |
| Q | Composite score | Final ranking score (sortable) |
| R | Status | Pending / Selected / Scripted / Published |
| S | Run timestamp | When this row was added |

Default sort is by composite score (column Q) descending. You can filter column C to show only Primary competitor topics.

### Tab 2: "Top 10 Competitors"

Overwritten on each curation refresh. See `references/methodology/competitor-curation.md` for the full schema. At a glance you'll see:
- Ranked top 10 channels with their composite scores
- Their cadence, engagement, and recent trajectory
- Their 3 most recent breakout videos
- A notes column where you can annotate your own observations

---

## Doc naming convention

Scripts written to the folder follow this pattern:
```
[2026-05-20] How I Closed a $47k Deal Without a Discovery Call
```
Date prefix sorts naturally by creation date.
