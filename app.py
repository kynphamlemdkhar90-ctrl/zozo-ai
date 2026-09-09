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
# ============================================================

st.set_page_config(
    page_title="ZOZO AI",
    page_icon="🤖",
    layout="centered",
)

ZOZO_HOME = Path.home() / ".zozo_ai"

DENO_VERSION = "2.9.5"
BGUTIL_VERSION = "1.3.2"

DENO_DIR = ZOZO_HOME / "deno"
DENO_BIN = DENO_DIR / "deno"

BGUTIL_DIR = ZOZO_HOME / "bgutil-ytdlp-pot-provider"

BGUTIL_PORT = 4416


# ============================================================
# HELPERS
# ============================================================

def run_command(command, cwd=None, timeout=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            message or "Command failed."
        )

    return result.stdout.strip()


def valid_youtube(url):
    if not url:
        return False

    patterns = [
        r"https?://(www\.)?youtube\.com/watch\?v=",
        r"https?://youtu\.be/",
        r"https?://(www\.)?youtube\.com/shorts/",
        r"https?://(www\.)?youtube\.com/live/",
    ]

    return any(
        re.search(pattern, url)
        for pattern in patterns
    )


def get_duration(filename):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(filename),
    ]

    output = run_command(command)

    try:
        return float(output)
    except Exception:
        return 0.0


# ============================================================
# DENO
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
    ZOZO_HOME.mkdir(
        parents=True,
        exist_ok=True,
    )

    DENO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if DENO_BIN.exists():
        return str(DENO_BIN)

    asset = get_deno_asset()

    url = (
        "https://github.com/denoland/deno/releases/"
        f"download/v{DENO_VERSION}/{asset}"
    )

    zip_path = DENO_DIR / asset

    try:
        urllib.request.urlretrieve(
            url,
            zip_path,
        )

        with zipfile.ZipFile(
            zip_path,
            "r",
        ) as archive:
            archive.extractall(
                DENO_DIR
            )

        zip_path.unlink(
            missing_ok=True
        )

        if not DENO_BIN.exists():
            raise RuntimeError(
                "Deno executable was not found."
            )

        DENO_BIN.chmod(0o755)

        return str(DENO_BIN)

    except Exception as error:
        raise RuntimeError(
            f"Could not install Deno: {error}"
        )


# ============================================================
# BGUTIL PO TOKEN PROVIDER
# ============================================================

def provider_is_running():
    try:
        with socket.create_connection(
            (
                "127.0.0.1",
                BGUTIL_PORT,
            ),
            timeout=1,
        ):
            return True

    except Exception:
        return False


def install_bgutil_source():

    if (
        BGUTIL_DIR.exists()
        and (BGUTIL_DIR / "server").exists()
    ):
        return

    ZOZO_HOME.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive_path = (
        ZOZO_HOME
        / (
            "bgutil-ytdlp-pot-provider-"
            f"{BGUTIL_VERSION}.zip"
        )
    )

    url = (
        "https://github.com/Brainicism/"
        "bgutil-ytdlp-pot-provider/"
        f"archive/refs/tags/{BGUTIL_VERSION}.zip"
    )

    urllib.request.urlretrieve(
        url,
        archive_path,
    )

    extract_dir = (
        ZOZO_HOME
        / "bgutil_extract"
    )

    if extract_dir.exists():
        shutil.rmtree(
            extract_dir
        )

    extract_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(
        archive_path,
        "r",
    ) as archive:
        archive.extractall(
            extract_dir
        )

    folders = [
        item
        for item in extract_dir.iterdir()
        if item.is_dir()
    ]

    if not folders:
        raise RuntimeError(
            "Could not find bgutil provider source."
        )

    source_folder = folders[0]

    if BGUTIL_DIR.exists():
        shutil.rmtree(
            BGUTIL_DIR
        )

    shutil.copytree(
        source_folder,
        BGUTIL_DIR,
    )

    archive_path.unlink(
        missing_ok=True
    )

    shutil.rmtree(
        extract_dir,
        ignore_errors=True,
    )


