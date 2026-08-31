import os
import subprocess
import logging
import json
from typing import Optional, List, Dict, Any
import imageio_ffmpeg

logger = logging.getLogger("video_editor")

def get_ffmpeg_binary() -> str:
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

def generate_ass_subtitles(whisper_segments: List[Dict[str, Any]], ass_path: str, style_mode: str = "cyan"):
    """
    Generates Advanced SubStation Alpha (.ass) subtitles matching CapCut / Hormozi style:
    - Bold uppercase font
    - Cyan / Aqua highlight on key words
    - Thick black outline & drop shadow
    """
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,6,2,30,30,500,1
Style: Highlight,Arial,68,&H00FFE500,&H000000FF,&H00000000,&H80000000,-1,0,0,0,105,105,2,0,1,9,7,2,30,30,500,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    def format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds - int(seconds)) * 100)
        return f"{h:01d}:{m:02d}:{s:02d}.{cs:02d}"

    for seg in whisper_segments:
        text = seg.get("text", "").strip().upper()
        if not text:
            continue
        words = text.split()
        if not words:
            continue

        start_sec = seg.get("start", 0.0)
        end_sec = seg.get("end", start_sec + 2.0)
        
        # Split into chunks of 2-3 words for high energy dynamic shorts pacing
        chunk_size = 3
        duration = (end_sec - start_sec)
        num_chunks = (len(words) + chunk_size - 1) // chunk_size
        chunk_dur = duration / max(num_chunks, 1)

        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            c_start = start_sec + (i // chunk_size) * chunk_dur
            c_end = min(end_sec, c_start + chunk_dur)
            
            # Highlight first word with Cyan/Aqua (#00E5FF in BGR: &H00FFE500&)
            if len(chunk_words) > 1:
                highlighted_text = f"{{\\c&H00FFE500&}}{chunk_words[0]}{{\\c&H00FFFFFF&}} {' '.join(chunk_words[1:])}"
            else:
                highlighted_text = f"{{\\c&H00FFE500&}}{chunk_words[0]}"

            events.append(
                f"Dialogue: 0,{format_time(c_start)},{format_time(c_end)},Default,,0,0,0,,{highlighted_text}"
            )

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")

def transcribe_audio_whisper(video_path: str) -> List[Dict[str, Any]]:
    """Transcribes video audio using OpenAI Whisper (tiny model for fast runner execution)."""
    try:
        import whisper
        logger.info("Transcribing audio for dynamic captions with Whisper...")
        model = whisper.load_model("tiny")
        result = model.transcribe(video_path, fp16=False)
        return result.get("segments", [])
    except Exception as e:
        logger.warning(f"Whisper transcription failed or not available: {e}")
        return []

def apply_anti_copyright_and_captions(
    input_video: str,
    output_video: str,
    enable_filter: bool = True,
    enable_captions: bool = True,
    enable_audio_shift: bool = True
) -> str:
    """
    Applies comprehensive Anti-Copyright transformations & dynamic captions:
    1. Video: Micro-crop (1.5% scale zoom) + Color Grading (Contrast, Saturation, Sharpness)
    2. Audio: Micro pitch/speed shift (1.015x) + EQ tweak to alter audio fingerprint
    3. Captions: Hardcoded CapCut/Hormozi style animated subtitles
    """
    ffmpeg_exe = get_ffmpeg_binary()
    ass_path = input_video.replace(".mp4", "_sub.ass")

    # 1. Transcribe & Generate Subtitles if enabled
    has_subtitles = False
    if enable_captions:
        segments = transcribe_audio_whisper(input_video)
        if segments:
            generate_ass_subtitles(segments, ass_path)
            has_subtitles = os.path.exists(ass_path)

    # 2. Build Video Filter Complex
    video_filters = []
    
    if enable_filter:
        # Micro-crop/zoom to defeat pixel hash (crop 98% center, scale back to 1080x1920)
        video_filters.append("crop=in_w*0.98:in_h*0.98,scale=1080:1920:flags=lanczos")
        # Color grading & contrast filter
        video_filters.append("eq=contrast=1.06:brightness=0.01:saturation=1.10")
        # Sharpen filter
        video_filters.append("unsharp=3:3:0.6:3:3:0.3")

    if has_subtitles:
        # Escape path for FFmpeg subtitles filter
        escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")
        video_filters.append(f"subtitles='{escaped_ass}'")

    vf_arg = ",".join(video_filters) if video_filters else "scale=1080:1920"

    # 3. Build Audio Filter
    audio_filters = []
    if enable_audio_shift:
        # Anti-fingerprint micro pitch shift + EQ modification
        audio_filters.append("asetrate=44100*1.015,atempo=1/1.015,equalizer=f=1000:t=q:w=1:g=1.2")
    af_arg = ",".join(audio_filters) if audio_filters else "aformat=channel_layouts=stereo"

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", input_video,
        "-vf", vf_arg,
        "-af", af_arg,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18", # High visual quality
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        output_video
    ]

    logger.info(f"Rendering transformed video with Anti-Copyright filters & captions...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Clean up temp ass subtitle file
    if os.path.exists(ass_path):
        try:
            os.remove(ass_path)
        except Exception:
            pass

    if result.returncode == 0 and os.path.exists(output_video):
        logger.info(f"Video editing successfully completed: {output_video}")
        return output_video
    else:
        logger.error(f"FFmpeg video processing failed: {result.stderr}")
        return input_video # Fallback to original video if processing fails
