# 01 — Get a YouTube Data API v3 key

**Time:** ~5 minutes. **Cost:** Free (10,000 units/day free tier is plenty).

---

## Steps

1. Go to **https://console.cloud.google.com/**
2. Click the project dropdown at the top → **New Project**
   - Name it anything (e.g. `sales-yt-research`)
   - Click **Create**
3. Make sure your new project is selected in the dropdown
4. In the left sidebar → **APIs & Services** → **Library**
5. Search for **YouTube Data API v3** → click it → click **Enable**
6. In the left sidebar → **APIs & Services** → **Credentials**
7. Click **+ Create Credentials** → **API key**
8. A key is generated. Copy it now.
9. Click **Edit API key** (pencil icon)
   - Under **API restrictions** → select **Restrict key**
   - Choose **YouTube Data API v3** from the dropdown
   - Click **Save**

---

## Save the key

Paste it into `config/secrets.yaml`:

```yaml
youtube_api_key: "AIza..."
```

---

## Verify it works

```bash
python -c "
from utils.config import load_config
from utils.youtube_api import build_client
cfg = load_config()
yt = build_client(cfg.youtube_api_key)
r = yt.search().list(q='high ticket sales', type='channel', maxResults=1).execute()
print('OK —', r['items'][0]['snippet']['channelTitle'])
"
```

If you see a channel name, the key works.

---

## Quota notes

- Free tier: **10,000 units/day** resets at midnight Pacific
- A `search.list` call costs 100 units; a `videos.list` costs 1 unit
- A full first research run uses ~2,800–3,500 units total
- Subsequent incremental runs use 200–500 units
- The pipeline warns you at 9,000 units and stops at 9,500 to leave buffer