def start_bgutil_provider(
    deno_path
):

    if provider_is_running():
        return

    install_bgutil_source()

    server_dir = (
        BGUTIL_DIR
        / "server"
    )

    if not server_dir.exists():
        raise RuntimeError(
            "bgutil server directory was not found."
        )

    node_modules = (
        server_dir
        / "node_modules"
    )

    if not node_modules.exists():

        run_command(
            [
                deno_path,
                "install",
                "--allow-scripts=npm:canvas",
                "--frozen",
            ],
            cwd=server_dir,
            timeout=600,
        )

    command = [
        deno_path,
        "run",
        "--allow-env",
        "--allow-net",
        "--allow-ffi=.",
        "--allow-read=.",
        "../src/main.ts",
    ]

    subprocess.Popen(
        command,
        cwd=node_modules,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(30):

        if provider_is_running():
            return

        time.sleep(1)

    raise RuntimeError(
        "YouTube PO-token provider did not start."
    )


@st.cache_resource
def setup_youtube_runtime():

    deno_path = install_deno()

    start_bgutil_provider(
        deno_path
    )

    return deno_path


# ============================================================
# DOWNLOAD WITH MWEB + PO TOKEN
# ============================================================

def download_with_mweb(
    youtube_url,
    source,
    deno_path,
):

    opts = {
        "format": (
            "bv*[height<=1080]+ba/"
            "b[height<=1080]/best"
        ),

        "outtmpl": str(source),

        "merge_output_format": "mp4",

        "noplaylist": True,

        "quiet": True,

        "no_warnings": True,

        "retries": 3,

        "fragment_retries": 3,

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

        "js_runtimes": {
            "deno": {
                "path": deno_path
            }
        },
    }

    with yt_dlp.YoutubeDL(
        opts
    ) as ydl:

        ydl.download(
            [youtube_url]
        )


# ============================================================
# FALLBACK: WEB SAFARI / HLS
# ============================================================

def download_with_web_safari(
    youtube_url,
    source,
    deno_path,
):

    opts = {
        "format": (
            "best[protocol*=m3u8]/"
            "best"
        ),

        "outtmpl": str(source),

        "merge_output_format": "mp4",

        "noplaylist": True,

        "quiet": True,

        "no_warnings": True,

        "retries": 5,

        "fragment_retries": 5,

        "extractor_args": {
            "youtube": {
                "player_client": [
                    "web_safari"
                ]
            }
        },

        "js_runtimes": {
            "deno": {
                "path": deno_path
            }
        },
    }

    with yt_dlp.YoutubeDL(
        opts
    ) as ydl:

        ydl.download(
            [youtube_url]
        )


# ============================================================
# CLIP CREATION
# ============================================================

def make_clip(
    source,
    output_file,
    start_time,
    clip_length,
):

    command = [
        "ffmpeg",
        "-y",

        "-ss",
        str(start_time),

        "-i",
        str(source),

        "-t",
        str(clip_length),

        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:"
            "(ow-iw)/2:(oh-ih)/2"
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

        str(output_file),
    ]

    run_command(
        command,
        timeout=1200,
    )


# ============================================================
# UI
# ============================================================

st.title(
    "🤖 ZOZO AI"
)

st.write(
    "Turn long YouTube videos into engaging short clips."
)

st.divider()


youtube_url = st.text_input(
    "🔗 YouTube Video URL",
    placeholder=(
        "Paste a public YouTube video link here"
    ),
)

st.caption(
    "ZOZO AI works with normal public YouTube videos."
)


clip_length = st.selectbox(
    "⏱️ Clip Length",
    [15, 30, 45, 60],
    index=1,
)


number_of_clips = st.slider(
    "🎬 Number of Clips",
    min_value=1,
    max_value=10,
    value=1,
)


generate = st.button(
    "🚀 Generate Clips",
    type="primary",
    use_container_width=True,
)


# ============================================================
# PROCESS
# ============================================================

if generate:

    if not youtube_url.strip():

        st.error(
            "Please enter a YouTube video URL."
        )

        st.stop()


    if not valid_youtube(
        youtube_url.strip()
    ):

        st.error(
            "Please enter a valid public YouTube URL."
        )

        st.stop()


    work = Path(
        tempfile.mkdtemp(
            prefix="zozo_ai_"
        )
    )

    source = (
        work
        / "source.mp4"
    )

    output_dir = (
        work
        / "clips"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    try:

        st.info(
            "🤖 ZOZO AI is preparing..."
        )

        status = st.empty()

        status.info(
            "⚙️ Preparing YouTube download system..."
        )

        deno_path = (
            setup_youtube_runtime()
        )

        status.success(
            "✅ YouTube PO-token provider is ready."
        )

        status.info(
            "🔗 Connecting to YouTube..."
        )


        # ----------------------------------------------------
        # FIRST METHOD: MWEB + PO TOKEN
        # ----------------------------------------------------

        first_error = None

        try:

            download_with_mweb(
                youtube_url.strip(),
                source,
                deno_path,
            )

        except Exception as error:

            first_error = error


        # ----------------------------------------------------
        # SECOND METHOD: WEB SAFARI / HLS
        # ----------------------------------------------------

        if not source.exists():

            status.warning(
                "⚠️ YouTube rejected the first "
                "download method. Trying a safe "
                "HLS fallback..."
            )

            try:

                download_with_web_safari(
                    youtube_url.strip(),
                    source,
                    deno_path,
                )

            except Exception as second_error:

                raise RuntimeError(
                    "YouTube rejected both download "
                    "methods.\n\n"
                    f"First method:\n{first_error}\n\n"
                    f"Fallback method:\n{second_error}"
                )


        # ----------------------------------------------------
        # CHECK VIDEO
        # ----------------------------------------------------

        if not source.exists():

            candidates = list(
                work.glob("source.*")
            )

            if candidates:
                source = candidates[0]


        if not source.exists():

            raise RuntimeError(
                "The YouTube video was downloaded "
                "but the video file could not be found."
            )


        status.success(
            "✅ YouTube video downloaded successfully!"
        )


        duration = get_duration(
            source
        )


        if duration <= 0:

            raise RuntimeError(
                "Could not read the video duration."
            )


        actual_clip_length = min(
            int(clip_length),
            int(duration),
        )


        # ----------------------------------------------------
        # CLIP POSITIONS
        # ----------------------------------------------------

        if duration <= actual_clip_length:

            start_positions = [
                0
                for _ in range(
                    number_of_clips
                )
            ]

        else:

            available = int(
                duration
                - actual_clip_length
            )

            if number_of_clips == 1:

                start_positions = [
                    max(
                        0,
                        available // 2,
                    )
                ]

            else:

                start_positions = []

                for i in range(
                    number_of_clips
                ):

                    position = int(
                        available
                        * i
                        / max(
                            1,
                            number_of_clips - 1,
                        )
                    )

                    start_positions.append(
                        position
                    )


        # ----------------------------------------------------
        # CREATE CLIPS
        # ----------------------------------------------------

        st.write(
            "🎬 Creating your clips..."
        )

        progress = st.progress(
            0
        )

        created_clips = []


        for index, start_time in enumerate(
            start_positions,
            start=1,
        ):

            output_file = (
                output_dir
                / f"zozo_clip_{index}.mp4"
            )

            make_clip(
                source,
                output_file,
                start_time,
                actual_clip_length,
            )

            created_clips.append(
                output_file
            )

            progress.progress(
                index
                / len(start_positions)
            )


        # ----------------------------------------------------
        # RESULTS
        # ----------------------------------------------------

        status.success(
            "🎉 ZOZO AI finished creating your clips!"
        )

        st.divider()

        st.subheader(
            "🎥 Your ZOZO AI Clips"
        )


        for index, clip in enumerate(
            created_clips,
            start=1,
        ):

            st.markdown(
                f"### Clip {index}"
            )

            st.video(
                str(clip)
            )

            with open(
                clip,
                "rb",
            ) as video_file:

                st.download_button(
                    label=(
                        f"⬇️ Download Clip "
                        f"{index}"
                    ),

                    data=video_file.read(),

                    file_name=(
                        f"zozo_clip_{index}.mp4"
                    ),

                    mime="video/mp4",

                    use_container_width=True,
                )


        st.success(
            "❤️ Your clips are ready!"
        )

        st.info(
            "Automatic captions, AI-selected "
            "viral moments, speaker tracking, "
            "and AI-generated titles can be "
            "added to ZOZO AI next."
        )


    except Exception as error:

        st.error(
            "❌ ZOZO AI could not process this video."
        )

        st.code(
            str(error)
        )


    finally:

        shutil.rmtree(
            work,
            ignore_errors=True,
)
