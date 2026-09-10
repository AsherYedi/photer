"""PhotoSort — Find your best shots faster.

Flow: Connect Google Drive -> Select folder -> Analyze photos -> View results.

This file only handles the UI. Image analysis lives in analyzer.py,
scoring lives in scoring.py, and all Google Drive / OAuth calls live
in drive.py.
"""
from typing import Dict, List, Optional

import streamlit as st

import drive
from analyzer import analyze_image, make_thumbnail
from scoring import compute_score

st.set_page_config(page_title="PhotoSort", page_icon="📸", layout="wide")

STATUS_COLORS = {"GOOD": "#16a34a", "REVIEW": "#d97706", "POOR": "#dc2626"}
FILTERS = ["ALL", "GOOD", "REVIEW", "POOR"]

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "credentials": None,
    "results": [],          # list of scored photo dicts, see analyze_folder()
    "selected_folder": None,
    "detail_id": None,
    "filter": "ALL",
}
for key, value in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------------------------------------------------------------------
# Google Drive auth
# ---------------------------------------------------------------------------
def handle_oauth_redirect() -> None:
    """After Google redirects back with ?code=..., exchange it once."""
    code = st.query_params.get("code")
    if code and st.session_state.credentials is None:
        try:
            creds = drive.exchange_code_for_credentials(code)
            st.session_state.credentials = drive.credentials_to_dict(creds)
        except Exception as e:
            st.error(f"Google sign-in failed: {e}")
        finally:
            st.query_params.clear()


def get_drive_service():
    if not st.session_state.credentials:
        return None
    creds = drive.credentials_from_dict(st.session_state.credentials)
    creds = drive.refresh_if_needed(creds)
    st.session_state.credentials = drive.credentials_to_dict(creds)
    return drive.build_service(creds)


# ---------------------------------------------------------------------------
# UI sections
# ---------------------------------------------------------------------------
def render_header() -> None:
    st.markdown(
        "<h1 style='margin-bottom:0'>📸 PhotoSort</h1>"
        "<p style='color:gray;margin-top:0;font-size:1.1rem'>"
        "Find your best shots faster.</p>",
        unsafe_allow_html=True,
    )


def render_connect_step() -> None:
    st.subheader("1. Connect Google Drive")
    if not drive.is_configured():
        st.warning(
            "Google OAuth isn't configured yet. Add `client_id` / "
            "`client_secret` under `[google_oauth]` in "
            "`.streamlit/secrets.toml` — see README.md."
        )
        return

    if st.session_state.credentials:
        st.success("Google Drive connected.")
        if st.button("Disconnect"):
            st.session_state.credentials = None
            st.session_state.results = []
            st.session_state.selected_folder = None
            st.rerun()
    else:
        st.link_button("Connect Google Drive", drive.get_authorization_url())


def render_folder_step() -> Optional[str]:
    st.subheader("2. Select folder")
    service = get_drive_service()
    if not service:
        st.caption("Connect Google Drive first.")
        return None

    search = st.text_input("Search folder by name", placeholder="e.g. Wedding - Sept 2026")
    try:
        folders = drive.list_folders(service, query=search or None)
    except Exception as e:
        st.error(f"Could not list folders: {e}")
        return None

    if not folders:
        st.caption("No folders found.")
        return None

    options = {f["name"]: f["id"] for f in folders}
    chosen_name = st.selectbox("Folder", list(options.keys()))
    st.session_state.selected_folder = options.get(chosen_name)
    return st.session_state.selected_folder


def analyze_folder(service, folder_id: str) -> None:
    try:
        files = drive.list_images_in_folder(service, folder_id)
    except Exception as e:
        st.error(f"Could not list photos: {e}")
        return

    if not files:
        st.warning("No photos found in this folder.")
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
                "metrics": metrics,
                **scored,
            })
        except Exception as e:
            results.append({
                "id": f["id"],
                "name": f["name"],
                "thumbnail_bytes": None,
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


def render_local_test_mode() -> None:
    """Lets PhotoSort be exercised end-to-end with local files, before
    Google OAuth credentials are configured — useful for local dev.
    """
    st.caption(
        "Try the analyzer locally without connecting Drive. "
        "Uploaded photos are processed in memory only."
    )
    uploaded = st.file_uploader(
        "Upload photos",
        type=["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"],
        accept_multiple_files=True,
    )
    if uploaded and st.button("Analyze uploaded photos", type="primary"):
        total = len(uploaded)
        progress = st.progress(0.0, text="Starting analysis...")
        results: List[Dict] = []
        for i, f in enumerate(uploaded):
            image_bytes = f.read()
            try:
                metrics = analyze_image(image_bytes)
                scored = compute_score(metrics)
                thumbnail_bytes = make_thumbnail(image_bytes)
                results.append({
                    "id": f.name,
                    "name": f.name,
                    "thumbnail_bytes": thumbnail_bytes,
                    "metrics": metrics,
                    **scored,
                })
            except Exception as e:
                st.error(f"Could not analyze {f.name}: {e}")
            progress.progress((i + 1) / total, text=f"Analyzing {i + 1}/{total}")
        progress.empty()
        st.session_state.results = results
        st.session_state.detail_id = None


def render_dashboard(results: List[Dict]) -> None:
    total = len(results)
    good = sum(1 for r in results if r["label"] == "GOOD")
    review = sum(1 for r in results if r["label"] == "REVIEW")
    poor = sum(1 for r in results if r["label"] == "POOR")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Photos", total)
    c2.metric("GOOD", good)
    c3.metric("REVIEW", review)
    c4.metric("POOR", poor)


def render_filter() -> None:
    st.session_state.filter = st.radio(
        "Filter",
        FILTERS,
        horizontal=True,
        index=FILTERS.index(st.session_state.filter),
        label_visibility="collapsed",
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
                if item.get("thumbnail_bytes"):
                    st.image(item["thumbnail_bytes"], use_container_width=True)
                else:
                    st.write("🖼️ (no preview)")
                color = STATUS_COLORS[item["label"]]
                st.markdown(
                    f"**Score {item['score']}**  \n"
                    f"<span style='color:{color};font-weight:600'>{item['label']}</span>",
                    unsafe_allow_html=True,
                )
                if st.button("View details", key=f"view_{item['id']}", use_container_width=True):
                    st.session_state.detail_id = item["id"]
                    st.rerun()


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
        with c2:
            color = STATUS_COLORS[item["label"]]
            st.markdown(
                f"### {item['name']}\n"
                f"#### Score {item['score']} "
                f"<span style='color:{color}'>({item['label']})</span>",
                unsafe_allow_html=True,
            )
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
    handle_oauth_redirect()
    render_header()

    tab_drive, tab_local = st.tabs(["Google Drive", "Local test (no Drive needed)"])

    with tab_drive:
        render_connect_step()
        folder_id = render_folder_step()
        st.subheader("3. Analyze photos")
        if not folder_id:
            st.caption("Select a folder above first.")
        elif st.button("Analyze photos", type="primary"):
            service = get_drive_service()
            if service:
                analyze_folder(service, folder_id)

    with tab_local:
        render_local_test_mode()

    results = st.session_state.results
    if results:
        st.divider()
        st.subheader("4. Results")
        render_dashboard(results)
        render_filter()
        render_grid(results)
        render_detail(results)


if __name__ == "__main__":
    main()
