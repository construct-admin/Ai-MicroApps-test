# ------------------------------------------------------------------------------
# Refactor date: 2025-11-12
# Refactored by: Imaad Fakier
# Purpose: Align Discussion Generator micro-app with OES GenAI Streamlit standards.
# ------------------------------------------------------------------------------
"""
Visual Transcripts Generator (Refactored)
-----------------------------------------
Streamlit entrypoint for OES' Visual Transcripts micro-app.

Highlights in this refactor:
- Adds environment variable management with `.env` + `load_dotenv()`.
- Implements SHA-256 access-code gate aligned with other GenAI apps.
- Moves to OpenAI SDK v1 (`>=1.45.0,<2.0.0`) for vision transcription.
- Introduces structured, safer state management and ordered SRT parsing.
- Ensures predictable export behavior and frame handling using OpenCV.

This file follows the same documentation and style standards as the
Alt-Text Generator refactor for consistency across OES GenAI micro-apps.
"""

import os
import io
import cv2
import base64
import tempfile
import hashlib
from collections import OrderedDict
from datetime import timedelta

import numpy as np
import streamlit as st
from PIL import Image
from docx import Document
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Page setup and environment loading
# ------------------------------------------------------------------------------
st.set_page_config(page_title="VT Generator", page_icon="🖼️", layout="wide")
load_dotenv()  # Loads .env file variables into environment

# Constants and environment expectations
APP_TITLE = "Visual Transcripts Generator"
DEFAULT_FPS_FALLBACK = 30
MAX_FILES = 1  # Only one video processed at a time
SUPPORTED_VIDEO_EXTS = ["mp4"]
SUPPORTED_SRT_EXTS = ["srt"]
MODEL_NAME = os.getenv("VT_MODEL", "gpt-4o")  # Allow override via .env


# ------------------------------------------------------------------------------
# Authentication helpers
# ------------------------------------------------------------------------------
def sha256_hex(s: str) -> str:
    """Hash a provided access code using SHA‑256. Used for secure auth comparison."""
    return hashlib.sha256(s.encode()).hexdigest()


ACCESS_CODE_HASH = os.getenv("ACCESS_CODE_HASH")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not ACCESS_CODE_HASH:
    st.error(
        "⚠️ Hashed access code not found. Please set ACCESS_CODE_HASH in your environment or Streamlit secrets."
    )
    st.stop()


# ------------------------------------------------------------------------------
# Session State initialization
# ------------------------------------------------------------------------------
def init_state():
    """Initialize session_state keys for consistent runtime behavior.

    Keys maintained:
    - authenticated: Boolean for access control.
    - video_path: Temporary storage path of uploaded video.
    - fps / frame_count: Video metadata.
    - frame_index: Current frame slider value.
    - video_ready: Flag once video + subtitles parsed.
    - saved_frames: List of captured frames (dicts).
    - saved_subtitles: Subtitle text aligned with saved frames.
    - subtitles: OrderedDict mapping seconds -> subtitle text.
    - transcriptions: GPT‑generated descriptions per frame.
    """
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("video_path", None)
    st.session_state.setdefault("fps", DEFAULT_FPS_FALLBACK)
    st.session_state.setdefault("frame_count", 0)
    st.session_state.setdefault("frame_index", 0)
    st.session_state.setdefault("video_ready", False)
    st.session_state.setdefault("saved_frames", [])
    st.session_state.setdefault("saved_subtitles", [])
    st.session_state.setdefault("subtitles", OrderedDict())
    st.session_state.setdefault("transcriptions", {})


init_state()

# ------------------------------------------------------------------------------
# Access control gate
# ------------------------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔒 Access Restricted")
    with st.form("auth_form", clear_on_submit=False):
        access_code_input = st.text_input("Enter Access Code:", type="password")
        submitted = st.form_submit_button("Submit")
    if submitted:
        if sha256_hex(access_code_input) == ACCESS_CODE_HASH:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect access code. Please try again.")
    st.stop()


