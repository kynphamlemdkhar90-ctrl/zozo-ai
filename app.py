import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile
import platform
from pathlib import Path

import streamlit as st
import yt_dlp


# ============================================================
# ZOZO AI
# YouTube video → short vertical clips
# ============================================================

st.set_page_config(
    page_title="ZOZO AI",
    page_icon="🤖",
    layout="centered",
)


# ============================================================
# Paths and versions
# ============================================================

ZOZO_HOME = Path.home() / ".zozo_ai"

DENO_VERSION = "2.9.5"
BGUTIL_VERSION = "1.3.2"

DENO_DIR = ZOZO_HOME / "deno"
BGUTIL_DIR = ZOZO_HOME / "bgutil-ytdlp-pot-provider"

DENO_BIN = DENO_DIR / "deno"

BGUTIL_PORT = 4416


# ============================================================
# Basic helpers
# ============================================================

def run_command(cmd, cwd=None, timeout=None):
    return subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def valid_youtube(url):
    pattern = (
        r"^(https?://)?"
        r"(www\.)?"
        r"(youtube\.com|youtu\.be)/"
    )
    return bool(re.match(pattern, url.strip(), re.IGNORECASE))


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


# ============================================================
# Deno setup
# ============================================================

def get_deno_asset():
    machine = platform.machine().lower()

    if machine in ("x86_64", "amd64"):
        return "deno-x86_64-unknown-linux-gnu.zip"

    if machine in ("aarch64", "arm64"):
        return "deno-aarch64-unknown-linux-gnu.zip"

    raise RuntimeError(
        f"Unsupported CPU architecture: {machine}"
    )


def install_deno():
    ZOZO_HOME.mkdir(parents=True, exist_ok=True)
    DENO_DIR.mkdir(parents=True, exist_ok=True)

    system_deno = shutil.which("deno")

    if system_deno:
        return system_deno

    if DENO_BIN.exists():
        DENO_BIN.chmod(0o755)
        return str(DENO_BIN)

    asset = get_deno_asset()

    url = (
        "https://github.com/denoland/deno/releases/"
        f"download/v{DENO_VERSION}/{asset}"
    )

    zip_path = DENO_DIR / asset

    urllib.request.urlretrieve(
        url,
        zip_path,
    )

    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(DENO_DIR)

    zip_path.unlink(missing_ok=True)

    if not DENO_BIN.exists():
        raise RuntimeError(
            "Deno was downloaded but the executable could not be found."
        )

    DENO_BIN.chmod(0o755)

    return str(DENO_BIN)


# ============================================================
# BgUtils provider setup
# ============================================================

def install_bgutil_source():
    ZOZO_HOME.mkdir(parents=True, exist_ok=True)

    if BGUTIL_DIR.exists():
        return

    archive_path = ZOZO_HOME / "bgutil-provider.zip"

    url = (
        "https://github.com/Brainicism/"
        "bgutil-ytdlp-pot-provider/archive/refs/tags/"
        f"{BGUTIL_VERSION}.zip"
    )

    urllib.request.urlretrieve(
        url,
        archive_path,
    )

    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(ZOZO_HOME)

    extracted_dir = (
        ZOZO_HOME
        / f"bgutil-ytdlp-pot-provider-{BGUTIL_VERSION}"
    )

    if not extracted_dir.exists():
        raise RuntimeError(
            "BgUtils provider source could not be extracted."
        )

    extracted_dir.rename(BGUTIL_DIR)

    archive_path.unlink(missing_ok=True)


def provider_is_running():
    try:
        with socket.create_connection(
            ("127.0.0.1", BGUTIL_PORT),
            timeout=1,
        ):
            return True
    except OSError:
        return False


