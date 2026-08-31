import os
import subprocess
import logging
import json
import asyncio
import re
from typing import Optional, List, Dict, Any
import imageio_ffmpeg
import edge_tts

logger = logging.getLogger("video_editor")

def get_ffmpeg_binary() -> str:
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

def generate_ass_subtitles(segments_or_words: List[Dict[str, Any]], ass_path: str):
    """
    Generates Advanced SubStation Alpha (.ass) subtitles matching CapCut / Hormozi style:
    - Bold uppercase font
    - Cyan / Aqua highlight on key words (&H00FFE500&)
    - Thick black outline (&H00000000&) & Drop Shadow
    """
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,6,2,30,30,520,1

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

    for item in segments_or_words:
        text = item.get("text", "").strip().upper()
        if not text:
            continue
        words = text.split()
        if not words:
            continue

        start_sec = item.get("start", 0.0)
        end_sec = item.get("end", start_sec + 2.0)
        
        chunk_size = 2
        duration = max(end_sec - start_sec, 0.5)
        num_chunks = (len(words) + chunk_size - 1) // chunk_size
        chunk_dur = duration / max(num_chunks, 1)

        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            c_start = start_sec + (i // chunk_size) * chunk_dur
            c_end = min(end_sec, c_start + chunk_dur)
            
            # Cyan highlight on first word, White on remaining
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
    """Transcribes video audio using Whisper."""
    try:
        import whisper
        logger.info("Checking audio speech content with Whisper...")
        model = whisper.load_model("tiny")
        result = model.transcribe(video_path, fp16=False)
        return result.get("segments", [])
    except Exception as e:
        logger.warning(f"Whisper transcription skipped: {e}")
        return []

def generate_story_script(title: str) -> str:
    """Generates an engaging, viral wildlife/shorts story from the video title."""
    clean_title = re.sub(r"#\S+", "", title).strip()
    if not clean_title or len(clean_title) < 5:
        clean_title = "This incredible moment in the wild"

    templates = [
        f"You won't believe what happens here! {clean_title}. Nature always has a way to surprise us. Watch closely until the end!",
        f"Did you know this about wildlife? {clean_title}. In the animal kingdom, survival is everything. Look at this incredible power!",
        f"Wait till you see this! {clean_title}. One of the most fascinating wildlife moments ever captured. Drop a like if you love animals!"
    ]
    import random
    return random.choice(templates)

async def create_tts_voiceover(text: str, output_path: str, voice: str = "en-US-ChristopherNeural"):
    """Generates ultra-realistic neural AI voiceover using edge-tts."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_ai_voiceover(title: str, voice_output_path: str) -> List[Dict[str, Any]]:
    """Generates narrative story voiceover and estimates word timings."""
    script = generate_story_script(title)
    logger.info(f"Generating AI narrative voiceover: '{script}'")
    
    asyncio.run(create_tts_voiceover(script, voice_output_path))
    
    words = script.split()
    # Average speaking rate ~3.5 words per second
    total_est_time = len(words) / 3.2
    
    segments = []
    chunk_size = 4
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size])
        start = (i / len(words)) * total_est_time
        end = ((i + chunk_size) / len(words)) * total_est_time
        segments.append({"text": chunk, "start": start, "end": end})
    
    return segments

def apply_anti_copyright_and_captions(
    input_video: str,
    output_video: str,
    title: str = "",
    enable_filter: bool = True,
    enable_captions: bool = True,
    enable_ai_voice_if_silent: bool = True
) -> str:
    """
    Applies complete AI Video Transformation:
    1. Voice Detection: If video has no speech, generates engaging AI voiceover story + BGM.
    2. Dynamic Captions: Word-by-word highlighted subtitles in Cyan/White style.
    3. Video Filters: 2% scale zoom + Color Grading + Unsharp filter (defeats Content-ID pixel hash).
    4. Audio Filters: Micro pitch & EQ shift (defeats Content-ID audio hash).
    """
    ffmpeg_exe = get_ffmpeg_binary()
    ass_path = input_video.replace(".mp4", "_sub.ass")
    voice_path = input_video.replace(".mp4", "_ai_voice.mp3")

    # 1. Check existing speech in video
    segments = []
    if enable_captions:
        segments = transcribe_audio_whisper(input_video)

    has_generated_voice = False
    # If no speech detected, generate AI story voiceover
    if not segments and enable_ai_voice_if_silent:
        logger.info("No speech detected in video. Automatically creating AI story voiceover...")
        segments = generate_ai_voiceover(title, voice_path)
        has_generated_voice = os.path.exists(voice_path)

    has_subtitles = False
    if segments:
        generate_ass_subtitles(segments, ass_path)
        has_subtitles = os.path.exists(ass_path)

    # 2. Build Video Filter Complex
    video_filters = []
    if enable_filter:
        # Micro-crop/zoom to defeat pixel hash (crop 98% center, scale to 1080x1920)
        video_filters.append("crop=in_w*0.98:in_h*0.98,scale=1080:1920:flags=lanczos")
        # Color grading & contrast filter
        video_filters.append("eq=contrast=1.06:brightness=0.01:saturation=1.10")
        # Sharpen filter
        video_filters.append("unsharp=3:3:0.6:3:3:0.3")

    if has_subtitles:
        escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")
        video_filters.append(f"subtitles='{escaped_ass}'")

    vf_arg = ",".join(video_filters) if video_filters else "scale=1080:1920"

    # 3. Build Audio Filter & Mixing
    if has_generated_voice:
        # Mix background audio at low volume (-18dB) with crisp loud AI voiceover
        cmd = [
            ffmpeg_exe, "-y",
            "-i", input_video,
            "-i", voice_path,
            "-filter_complex",
            f"[0:v]{vf_arg}[v];[0:a]volume=0.2[bgm];[1:a]volume=1.2,asetrate=44100*1.01,atempo=1/1.01[voice];[bgm][voice]amix=inputs=2:duration=first[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            output_video
        ]
    else:
        audio_filters = ["asetrate=44100*1.015,atempo=1/1.015,equalizer=f=1000:t=q:w=1:g=1.2"]
        af_arg = ",".join(audio_filters)
        cmd = [
            ffmpeg_exe, "-y",
            "-i", input_video,
            "-vf", vf_arg,
            "-af", af_arg,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            output_video
        ]

    logger.info(f"Rendering transformed video with Anti-Copyright filters, AI voiceover & captions...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Clean up temp files
    for temp_f in [ass_path, voice_path]:
        if os.path.exists(temp_f):
            try:
                os.remove(temp_f)
            except Exception:
                pass

    if result.returncode == 0 and os.path.exists(output_video):
        logger.info(f"Video editing successfully completed: {output_video}")
        return output_video
    else:
        logger.error(f"FFmpeg video processing failed: {result.stderr}")
        return input_video
