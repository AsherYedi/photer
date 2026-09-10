# PhotoSort

**Find your best shots faster.**

PhotoSort helps photographers sort through thousands of event photos by
technical quality. Connect a Google Drive folder, and PhotoSort scores
every photo 0–100 on sharpness, brightness, exposure, and resolution —
then sorts them into **GOOD**, **REVIEW**, and **POOR**, with the reason
behind every score.

This first version uses classic image processing (OpenCV) only — no AI
model. The codebase is intentionally modular so an AI-based scoring pass
can be added later without a rewrite.

## How it works

```
Google Drive → pick a folder → OpenCV analysis → quality score → GOOD / REVIEW / POOR
```

Each photo is scored on:

| Factor | Method |
|---|---|
| Sharpness | Variance of the Laplacian (blur detection) |
| Brightness | Mean pixel intensity |
| Exposure | % of pixels clipped into pure shadow / highlight |
| Resolution | Megapixels |

Photos are only held in memory long enough to analyze them — PhotoSort
never writes your photos to disk on the server.

## Project structure

```
PhotoSort/
├── app.py            # Streamlit UI: connect, select folder, progress, results
├── analyzer.py        # OpenCV analysis: sharpness, brightness, exposure, resolution
├── scoring.py          # Turns metrics into a 0-100 score + GOOD/REVIEW/POOR + reasons
├── drive.py            # Google OAuth 2.0 + Drive API
├── requirements.txt
├── README.md
├── .gitignore
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

You can try the analyzer immediately, before setting up OAuth, using the
**"Local test"** tab in the app to upload a handful of photos directly:

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
   (create this file — it's already git-ignored):

   ```toml
   [google_oauth]
   client_id = "xxxxxxxx.apps.googleusercontent.com"
   client_secret = "xxxxxxxx"
   redirect_uri = "http://localhost:8501"
   ```

   Never commit this file or paste real credentials into the repo.

6. Restart the app. The **"Connect Google Drive"** button on the
   "Google Drive" tab will now work.

### 4. Deploy to Streamlit Cloud

1. Push this repo to GitHub (secrets stay out of the repo thanks to
   `.gitignore`).
2. On [share.streamlit.io](https://share.streamlit.io), create a new app
   pointing at `app.py`.
3. In the app's **Settings → Secrets**, paste the same `[google_oauth]`
   block as above, but set `redirect_uri` to your deployed app's URL
   (e.g. `https://your-app.streamlit.app`).
4. Go back to Google Cloud Console and add that same URL as an
   **Authorized redirect URI** on the OAuth client.

## MVP scope

**In scope:** Google Drive → OpenCV analysis → scoring → results, using
Google OAuth as the only sign-in method.

**Deliberately out of scope for this version** (candidates for a later
release): a custom AI model, YOLO/object detection, facial recognition,
non-Google login, a full database, payments, a mobile app.

## Roadmap

The current scoring is rule-based and fully explainable. A natural next
step is an AI-assisted pass (e.g. aesthetic/composition scoring, face
detection to catch closed eyes, duplicate/near-duplicate grouping) layered
on top of — not replacing — the existing technical-quality score.