def start_bgutil_provider(deno_path):
    server_dir = BGUTIL_DIR / "server"
    node_modules = server_dir / "node_modules"

    if not server_dir.exists():
        raise RuntimeError(
            "BgUtils server directory was not found."
        )

    # Install provider dependencies once.
    if not node_modules.exists():
        result = run_command(
            [
                deno_path,
                "install",
                "--allow-scripts=npm:canvas",
                "--frozen",
            ],
            cwd=str(server_dir),
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "BgUtils dependency installation failed:\n\n"
                + result.stderr[-5000:]
            )

    # Start server if it isn't already running.
    if not provider_is_running():
        subprocess.Popen(
            [
                deno_path,
                "run",
                "--allow-env",
                "--allow-net",
                "--allow-ffi=.",
                "--allow-read=.",
                "../src/main.ts",
            ],
            cwd=str(node_modules),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Wait for server.
    for _ in range(30):
        if provider_is_running():
            return

        time.sleep(1)

    raise RuntimeError(
        "BgUtils PO-token provider did not start on port 4416."
    )


@st.cache_resource(show_spinner=False)
def setup_youtube_runtime():
    """
    Install Deno + BgUtils once per running Streamlit instance.
    """

    deno_path = install_deno()

    # Make Deno visible to yt-dlp and the provider.
    deno_parent = str(Path(deno_path).parent)

    os.environ["PATH"] = (
        deno_parent
        + os.pathsep
        + os.environ.get("PATH", "")
    )

    os.environ["DENO_NO_PROMPT"] = "1"
    os.environ["DENO_NO_UPDATE_CHECK"] = "1"

    install_bgutil_source()
    start_bgutil_provider(deno_path)

    return deno_path


# ============================================================
# Video processing
# ============================================================

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

            # Vertical 9:16 output.
            "-vf",
            (
                "scale=1080:1920:"
                "force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
            ),

            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",

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


# ============================================================
# Header
# ============================================================

st.title("🤖 ZOZO AI")

st.write(
    "Turn long YouTube videos into engaging short clips."
)

st.divider()


# ============================================================
# YouTube URL
# ============================================================

url = st.text_input(
    "🔗 YouTube Video URL",
    placeholder="Paste your YouTube video link here",
)

st.caption(
    "ZOZO AI works with normal public YouTube videos."
)


# ============================================================
# Settings
# ============================================================

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


# ============================================================
# Generate button
# ============================================================

generate = st.button(
    "🚀 Generate Clips",
    type="primary",
    use_container_width=True,
)


# ============================================================
# Main processing
# ============================================================

if generate:

    # --------------------------------------------------------
    # Validate URL
    # --------------------------------------------------------

    if not url.strip():
        st.error(
            "Please paste a YouTube video URL."
        )
        st.stop()

    if not valid_youtube(url):
        st.error(
            "Please enter a valid YouTube URL."
        )
        st.stop()

    # --------------------------------------------------------
    # Working directory
    # --------------------------------------------------------

    work = Path(
        tempfile.mkdtemp(
            prefix="zozo_"
        )
    )

    source = work / "source.mp4"

    try:

        # ----------------------------------------------------
        # Setup runtime and PO-token provider
        # ----------------------------------------------------

        with st.status(
            "🤖 ZOZO AI is preparing...",
            expanded=True,
        ):

            st.write(
                "⚙️ Preparing YouTube download system..."
            )

            deno_path = setup_youtube_runtime()

            st.write(
                "✅ YouTube PO-token provider is ready."
            )

            # ------------------------------------------------
            # yt-dlp configuration
            # ------------------------------------------------

            opts = {
                "format": (
                    "bv*[height<=1080]+ba/"
                    "b[height<=1080]/"
                    "best"
                ),

                "outtmpl": str(source),

                "merge_output_format": "mp4",

                "noplaylist": True,

                "quiet": True,

                "no_warnings": True,

                # Current yt-dlp YouTube recommendation:
                # use mweb with a PO-token provider.
                "extractor_args": {
                    "youtube": {
                        "player_client": [
                            "mweb"
                        ]
                    },

                    "youtubepot-bgutilhttp": {
                        "base_url": (
                            "http://127.0.0.1:4416"
                        )
                    },
                },

                # Deno is the JS runtime for yt-dlp EJS.
                "js_runtimes": {
                    "deno": deno_path
                },
            }

            st.write(
                "🔗 Connecting to YouTube..."
            )

            # ------------------------------------------------
            # Download
            # ------------------------------------------------

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        st.success(
            "✅ Video downloaded successfully."
        )

        # ----------------------------------------------------
        # Find downloaded video
        # ----------------------------------------------------

        if not source.exists():

            candidates = list(
                work.glob("*")
            )

            video_candidates = [
                p
                for p in candidates
                if p.suffix.lower()
                in [
                    ".mp4",
                    ".webm",
                    ".mkv",
                    ".mov",
                    ".m4a",
                ]
            ]

            if video_candidates:
                source = video_candidates[0]

        if not source.exists():
            raise RuntimeError(
                "The video was downloaded, but the "
                "video file could not be found."
            )

        # ----------------------------------------------------
        # Get duration
        # ----------------------------------------------------

        duration = get_duration(source)

        if duration <= 0:
            raise RuntimeError(
                "Could not read the video duration."
            )

        st.write(
            f"🎥 Video duration: "
            f"{duration:.1f} seconds"
        )

        # ----------------------------------------------------
        # Create output directory
        # ----------------------------------------------------

        output_folder = Path("output")

        output_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ----------------------------------------------------
        # Calculate clip length
        # ----------------------------------------------------

        clip_length_real = min(
            float(clip_length),
            duration,
        )

        max_start = max(
            0,
            duration - clip_length_real,
        )

        # ----------------------------------------------------
        # Select clip positions
        # ----------------------------------------------------

        if number_of_clips == 1:

            starts = [0]

        else:

            starts = [
                max_start * i / (number_of_clips - 1)
                for i in range(number_of_clips)
            ]

        # ----------------------------------------------------
        # Generate clips
        # ----------------------------------------------------

        st.subheader(
            "✂️ Creating Short Clips"
        )

        generated_clips = []

        progress = st.progress(0)

        for index, start in enumerate(starts):

            clip_path = (
                work
                / f"zozo_clip_{index + 1}.mp4"
            )

            result = make_clip(
                source,
                clip_path,
                start,
                clip_length_real,
            )

            if result.returncode != 0:

                error_text = (
                    result.stderr[-4000:]
                    if result.stderr
                    else "Unknown FFmpeg error."
                )

                raise RuntimeError(
                    error_text
                )

            final_path = (
                output_folder
                / f"zozo_clip_{index + 1}.mp4"
            )

            shutil.copy2(
                clip_path,
                final_path,
            )

            generated_clips.append(
                final_path
            )

            progress.progress(
                (index + 1) / len(starts)
            )

        # ----------------------------------------------------
        # Show results
        # ----------------------------------------------------

        st.success(
            f"🎉 Created {len(generated_clips)} clip(s)!"
        )

        st.divider()

        st.subheader(
            "🎬 Your ZOZO AI Clips"
        )

        for index, clip_path in enumerate(
            generated_clips,
            start=1,
        ):

            st.markdown(
                f"### Clip {index}"
            )

            st.video(
                str(clip_path)
            )

            with open(
                clip_path,
                "rb",
            ) as video_file:

                st.download_button(
                    label=(
                        f"⬇️ Download Clip {index}"
                    ),

                    data=video_file,

                    file_name=(
                        f"zozo_ai_clip_{index}.mp4"
                    ),

                    mime="video/mp4",

                    use_container_width=True,

                    key=f"download_{index}",
                )

        # ----------------------------------------------------
        # Features
        # ----------------------------------------------------

        st.divider()

        st.subheader(
            "✨ ZOZO AI Features"
        )

        st.write(
            "✅ YouTube video input"
        )

        st.write(
            "✅ Up to 1080p source video"
        )

        st.write(
            "✅ Multiple short clips"
        )

        st.write(
            "✅ 9:16 vertical format"
        )

        st.write(
            "✅ Automatic video cropping"
        )

        st.write(
            "✅ Clip preview"
        )

        st.write(
            "✅ Download generated clips"
        )

        st.info(
            "🚀 More AI features such as automatic "
            "captions, AI-selected viral moments, "
            "speaker tracking, and AI-generated "
            "titles/descriptions can be added next."
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
