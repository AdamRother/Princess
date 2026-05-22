# 02 — Google OAuth setup (Sheets + Drive + Docs)

The pipeline writes topic candidates to a Google Sheet and scripts to a Google Doc in your Drive. Both need OAuth access using your Google account.

**Time:** ~10 minutes. **Cost:** Free.

---

## Part A — Enable the APIs

1. Go to **https://console.cloud.google.com/** and select your project (same one from guide 01)
2. In the left sidebar → **APIs & Services** → **Library**
3. Search for and **Enable** each of these three APIs:
   - **Google Sheets API**
   - **Google Drive API**
   - **Google Docs API**

---

## Part B — Create OAuth credentials

1. In the left sidebar → **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. If prompted to configure the OAuth consent screen:
   - Click **Configure consent screen**
   - Choose **External** → **Create**
   - Fill in App name (anything, e.g. `Sales YT Research`)
   - Fill in your email for User support email and Developer contact
   - Click **Save and Continue** through all steps (no scopes needed here)
   - On the last step, click **Back to Dashboard**
   - Return to **Credentials** → **+ Create Credentials** → **OAuth client ID**
4. Application type: **Desktop app**
5. Name it anything (e.g. `Sales YT Research Desktop`)
6. Click **Create**
7. Click **Download JSON** on the confirmation dialog (or download from the credentials list)
8. Rename the downloaded file to `client_secrets.json`
9. Move it to: `config/client_secrets.json`

---

## Part C — First-time authorization

On the first run that needs Google access (Phase 6/7 or script generation), the pipeline will open a browser window asking you to authorize. Just:
1. Select your Google account
2. Click **Continue** (you may see "unverified app" — that's fine, it's your own OAuth app)
3. Grant access
4. The browser will show "The authentication flow has completed."

Your token is saved to `config/token.json` and reused for all future runs. You won't need to re-authorize unless you delete the token file.

---

## Verify it works

After authorization, run:

```bash
python -c "
from utils.config import load_config
from utils.google_workspace import get_sheets_client
cfg = load_config()
gc = get_sheets_client(cfg.client_secrets_path)
print('OK — authenticated as', gc.auth.service_account_email if hasattr(gc.auth, 'service_account_email') else 'OAuth user')
"
```

---

## Troubleshooting

**"redirect_uri_mismatch"** — Make sure you chose **Desktop app** not **Web application** when creating the OAuth client.

**"Access blocked: app not verified"** — Click "Advanced" → "Go to [app name] (unsafe)". This is expected for personal OAuth apps you haven't submitted for Google review.

**Token expired** — Delete `config/token.json` and re-run. The browser flow will repeat once.
