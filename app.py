import streamlit as st
import subprocess
import os

st.set_page_config(page_title="ZOZO AI", page_icon="🤖")

st.title("🤖 ZOZO AI")
st.write("Turn YouTube videos into short clips.")

youtube_url = st.text_input(
    "🔗 Paste your YouTube video link",
    placeholder="https://www.youtube.com/watch?v=..."
)

if st.button("🚀 Download Video"):
    if youtube_url.strip():
        os.makedirs("output", exist_ok=True)

        result = subprocess.run(
            ["yt-dlp", "-f", "mp4", "-o", "output/source.%(ext)s", youtube_url],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            st.success("Video downloaded successfully! ✅")
        else:
            st.error("Could not download the video.")
            st.code(result.stderr)

st.divider()

st.subheader("✨ ZOZO AI will eventually do")

st.write("🎯 Find the best moments")
st.write("✂️ Create multiple short videos")
st.write("📱 Convert to 9:16 Shorts")
st.write("📝 Add automatic captions")
st.write("💡 Generate titles and descriptions")
st.write("👀 Preview and choose your clips")
st.write("⬇️ Download your selected videos")

st.caption("ZOZO AI • Personal Edition")
