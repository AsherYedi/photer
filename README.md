# PhotoSort

**Find your best shots faster.**

PhotoSort helps photographers sort through thousands of event photos by
technical quality. Paste a Google Drive folder link, connect your Google
account, and PhotoSort scores every photo 0–100 on sharpness, brightness,
exposure, and resolution — then sorts them into **GOOD**, **REVIEW**, and
**POOR**, with the reason behind every score and a one-click link back to
the original file in Drive.

This version uses classic image processing (OpenCV) only — no AI model,
no YOLO, no database. The codebase stays modular so an AI-based scoring
pass can be added later without a rewrite.

## Flow

```
Landing → paste Google Drive folder link → connect with Google → analyze → results
```

Each photo is scored on:

| Factor | Method |
|---|---|
| Sharpness | Variance of the Laplacian (blur detection) |
| Brightness | Mean pixel intensity |
| Exposure | % of pixels clipped into pure shadow / highlight |
| Resolution | Megapixels |

Results show: **GOOD / REVIEW / POOR** label, quality score, a filterable
photo grid, a per-photo detail panel with the full breakdown, and an
**Open in Google Drive** link on every photo.

Photos are only held in memory long enough to analyze them — PhotoSort
never writes your photos to disk on the server.

## Project structure

```
PhotoSort/
├── app.py                    # Streamlit UI: landing, paste-link flow, results
├── analyzer.py                # OpenCV analysis: sharpness, brightness, exposure, resolution
├── scoring.py                  # Turns metrics into a 0-100 score + GOOD/REVIEW/POOR + reasons
├── drive.py                    # Google OAuth 2.0 + Drive API (folder-link parsing, file listing/download)
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml            # Dark theme tokens (safe to commit — no secrets)
└── assets/
```

## Setup

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run it locally without Google Drive first

Open the **"Try it without Google Drive"** panel in the app to upload a
handful of photos directly and see the analyzer/scoring in action before
setting up OAuth:

```bash
streamlit run app.py
```

### 3. Set up Google Drive access

1. In [Google Cloud Console](https://console.cloud.google.com/), create
   (or pick) a project.
2. Enable the **Google Drive API**.
3. Configure the OAuth consent screen (External is fine for testing;
   add yourself as a test user).
4. Create an **OAuth client ID** of type **Web application**.
   - Add an **Authorized redirect URI** matching where you'll run the
     app, e.g. `http://localhost:8501` for local dev.
5. Copy the client ID and client secret into `.streamlit/secrets.toml`
   (create this file — it's already git-ignored, so real credentials
   never reach the repo):

   ```toml
   [google_oauth]
   client_id = "xxxxxxxx.apps.googleusercontent.com"
   client_secret = "xxxxxxxx"
   redirect_uri = "http://localhost:8501"
   ```

6. Restart the app. Paste a Drive folder link and the **"Continue with
   Google"** button will now work.

Note: PhotoSort only requests the read-only Drive scope
(`drive.readonly`) — it can't edit, delete, or upload anything in your
Drive.

### 4. Deploy to Streamlit Cloud

1. Push this repo to GitHub (`.streamlit/secrets.toml` stays out of the
   repo thanks to `.gitignore`; `.streamlit/config.toml` is safe to
   commit since it only holds theme colors).
2. On [share.streamlit.io](https://share.streamlit.io), create a new app
   pointing at `app.py`.
3. In the app's **Settings → Secrets**, paste the same `[google_oauth]`
   block as above, but set `redirect_uri` to your deployed app's URL
   (e.g. `https://your-app.streamlit.app`).
4. Go back to Google Cloud Console and add that same URL as an
   **Authorized redirect URI** on the OAuth client.
5. Reboot the app from Streamlit Cloud after saving secrets.

## How sign-in works

Clicking **"Continue with Google"** sends the folder ID you pasted along
as the OAuth `state` parameter, so when Google redirects back with an
authorization code, PhotoSort picks up exactly where you left off and
starts analyzing automatically — no need to re-paste the link after
signing in.

## MVP scope

**In scope:** paste a Drive folder link → Google OAuth → OpenCV analysis
→ scoring → results, using Google as the only sign-in method.

**Deliberately out of scope for this version:** a custom AI model,
YOLO/object detection, facial recognition, non-Google login, a database,
payments, a mobile app.

## Roadmap

The current scoring is rule-based and fully explainable. A natural next
step is an AI-assisted pass (e.g. aesthetic/composition scoring, face
detection to catch closed eyes, duplicate/near-duplicate grouping) layered
on top of — not replacing — the existing technical-quality score.
