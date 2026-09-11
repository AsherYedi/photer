"""PhotoSort — Find your best shots faster.

Flow: Landing -> paste a Google Drive folder link -> connect with Google
-> analyze -> browse GOOD / REVIEW / POOR results.

This file only handles the UI. Image analysis lives in analyzer.py,
scoring lives in scoring.py, and all Google Drive / OAuth calls live
in drive.py. Photos are only ever held in memory long enough to score
them — nothing is written to disk on the server.
"""
from typing import Dict, List

import streamlit as st

import drive
from analyzer import analyze_image, make_thumbnail
from scoring import compute_score

st.set_page_config(page_title="PhotoSort", page_icon="📸", layout="wide")

FILTERS = ["ALL", "GOOD", "REVIEW", "POOR"]

# ---------------------------------------------------------------------------
# Theme — dark, editorial, photography-tool feel. Not default Streamlit.
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
[data-testid="stAppViewContainer"] { background: #14151A; }
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

.block-container { padding-top: 2.4rem; max-width: 1080px; }

.ps-hero { padding-bottom: 1.6rem; border-bottom: 1px solid #262832; margin-bottom: 1.8rem; }
.ps-hero-title {
    font-family: 'Space Grotesk', sans-serif; font-weight: 700;
    font-size: 2.4rem; color: #F2F1ED; letter-spacing: -0.01em;
    margin: 0; line-height: 1.15;
}
.ps-hero-tag { font-size: 1.02rem; color: #9A9CA8; margin: 0.5rem 0 1.4rem 0; max-width: 640px; }

.ps-strip { display: flex; gap: 0.7rem; flex-wrap: wrap; }
.ps-frame { flex: 1; min-width: 130px; border-radius: 4px; padding: 0.8rem 1rem; }
.ps-frame-good { background: rgba(95,191,119,0.08); border: 1px solid rgba(95,191,119,0.35); }
.ps-frame-review { background: rgba(232,163,61,0.08); border: 1px solid rgba(232,163,61,0.35); }
.ps-frame-poor { background: rgba(224,97,90,0.08); border: 1px solid rgba(224,97,90,0.35); }
.ps-frame-score { font-family: 'Space Grotesk', sans-serif; font-size: 1.4rem; font-weight: 600; color: #F2F1ED; }
.ps-frame-label { font-size: 0.78rem; margin-top: 0.1rem; font-weight: 600; }
.ps-frame-good .ps-frame-label { color: #5FBF77; }
.ps-frame-review .ps-frame-label { color: #E8A33D; }
.ps-frame-poor .ps-frame-label { color: #E0615A; }

.ps-step {
    font-family: 'Space Grotesk', sans-serif; font-size: 1.05rem; font-weight: 600;
    color: #F2F1ED; margin: 0.4rem 0 0.5rem 0;
}
.ps-caption { color: #7D7F8C; font-size: 0.86rem; margin: 0.2rem 0 1rem 0; }

.ps-stats { display: flex; gap: 0.8rem; margin-bottom: 1.1rem; flex-wrap: wrap; }
.ps-stat { flex: 1; min-width: 120px; background: #1B1C22; border: 1px solid #262832; border-radius: 4px; padding: 0.85rem 1.05rem; }
.ps-stat-value { font-family: 'Space Grotesk', sans-serif; font-size: 1.6rem; font-weight: 600; color: #F2F1ED; }
.ps-stat-label { font-size: 0.78rem; color: #9A9CA8; margin-top: 0.1rem; }
.ps-stat-good .ps-stat-value { color: #5FBF77; }
.ps-stat-review .ps-stat-value { color: #E8A33D; }
.ps-stat-poor .ps-stat-value { color: #E0615A; }

.ps-badge { display: inline-flex; align-items: center; font-size: 0.76rem; font-weight: 600; padding: 0.15rem 0.5rem; border-radius: 3px; }
.ps-badge-good { background: rgba(95,191,119,0.14); color: #5FBF77; }
.ps-badge-review { background: rgba(232,163,61,0.14); color: #E8A33D; }
.ps-badge-poor { background: rgba(224,97,90,0.14); color: #E0615A; }
.ps-score { font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 0.98rem; color: #F2F1ED; margin-right: 0.45rem; }

.stButton button, .stLinkButton a {
    border-radius: 4px !important; border: 1px solid #33353F !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}
.stButton button[kind="primary"] {
    background: #D9A441 !important; color: #14151A !important;
    border: none !important; font-weight: 600 !important;
}
[data-testid="stVerticalBlockBorderWrapper"] { background: #1B1C22; border-color: #262832 !important; border-radius: 4px !important; }
[data-testid="stTextInput"] input { background: #1B1C22 !important; color: #F2F1ED !important; border-color: #33353F !important; }
</style>
"""

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "credentials": None,
    "results": [],
    "folder_link": "",
    "folder_name": None,
    "detail_id": None,
    "filter": "ALL",
    "error": None,
}
for _key, _value in _DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _value


# ---------------------------------------------------------------------------
# Google Drive auth
# ---------------------------------------------------------------------------
def handle_oauth_redirect() -> None:
    """After Google redirects back with ?code=&state=, exchange the code
    and immediately resume analysis on the folder the person pasted
    before leaving for the Google consent screen. The folder ID travels
    in the OAuth `state` param since a full-page redirect to Google and
    back isn't guaranteed to preserve session_state.
    """
    code = st.query_params.get("code")
    if not code or st.session_state.credentials is not None:
        return

    folder_id = st.query_params.get("state")
    try:
        creds = drive.exchange_code_for_credentials(code)
        st.session_state.credentials = drive.credentials_to_dict(creds)
    except Exception as e:
        st.session_state.error = f"Google sign-in failed: {e}"
        st.query_params.clear()
        return

    st.query_params.clear()
    if folder_id:
        service = get_drive_service()
        if service:
            run_analysis(service, folder_id)
    st.rerun()


def get_drive_service():
    if not st.session_state.credentials:
        return None
    creds = drive.credentials_from_dict(st.session_state.credentials)
    creds = drive.refresh_if_needed(creds)
    st.session_state.credentials = drive.credentials_to_dict(creds)
    return drive.build_service(creds)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def run_analysis(service, folder_id: str) -> None:
    """Look up the folder, list its images, score every one. Photos are
    only ever held in memory for the duration of this call — nothing
    touches disk on the server.
    """
    try:
        st.session_state.folder_name = drive.get_folder_name(service, folder_id)
    except Exception:
        st.session_state.folder_name = None

    try:
        files = drive.list_images_in_folder(service, folder_id)
    except Exception as e:
        st.session_state.error = f"Could not read that folder: {e}"
        return

    if not files:
        st.session_state.error = "No photos found in that folder."
        st.session_state.results = []
        return

    total = len(files)
    progress = st.progress(0.0, text="Starting analysis...")
    results: List[Dict] = []

    for i, f in enumerate(files):
        try:
            image_bytes = drive.download_image_bytes(service, f["id"])
            metrics = analyze_image(image_bytes)
            scored = compute_score(metrics)
            thumbnail_bytes = make_thumbnail(image_bytes)
            results.append({
                "id": f["id"],
                "name": f["name"],
                "thumbnail_bytes": thumbnail_bytes,
                "web_view_link": f.get("webViewLink"),
                "metrics": metrics,
                **scored,
            })
        except Exception as e:
            results.append({
                "id": f["id"],
                "name": f["name"],
                "thumbnail_bytes": None,
                "web_view_link": f.get("webViewLink"),
                "metrics": {},
                "score": 0,
                "label": "POOR",
                "reasons": [f"Could not analyze this photo ({e})"],
                "sub_scores": {},
            })
        progress.progress((i + 1) / total, text=f"Analyzing {i + 1}/{total}: {f['name']}")

    progress.empty()
    st.session_state.results = results
    st.session_state.detail_id = None
    st.session_state.error = None


def run_local_analysis(uploaded_files) -> None:
    """Same scoring pipeline, fed by direct uploads instead of Drive —
    handy for trying PhotoSort before OAuth is configured at all.
    """
    total = len(uploaded_files)
    progress = st.progress(0.0, text="Starting analysis...")
    results: List[Dict] = []
    for i, f in enumerate(uploaded_files):
        image_bytes = f.read()
        try:
            metrics = analyze_image(image_bytes)
            scored = compute_score(metrics)
            thumbnail_bytes = make_thumbnail(image_bytes)
            results.append({
                "id": f.name,
                "name": f.name,
                "thumbnail_bytes": thumbnail_bytes,
                "web_view_link": None,
                "metrics": metrics,
                **scored,
            })
        except Exception as e:
            st.error(f"Could not analyze {f.name}: {e}")
        progress.progress((i + 1) / total, text=f"Analyzing {i + 1}/{total}")
    progress.empty()
    st.session_state.results = results
    st.session_state.detail_id = None
    st.session_state.folder_name = "Uploaded photos"


# ---------------------------------------------------------------------------
# UI sections
# ---------------------------------------------------------------------------
def render_hero() -> None:
    st.markdown(
        "<div class='ps-hero'>"
        "<p class='ps-hero-title'>📸 PhotoSort</p>"
        "<p class='ps-hero-tag'>Paste a Google Drive folder link, connect your account, "
        "and PhotoSort scores every photo for sharpness, exposure, brightness, "
        "and resolution — no AI model, fully explainable.</p>"
        "<div class='ps-strip'>"
        "<div class='ps-frame ps-frame-good'><div class='ps-frame-score'>92</div>"
        "<div class='ps-frame-label'>GOOD</div></div>"
        "<div class='ps-frame ps-frame-review'><div class='ps-frame-score'>74</div>"
        "<div class='ps-frame-label'>REVIEW</div></div>"
        "<div class='ps-frame ps-frame-poor'><div class='ps-frame-score'>38</div>"
        "<div class='ps-frame-label'>POOR</div></div>"
        "</div></div>",
        unsafe_allow_html=True,
    )


def render_connect_and_analyze() -> None:
    st.markdown("<p class='ps-step'>1. Paste your Google Drive folder link</p>", unsafe_allow_html=True)
    st.session_state.folder_link = st.text_input(
        "Drive folder link",
        value=st.session_state.folder_link,
        placeholder="https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp...",
        label_visibility="collapsed",
    )
    st.markdown(
        "<p class='ps-caption'>Open the folder in Google Drive, click Share → Copy link, "
        "and paste it here. PhotoSort only reads photos inside that folder.</p>",
        unsafe_allow_html=True,
    )

    if not drive.is_configured():
        st.warning(
            "Google OAuth isn't configured yet. Add `client_id` / `client_secret` "
            "under `[google_oauth]` in Streamlit Secrets — see README.md."
        )
        return

    link_typed = bool(st.session_state.folder_link.strip())
    folder_id = drive.extract_folder_id(st.session_state.folder_link) if link_typed else None

    st.markdown("<p class='ps-step'>2 &amp; 3. Connect &amp; analyze</p>", unsafe_allow_html=True)

    if link_typed and not folder_id:
        st.error("That doesn't look like a Google Drive folder link. Double-check and paste it again.")
        return
    if not folder_id:
        st.caption("Paste a folder link above to continue.")
        return

    if st.session_state.credentials:
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Analyze photos", type="primary", use_container_width=True):
                service = get_drive_service()
                if service:
                    run_analysis(service, folder_id)
        with col2:
            if st.button("Disconnect Google account", use_container_width=True):
                st.session_state.credentials = None
                st.session_state.results = []
                st.rerun()
    else:
        auth_url = drive.get_authorization_url(state=folder_id)
        st.link_button("Continue with Google to analyze this folder", auth_url, type="primary")

    if st.session_state.error:
        st.error(st.session_state.error)


def render_local_fallback() -> None:
    with st.expander("Try it without Google Drive (upload photos directly)"):
        st.caption("Uploaded photos are processed in memory only, never saved to disk.")
        uploaded = st.file_uploader(
            "Upload photos",
            type=["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if uploaded and st.button("Analyze uploaded photos"):
            run_local_analysis(uploaded)


def render_dashboard(results: List[Dict]) -> None:
    total = len(results)
    good = sum(1 for r in results if r["label"] == "GOOD")
    review = sum(1 for r in results if r["label"] == "REVIEW")
    poor = sum(1 for r in results if r["label"] == "POOR")

    st.markdown(
        "<div class='ps-stats'>"
        f"<div class='ps-stat'><div class='ps-stat-value'>{total}</div>"
        f"<div class='ps-stat-label'>Total Photos</div></div>"
        f"<div class='ps-stat ps-stat-good'><div class='ps-stat-value'>{good}</div>"
        f"<div class='ps-stat-label'>GOOD</div></div>"
        f"<div class='ps-stat ps-stat-review'><div class='ps-stat-value'>{review}</div>"
        f"<div class='ps-stat-label'>REVIEW</div></div>"
        f"<div class='ps-stat ps-stat-poor'><div class='ps-stat-value'>{poor}</div>"
        f"<div class='ps-stat-label'>POOR</div></div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_filter() -> None:
    st.session_state.filter = st.radio(
        "Filter", FILTERS, horizontal=True,
        index=FILTERS.index(st.session_state.filter),
        label_visibility="collapsed",
    )


def _badge_html(item: Dict) -> str:
    label = item["label"].lower()
    return (
        f"<span class='ps-score'>{item['score']}</span>"
        f"<span class='ps-badge ps-badge-{label}'>{item['label']}</span>"
    )


def render_grid(results: List[Dict]) -> None:
    filt = st.session_state.filter
    filtered = results if filt == "ALL" else [r for r in results if r["label"] == filt]
    if not filtered:
        st.caption("No photos in this category.")
        return

    cols_per_row = 4
    for row_start in range(0, len(filtered), cols_per_row):
        row_items = filtered[row_start:row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, item in zip(cols, row_items):
            with col:
                with st.container(border=True):
                    if item.get("thumbnail_bytes"):
                        st.image(item["thumbnail_bytes"], use_container_width=True)
                    else:
                        st.write("🖼️ (no preview)")
                    st.markdown(_badge_html(item), unsafe_allow_html=True)
                    if st.button("View details", key=f"view_{item['id']}", use_container_width=True):
                        st.session_state.detail_id = item["id"]
                        st.rerun()
                    if item.get("web_view_link"):
                        st.link_button("Open in Google Drive", item["web_view_link"], use_container_width=True)


def render_detail(results: List[Dict]) -> None:
    detail_id = st.session_state.detail_id
    if not detail_id:
        return
    item = next((r for r in results if r["id"] == detail_id), None)
    if not item:
        return

    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            if item.get("thumbnail_bytes"):
                st.image(item["thumbnail_bytes"], use_container_width=True)
            if item.get("web_view_link"):
                st.link_button("Open in Google Drive", item["web_view_link"], use_container_width=True)
        with c2:
            st.markdown(f"#### {item['name']}", unsafe_allow_html=True)
            st.markdown(_badge_html(item), unsafe_allow_html=True)
            m = item["metrics"]
            if m:
                st.write(f"**Sharpness:** {m['sharpness']:.1f}")
                st.write(f"**Brightness:** {m['brightness']:.1f} / 255")
                st.write(
                    f"**Exposure:** {m['shadow_clip_pct']:.1f}% shadow clip, "
                    f"{m['highlight_clip_pct']:.1f}% highlight clip"
                )
                st.write(f"**Resolution:** {m['width']}×{m['height']} ({m['megapixels']} MP)")
            st.write("**Why this score:**")
            for reason in item["reasons"]:
                st.write(f"- {reason}")
        if st.button("Close"):
            st.session_state.detail_id = None
            st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    handle_oauth_redirect()
    render_hero()
    render_connect_and_analyze()
    render_local_fallback()

    results = st.session_state.results
    if results:
        st.divider()
        name = st.session_state.folder_name
        heading = "4. Results" + (f" — {name}" if name else "")
        st.markdown(f"<p class='ps-step'>{heading}</p>", unsafe_allow_html=True)
        render_dashboard(results)
        render_filter()
        render_grid(results)
        render_detail(results)


if __name__ == "__main__":
    main()
