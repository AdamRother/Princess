# 03 — Find Your YouTube Channel ID

Your channel ID is a unique string that looks like `UCxxxxxxxxxxxxxxxxxxxxxxxx`. It's distinct from your channel handle (`@yourhandle`) and your channel name. The pipeline uses it to filter your own channel out of competitor lists and to calibrate tier thresholds.

---

## Method 1 — Read it from your channel URL

1. Open YouTube and sign in.
2. Click your profile icon → **Your channel**.
3. Look at the URL in the address bar.

If you have a custom URL it might look like:
```
https://www.youtube.com/@yourhandle
```

In that case, continue to Method 2. If the URL contains `/channel/` directly:
```
https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxxxx
```
Copy everything after `/channel/` — that's your channel ID.

---

## Method 2 — YouTube Studio (most reliable)

1. Go to [studio.youtube.com](https://studio.youtube.com).
2. Click **Settings** (gear icon, bottom left).
3. Click **Channel** → **Advanced settings**.
4. Your **Channel ID** is displayed under "Channel ID" — it starts with `UC`.

Copy it from there.

---

## Method 3 — YouTube Data API (if you have your API key)

If you've already set up your `YOUTUBE_API_KEY`, run this one-liner from the project root with your venv active:

```bash
source .venv/bin/activate
python3 -c "
import os, requests
key = open('.env').read()
key = [l.split('=',1)[1].strip() for l in key.splitlines() if l.startswith('YOUTUBE_API_KEY')][0]
handle = input('Enter your handle (e.g. @yourhandle): ').lstrip('@')
r = requests.get('https://www.googleapis.com/youtube/v3/channels',
    params={'part':'id','forHandle':handle,'key':key})
print(r.json()['items'][0]['id'])
"
```

---

## Where to put the value

Once you have your channel ID, paste it into `.env`:

```
YOUR_CHANNEL_ID=UCxxxxxxxxxxxxxxxxxxxxxxxx
```

If the `.env` doesn't have a `YOUR_CHANNEL_ID` line yet, add it on a new line.

---

## Verification

The pipeline uses this ID to:
- Exclude your own channel from competitor discovery results
- Set your subscriber count as the baseline for tier calibration

If you set it incorrectly, you'll see your own channel appearing in the competitor list. Fix it in `.env` and re-run.
