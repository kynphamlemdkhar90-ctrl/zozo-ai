import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import streamlit as st
import yt_dlp

st.set_page_config(page_title="ZOZO AI", page_icon="🤖", layout="centered")

st.markdown("""
<style>
.block-container {max-width: 900px; padding-top: 2.5rem;}
.hero {text-align:center; padding: 1rem 0 1.5rem;}
.hero h1 {font-size: 3.2rem; margin-bottom: .3rem;}
.hero p {font-size: 1.15rem; color:#666;}
.urlbox {border:1px solid #ddd; border-radius:18px; padding:1rem;}
.feature {border:1px solid #eee; border-radius:16px; padding:1rem; margin:.5rem 0;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>🤖 ZOZO AI</h1>
<p>Turn long videos into engaging short clips.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("### 🔗 Paste a YouTube video URL")
url = st.text_input(
    "YouTube URL",
    placeholder="https://www.youtube.com/watch?v=...",
    label_visibility="collapsed",
)

st.caption("Your phone only sends the link. ZOZO AI processes the source video on the server.")

duration = st.selectbox("🎬 Clip length", [30, 45, 60], index=1, format_func=lambda x: f"{x} seconds")
num_clips = st.slider("✂️ Number of clips", 1, 6, 3)

generate = st.button("🚀 Generate Clips", type="primary", use_container_width=True)

def valid_youtube(u: str) -> bool:
    return bool(re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", u.strip()))

def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def get_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0

def make_clip(src, out, start, length):
    r = run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(src),
        "-t", str(length),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(out)
    ])
    return r.returncode == 0

if generate:
    if not url.strip():
        st.error("Please paste a YouTube video link first.")
        st.stop()
    if not valid_youtube(url):
        st.error("Please enter a valid YouTube or youtu.be link.")
        st.stop()

    work = Path(tempfile.mkdtemp(prefix="zozo_"))
    source = work / "source.mp4"

    try:
        with st.status("🤖 ZOZO AI is working...", expanded=True) as status:
            st.write("🔗 Connecting to the video...")
            opts = {
                "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "outtmpl": str(source),
                "merge_output_format": "mp4",
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            if not source.exists():
                candidates = list(work.glob("*"))
                mp4s = [p for p in candidates if p.suffix.lower() == ".mp4"]
                if mp4s:
                    source = mp4s[0]

            if not source.exists():
                raise RuntimeError("The video could not be downloaded.")

            total = get_duration(source)
            if total < 5:
                raise RuntimeError("The downloaded video is too short or its duration could not be read.")

            st.write("🧠 Finding highlight candidates...")
            # Lightweight server-side highlight selection:
            # choose several well-spaced moments, avoiding the very beginning/end.
            usable = max(total - duration, 0)
            if usable <= 0:
                starts = [0]
            else:
                count = min(num_clips, max(1, int(total // max(duration * 0.75, 1))))
                count = min(count, num_clips)
                if count == 1:
                    starts = [usable / 2]
                else:
                    starts = [usable * i / (count - 1) for i in range(count)]

            output_dir = work / "clips"
            output_dir.mkdir()
            clips = []

            st.write("✂️ Creating vertical 9:16 clips...")
            for i, start in enumerate(starts, 1):
                out = output_dir / f"ZOZO_AI_Clip_{i}.mp4"
                length = min(duration, total - start)
                if make_clip(source, out, start, length):
                    clips.append(out)

            if not clips:
                raise RuntimeError("No clips could be created.")

            status.update(label="✅ Your clips are ready!", state="complete")

        st.success(f"Created {len(clips)} clip(s).")
        st.markdown("### 🎬 Your ZOZO AI clips")

        for i, clip in enumerate(clips, 1):
            st.markdown(f"**Clip {i}** · 9:16 vertical")
            st.video(str(clip))
            with open(clip, "rb") as f:
                st.download_button(
                    f"⬇️ Download Clip {i}",
                    data=f.read(),
                    file_name=clip.name,
                    mime="video/mp4",
                    key=f"download_{i}",
                    use_container_width=True,
                )

        st.info("💡 This first online version creates smart highlight candidates and converts them to 9:16. Automatic captions, speaker tracking and AI-generated titles are the next upgrades.")

    except Exception as e:
        st.error("ZOZO AI could not process this video.")
        st.caption(str(e))
    finally:
        shutil.rmtree(work, ignore_errors=True)

st.divider()
st.markdown("### ✨ ZOZO AI")
cols = st.columns(2)
with cols[0]:
    st.markdown("**🎯 Find highlight candidates**")
    st.markdown("**✂️ Create multiple short clips**")
    st.markdown("**📱 Convert to 9:16 Shorts**")
with cols[1]:
    st.markdown("**▶️ Preview your clips**")
    st.markdown("**⬇️ Download selected clips**")
    st.markdown("**📝 Captions & AI titles — next upgrade**")