# ------------------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------------------
def seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds float to HH:MM:SS.mmm formatted timestamp."""
    td = timedelta(seconds=int(seconds))
    ms = int((seconds - int(seconds)) * 1000)
    return f"{str(td)}.{ms:03d}"


def parse_srt_bytes(srt_bytes: bytes) -> OrderedDict:
    """Parse SRT file bytes into an OrderedDict of {start_seconds: caption}.

    Handles multi‑line captions and ensures natural time ordering.
    Returns OrderedDict for deterministic iteration.
    """
    text = srt_bytes.decode("utf-8", errors="ignore").replace("\r\n", "\n")
    blocks, block = [], []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            block.append(line)
        else:
            if block:
                blocks.append(block)
                block = []
    if block:
        blocks.append(block)

    parsed = []
    for b in blocks:
        if len(b) < 2:
            continue
        timing_line, text_lines = None, []
        for i, line in enumerate(b):
            if "-->" in line:
                timing_line = line
                text_lines = b[i + 1 :]
                break
        if not timing_line:
            continue
        start_str = timing_line.split("-->")[0].strip().replace(",", ".")
        parts = start_str.split(":")
        try:
            if len(parts) == 3:
                h, m, s = parts
                start_seconds = int(h) * 3600 + int(m) * 60 + float(s)
            else:
                m, s = parts
                start_seconds = int(m) * 60 + float(s)
        except Exception:
            continue
        caption = " ".join(t.strip() for t in text_lines if t.strip())
        parsed.append((start_seconds, caption))
    parsed.sort(key=lambda x: x[0])
    return OrderedDict(parsed)


def pil_to_base64_jpg(pil_img: Image.Image) -> str:
    """Convert PIL image to base64‑encoded JPEG string for GPT‑4o vision input."""
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=95)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ------------------------------------------------------------------------------
# OpenAI integration (SDK v1)
# ------------------------------------------------------------------------------
_client = None


def get_openai_client():
    """Initialize and memoize OpenAI client using API key from environment."""
    global _client
    if _client is None:
        from openai import OpenAI  # type: ignore

        if not OPENAI_API_KEY:
            st.sidebar.error("Missing OPENAI_API_KEY in environment")
            raise RuntimeError("OPENAI_API_KEY missing")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def describe_image_with_gpt(
    pil_img: Image.Image, prompt: str = "What’s in this image?", max_tokens: int = 300
) -> str:
    """Send an image to GPT‑4o for description using vision API.

    Parameters:
        pil_img: The frame captured from the video.
        prompt: Optional custom text prompt.
        max_tokens: Upper bound for token count.

    Returns: string content of GPT response.
    """
    base64_image = pil_to_base64_jpg(pil_img)
    client = get_openai_client()
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }
        ],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ------------------------------------------------------------------------------
# UI: Main layout and functional flow
# ------------------------------------------------------------------------------
st.title(APP_TITLE)
st.caption(
    "Refactored to Alt‑Text architecture: env + auth + unified OpenAI SDK + safer state."
)

# Uploaders for video and SRT
col_u1, col_u2 = st.columns([2, 1])
with col_u1:
    video_file = st.file_uploader("Upload Video File (MP4)", type=SUPPORTED_VIDEO_EXTS)
with col_u2:
    srt_file = st.file_uploader("Upload Subtitle File (SRT)", type=SUPPORTED_SRT_EXTS)

# Video preview
if video_file:
    with st.expander("▶️ Click to Preview Uploaded Video"):
        st.video(video_file)
    temp_video_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    with open(temp_video_path, "wb") as f:
        f.write(video_file.read())
    st.session_state["video_path"] = temp_video_path

# Process button (extract metadata and parse SRT)
if video_file and srt_file and st.button("Process"):
    st.session_state["subtitles"] = parse_srt_bytes(srt_file.read())
    cap = cv2.VideoCapture(st.session_state["video_path"])
    fps = cap.get(cv2.CAP_PROP_FPS) or DEFAULT_FPS_FALLBACK
    st.session_state["fps"] = int(round(fps))
    st.session_state["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    st.session_state["video_ready"] = True
    st.success("Video and subtitles processed.")

# Sidebar transcript listing
st.sidebar.subheader("Transcript")
if st.session_state["subtitles"]:
    for ts_sec, text in st.session_state["subtitles"].items():
        st.sidebar.write(f"**{seconds_to_timestamp(ts_sec)}**: {text}")
else:
    st.sidebar.info("Upload and process an SRT to view transcript here.")

# ------------------------------------------------------------------------------
# Frame navigation and capture
# ------------------------------------------------------------------------------
if st.session_state.get("video_ready", False):
    max_index = max(0, st.session_state["frame_count"] - 1)
    frame_slider = st.slider(
        "Select Frame", 0, max_index, st.session_state["frame_index"]
    )
    st.session_state["frame_index"] = frame_slider

    cap = cv2.VideoCapture(st.session_state["video_path"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_slider)
    ret, frame = cap.read()
    cap.release()

    if ret and frame is not None:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        st.image(pil_image, caption=f"Frame {frame_slider}")
    else:
        st.warning("Could not read frame.")
        pil_image = None

    # Navigation and saving controls
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("⏮️ Previous Frame"):
            st.session_state["frame_index"] = max(
                0, st.session_state["frame_index"] - 1
            )
            st.rerun()
    with c2:
        if st.button("⏭️ Next Frame"):
            st.session_state["frame_index"] = min(
                st.session_state["frame_index"] + 1, max_index
            )
            st.rerun()
    with c3:
        if pil_image and st.button("💾 Save This Frame"):
            st.session_state["saved_frames"].append(
                {"image": pil_image, "original_frame_index": frame_slider}
            )
            fps = st.session_state.get("fps", DEFAULT_FPS_FALLBACK)
            seconds = frame_slider / max(fps, 1)
            subtitle_text = st.session_state["subtitles"].get(seconds, "No Subtitle")
            st.session_state["saved_subtitles"].append(subtitle_text)
            st.success("Frame saved to sidebar list.")

# ------------------------------------------------------------------------------
# Sidebar saved frames and GPT transcription
# ------------------------------------------------------------------------------
if st.session_state["saved_frames"]:
    st.sidebar.subheader("Saved Frames")
    for i, (frame_data, subtitle) in enumerate(
        zip(st.session_state["saved_frames"], st.session_state["saved_subtitles"])
    ):
        st.sidebar.image(frame_data["image"], caption=f"Saved Frame {i}")
        st.sidebar.write(subtitle)

    st.sidebar.subheader("Frame Transcription")
    for i, frame_data in enumerate(st.session_state["saved_frames"]):
        if st.sidebar.button(f"Transcribe Frame {i}"):
            st.sidebar.write(f"Transcribing Frame {i}…")
            transcription = describe_image_with_gpt(
                frame_data["image"],
                prompt="Describe the key visual details and any on‑screen text relevant to learning context.",
            )
            st.session_state["transcriptions"][i] = transcription
            st.sidebar.text_area(
                f"GPT Response for Frame {i}", transcription, height=180
            )

        if i in st.session_state["transcriptions"] and st.sidebar.button(
            f"Insert into Transcript {i}"
        ):
            fps = st.session_state.get("fps", DEFAULT_FPS_FALLBACK)
            original_frame = frame_data["original_frame_index"]
            seconds = original_frame / max(fps, 1)
            gpt_text = f"[Visual Transcript]: {st.session_state['transcriptions'][i]}"
            prev = st.session_state["subtitles"].get(seconds)
            st.session_state["subtitles"][seconds] = (
                prev + "\n" + gpt_text if prev else gpt_text
            )
            st.sidebar.success(f"Inserted at {seconds_to_timestamp(seconds)}")


# ------------------------------------------------------------------------------
# Export transcript to .docx
# ------------------------------------------------------------------------------
def build_docx_from_subtitles(subtitles_od: OrderedDict) -> str:
    """Generate a .docx transcript preserving timestamp order."""
    doc = Document()
    doc.add_heading("Visual Transcript", level=1)
    for ts_sec, text in subtitles_od.items():
        doc.add_paragraph(f"{seconds_to_timestamp(ts_sec)}: {text}")
    out_path = tempfile.NamedTemporaryFile(delete=False, suffix=".docx").name
    doc.save(out_path)
    return out_path


st.sidebar.subheader("Download Options")
if st.sidebar.button("Generate .docx"):
    if st.session_state["subtitles"]:
        path = build_docx_from_subtitles(st.session_state["subtitles"])
        with open(path, "rb") as fh:
            st.sidebar.download_button(
                "Download Transcript",
                data=fh,
                file_name="visual_transcript.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
    else:
        st.sidebar.info("Nothing to export yet.")

# ------------------------------------------------------------------------------
# Logout control
# ------------------------------------------------------------------------------
st.sidebar.button(
    "Logout",
    on_click=lambda: st.session_state.update({"authenticated": False}),
    key="logout_button",
)
