import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import streamlit as st
import yt_dlp


# -----------------------------
# ZOZO AI
# -----------------------------

st.set_page_config(
    page_title="ZOZO AI",
    page_icon="🤖",
    layout="centered",
)


# -----------------------------
# Helpers
# -----------------------------

def run_command(cmd):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def valid_youtube(url):
    pattern = r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$"
    return bool(re.match(pattern, url.strip()))


def get_duration(video_path):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
    )

    if result.returncode != 0:
        return 0

    try:
        return float(result.stdout.strip())
    except Exception:
        return 0


def make_clip(source, output, start, length):
    result = run_command(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-i",
            str(source),
            "-t",
            str(length),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )

    return result


# -----------------------------
# Header
# -----------------------------

st.title("🤖 ZOZO AI")
st.write("Turn long videos into engaging short clips.")

st.divider()


# -----------------------------
# YouTube URL
# -----------------------------

url = st.text_input(
    "🔗 YouTube Video URL",
    placeholder="Paste your YouTube video link here...",
)

st.caption(
    "ZOZO AI works with normal public YouTube video links."
)


# -----------------------------
# Settings
# -----------------------------

col1, col2 = st.columns(2)

with col1:
    clip_length = st.selectbox(
        "⏱️ Clip Length",
        [15, 30, 45, 60],
        index=1,
    )

with col2:
    number_of_clips = st.slider(
        "🎬 Number of Clips",
        min_value=1,
        max_value=10,
        value=1,
    )


# -----------------------------
# Generate
# -----------------------------

generate = st.button(
    "🚀 Generate Clips",
    type="primary",
    use_container_width=True,
)


if generate:

    # Validate URL
    if not url.strip():
        st.error("Please paste a YouTube video link.")
        st.stop()

    if not valid_youtube(url):
        st.error("Please enter a valid YouTube or YouTube Shorts link.")
        st.stop()

    # Temporary working folder
    work = Path(
        tempfile.mkdtemp(prefix="zozo_")
    )

    source = work / "source.mp4"

    try:

        with st.status(
            "🤖 ZOZO AI is working...",
            expanded=True,
        ):

            st.write("🔗 Connecting to the video...")

            # -----------------------------
            # YouTube downloader
            # -----------------------------

            opts = {
                "format": "best[height<=1080]/best",
                "outtmpl": str(source),
                "merge_output_format": "mp4",

                "extractor_args": {
                    "youtube": {
                        "player_client": [
                            "default",
                            "tv",
                            "web_embedded",
                        ]
                    }
                },

                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            st.write("✅ Video downloaded.")

            # -----------------------------
            # Find downloaded file
            # -----------------------------

            if not source.exists():

                candidates = list(work.glob("*"))

                video_candidates = [
                    p for p in candidates
                    if p.suffix.lower()
                    in [".mp4", ".webm", ".mkv", ".mov"]
                ]

                if video_candidates:
                    source = video_candidates[0]

            if not source.exists():
                raise RuntimeError(
                    "The video could not be downloaded."
                )

            # -----------------------------
            # Get duration
            # -----------------------------

            duration = get_duration(source)

            if duration <= 0:
                raise RuntimeError(
                    "Could not read the video duration."
                )

            st.write(
                f"📹 Video duration: {duration:.1f} seconds"
            )

            # -----------------------------
            # Create clips
            # -----------------------------

            st.write("✂️ Creating short clips...")

            clip_length_real = min(
                float(clip_length),
                duration,
            )

            max_start = max(
                0,
                duration - clip_length_real,
            )

            if number_of_clips == 1:
                starts = [0]
            else:
                starts = [
                    max_start * i / (number_of_clips - 1)
                    for i in range(number_of_clips)
                ]

            output_folder = Path("output")
            output_folder.mkdir(
                parents=True,
                exist_ok=True,
            )

            generated_clips = []

            for index, start in enumerate(starts, start=1):

                clip_path = (
                    work / f"zozo_clip_{index}.mp4"
                )

                result = make_clip(
                    source,
                    clip_path,
                    start,
                    clip_length_real,
                )

                if result.returncode != 0:
                    raise RuntimeError(
                        result.stderr[-2000:]
                    )

                final_path = (
                    output_folder
                    / f"zozo_clip_{index}.mp4"
                )

                shutil.copy2(
                    clip_path,
                    final_path,
                )

                generated_clips.append(
                    final_path
                )

            st.write(
                f"✅ Created {len(generated_clips)} clip(s)."
            )

        # -----------------------------
        # Results
        # -----------------------------

        st.success(
            "🎉 ZOZO AI finished creating your clips!"
        )

        st.subheader("🎬 Your Clips")

        for index, clip in enumerate(
            generated_clips,
            start=1,
        ):

            st.write(
                f"### Clip {index}"
            )

            st.video(str(clip))

            with open(clip, "rb") as video_file:

                st.download_button(
                    label=f"⬇️ Download Clip {index}",
                    data=video_file,
                    file_name=clip.name,
                    mime="video/mp4",
                    use_container_width=True,
                )

        st.divider()

        st.subheader("✨ ZOZO AI Features")

        st.write("✅ YouTube video input")
        st.write("✅ Up to 1080p source video")
        st.write("✅ Multiple short clips")
        st.write("✅ 9:16 vertical format")
        st.write("✅ Automatic video cropping")
        st.write("✅ Clip preview")
        st.write("✅ Download generated clips")

        st.info(
            "🚀 More AI features such as automatic captions, "
            "AI-selected viral moments, speaker tracking, "
            "and AI-generated titles can be added next."
        )

    except Exception as error:

        st.error(
            "❌ ZOZO AI could not process this video."
        )

        st.code(
            str(error),
            language="text",
        )

    finally:

        shutil.rmtree(
            work,
            ignore_errors=True,
            )
