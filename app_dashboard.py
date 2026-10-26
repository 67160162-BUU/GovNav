#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
GovNav (Government Navigator) - Complete Interactive Web Kiosk & Dashboard
=============================================================================
รันด้วยคำสั่ง:
    streamlit run app_dashboard.py --server.address 0.0.0.0 --server.port 8501

คุณสมบัติครบถ้วนพร้อมใช้งานจริง (Resilient Production-Ready Kiosk):
1. รองรับเสียงพูดภาษาไทย Offline 100% ด้วย VachanaTTS (VITS + Piper ONNX)
   - ทำงานได้แม้ไฟล์ใน core/ จะเป็นเวอร์ชันเก่าหรือใหม่ (Zero-AttributeError)
   - ใช้โมเดลเสียงผู้หญิงที่ 2 (th_f_2) คู่กับบุคลิกเจ้าหน้าที่ประชาสัมพันธ์หญิง (ค่ะ/นะคะ) ปรับความเร็วและความดังได้
   - มีเครื่องเล่นเสียงบนหน้าเว็บ (Web Audio Player) + รองรับลำโพงบอร์ด RPi4 (aplay)
2. ประมวลผลคำถามภาษาชาวบ้านด้วย On-Device Qwen (.gguf) + Smart Keyword RAG
3. แสดงแผนที่นำทางครบ 2 รูปแบบ: แผนผังกราฟิก (.png) และแผนที่เส้นขีด (ASCII Slip Map)
4. เชื่อมต่อและแสดงผลเซนเซอร์ IoT แบบสด (Ultrasonic, DHT22, ไฟ LED ชี้ทาง, กริ่งเรียกเจ้าหน้าที่)
5. ระบบวิเคราะห์สถิติและประวัติผู้มาติดต่อราชการจากฐานข้อมูล SQLite พร้อมส่งออก CSV
=============================================================================
"""

import os
import re
import io
import csv
import sys
import json
import time
import glob
import shutil
import sqlite3
import hashlib
import inspect
import subprocess
import importlib.util
import streamlit as st

import config
from core.llm_navigator import GovNavLLM
from core.iot_hardware import GovNavIoTHardware
from core.tts_speaker import GovNavTTSSpeaker
from core.db_logger import GovNavDBLogger

# ดึงค่าตั้งค่าแบบปลอดภัย (รองรับทั้ง config.py เก่าและใหม่)
BASE_DIR = getattr(config, "BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = getattr(config, "DATA_DIR", os.path.join(BASE_DIR, "data"))
EVAL_REPORT_JSON = os.path.join(DATA_DIR, "eval_report.json")
EVAL_REPORT_CSV = os.path.join(DATA_DIR, "eval_report_details.csv")
LLM_CACHE_JSON = os.path.join(DATA_DIR, "llm_query_cache.json")
AUDIO_OUT_DIR = getattr(config, "AUDIO_OUT_DIR", os.path.join(BASE_DIR, "assets", "audio_out"))
AUDIO_CACHE_DIR = getattr(config, "AUDIO_CACHE_DIR", os.path.join(BASE_DIR, "assets", "audio_cache"))
VOICES_DIR = getattr(config, "VOICES_DIR", os.path.join(BASE_DIR, "voices"))
SQLITE_DB_PATH = getattr(config, "SQLITE_DB_PATH", os.path.join(BASE_DIR, "data", "govnav_logs.db"))
GPIO_PINS = getattr(config, "GPIO_PINS", {})
APPROACH_DISTANCE_CM = getattr(config, "APPROACH_DISTANCE_CM", 150.0)
TTS_SPEED = float(getattr(config, "TTS_SPEED", 1.0))
TTS_VOLUME = float(getattr(config, "TTS_VOLUME", 1.0))
AVAILABLE_VOICES = getattr(
    config,
    "AVAILABLE_VOICES",
    {
        "th_f_2": "👩 หญิง 2 (th_f_2) — สดใส สุภาพ ชัดเจน",
    },
)
raw_tts_model = getattr(config, "TTS_MODEL", "th_f_2")
TTS_MODEL = raw_tts_model if raw_tts_model in AVAILABLE_VOICES else "th_f_2"

# -----------------------------------------------------------------------------
# ตั้งค่าหน้าเพจ Streamlit
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="GovNav - ตู้ผู้ช่วยนำทางศูนย์ราชการอัจฉริยะ",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

_BTN_PARAMS = inspect.signature(st.button).parameters
STRETCH_KW = {"width": "stretch"} if "width" in _BTN_PARAMS else {"use_container_width": True}

st.markdown(
    """
    <style>
    .govnav-hero {
        background: linear-gradient(135deg, #0b2239 0%, #163d66 60%, #1e4e79 100%);
        color: #ffffff;
        padding: 1.5rem 2rem;
        border-radius: 16px;
        border-bottom: 4px solid #e0b341;
        box-shadow: 0 6px 20px rgba(11, 34, 57, 0.18);
        margin-bottom: 1.2rem;
    }
    .govnav-hero h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
        color: #ffffff !important;
    }
    .govnav-hero p {
        margin: 0.35rem 0 0.8rem 0;
        font-size: 1.05rem;
        color: #dbeafe;
    }
    .badge-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        margin-top: 0.5rem;
    }
    .gov-badge {
        background: rgba(255, 255, 255, 0.14);
        border: 1px solid rgba(255, 255, 255, 0.25);
        color: #f8fafc;
        padding: 0.28rem 0.75rem;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 500;
    }
    .gov-badge-gold {
        background: rgba(224, 179, 65, 0.22);
        border: 1px solid #e0b341;
        color: #fef08a;
        padding: 0.28rem 0.75rem;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .ai-reply-card {
        background: linear-gradient(90deg, #eff6ff 0%, #f8fafc 100%);
        border-left: 6px solid #1d4ed8;
        border-radius: 12px;
        padding: 1.15rem 1.4rem;
        margin: 0.75rem 0 1rem 0;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
        color: #0f172a;
        font-size: 1.12rem;
        line-height: 1.65;
    }
    .led-banner {
        background: #ecfdf5;
        border: 1.5px solid #10b981;
        border-radius: 12px;
        padding: 0.8rem 1.2rem;
        color: #065f46;
        font-weight: 600;
        font-size: 1.02rem;
        margin-bottom: 1rem;
    }
    .room-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1.2rem 1.35rem;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
        margin-bottom: 1rem;
        color: #1e293b;
    }
    .report-box {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 1.4rem 1.6rem;
        color: #0f172a;
        margin-top: 0.6rem;
    }
    table.exp-table {
        width: 100%;
        border-collapse: collapse;
        margin: 0.8rem 0 1.2rem 0;
        font-size: 1rem;
    }
    table.exp-table thead tr {
        background-color: #17365d;
        color: #ffffff;
    }
    table.exp-table th {
        padding: 12px 14px;
        font-weight: 700;
        text-align: center;
        border: none;
    }
    table.exp-table th:first-child {
        text-align: left;
    }
    table.exp-table td {
        padding: 11px 14px;
        color: #1e293b;
        border-bottom: 1px solid #e2e8f0;
        text-align: center;
    }
    table.exp-table td:first-child {
        text-align: left;
        font-weight: 500;
    }
    table.exp-table tbody tr:nth-child(even) {
        background-color: #f1f5f9;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# ฟังก์ชัน Wrapper แบบปลอดภัย (ป้องกัน AttributeError กรณีไฟล์ย่อยใน core/ เป็นรุ่นเก่า)
# -----------------------------------------------------------------------------
def create_tts_instance():
    init_params = inspect.signature(GovNavTTSSpeaker.__init__).parameters
    if "voice_name" in init_params:
        return GovNavTTSSpeaker(enabled=True, voice_name=TTS_MODEL, volume=TTS_VOLUME, speed=TTS_SPEED)
    return GovNavTTSSpeaker(enabled=True)


def safe_tts_status(tts_obj) -> dict:
    if hasattr(tts_obj, "get_engine_status"):
        return tts_obj.get_engine_status()
    has_vachana = importlib.util.find_spec("vachanatts") is not None
    os.makedirs(VOICES_DIR, exist_ok=True)
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    models = [os.path.basename(p).replace(".onnx", "") for p in glob.glob(os.path.join(VOICES_DIR, "*.onnx"))]
    caches = len(glob.glob(os.path.join(AUDIO_CACHE_DIR, "*.wav")))
    return {
        "ready": True,
        "vachanatts_installed": has_vachana,
        "engine_name": "VachanaTTS (VITS ONNX Offline)" if has_vachana else "Fallback TTS",
        "active_voice": TTS_MODEL,
        "downloaded_voices": sorted(models),
        "cached_audio_count": caches,
        "last_engine_used": getattr(tts_obj, "last_engine_used", "VachanaTTS"),
    }


def _normalize_female_text(text: str) -> str:
    if not text:
        return text
    text = text.replace("ครับผม", "ค่ะ").replace("นะครับ", "นะคะ")
    text = text.replace("ไหมครับ", "ไหมคะ").replace("ไหนครับ", "ไหนคะ")
    text = text.replace("อะไรครับ", "อะไรคะ").replace("หรือครับ", "หรือคะ")
    text = text.replace("กระผม", "ดิฉัน").replace("ผมขอ", "ดิฉันขอ")
    return text.replace("ครับ", "ค่ะ")


def safe_navigate(nav_obj, user_query: str, bypass_cache: bool = False) -> dict:
    """เรียกใช้ nav_ai.navigate พร้อมระบบแคชคำตอบสำรอง ป้องกัน Qwen สุ่มคำพูดใหม่ทุกครั้งที่กดปุ่มเดิม"""
    norm_q = re.sub(r"\s+", " ", user_query.strip())
    nav_params = inspect.signature(nav_obj.navigate).parameters
    if "bypass_cache" in nav_params:
        res_direct = nav_obj.navigate(norm_q, auto_open_image=False, bypass_cache=bypass_cache)
        if "spoken_response" in res_direct:
            res_direct["spoken_response"] = _normalize_female_text(res_direct["spoken_response"])
        return res_direct

    # กรณี core/llm_navigator.py บนเครื่องยังเป็นไฟล์เก่า ให้เช็กและแคชคำตอบที่ระดับ Dashboard ทันที
    full_cache_file = os.path.join(DATA_DIR, "llm_full_result_cache.json")
    cache_map = {}
    if os.path.exists(full_cache_file):
        try:
            with open(full_cache_file, "r", encoding="utf-8") as cf:
                cache_map = json.load(cf)
        except Exception:
            cache_map = {}

    if (not bypass_cache) and (norm_q in cache_map) and isinstance(cache_map[norm_q], dict):
        cached_res = dict(cache_map[norm_q])
        if "spoken_response" in cached_res:
            cached_res["spoken_response"] = _normalize_female_text(cached_res["spoken_response"])
        cached_res["llm_cache_hit"] = True
        cached_res["llm_time_sec"] = 0.001
        cached_res["map_routing_time_sec"] = 0.001
        cached_res["latency_ms"] = 2.0
        print(f"⚡ [LLM Cache Hit] ใช้คำตอบแคชทันทีสำหรับ: \"{norm_q[:45]}\"", flush=True)
        return cached_res

    t_nav0 = time.perf_counter()
    res = nav_obj.navigate(norm_q, auto_open_image=False)
    if "spoken_response" in res:
        res["spoken_response"] = _normalize_female_text(res["spoken_response"])
    res["llm_cache_hit"] = False
    res.setdefault("llm_time_sec", round(time.perf_counter() - t_nav0, 4))
    res.setdefault("map_routing_time_sec", 0.002)

    if not bypass_cache:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            cache_map[norm_q] = res
            with open(full_cache_file, "w", encoding="utf-8") as cf:
                json.dump(cache_map, cf, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return res


def safe_tts_speak(
    tts_obj,
    text: str,
    output_wav: str,
    play_device: bool,
    voice_name: str,
    speed: float,
    volume: float,
    bypass_cache: bool = False,
) -> str:
    speak_params = inspect.signature(tts_obj.speak).parameters
    if "bypass_cache" in speak_params:
        return tts_obj.speak(
            text,
            output_wav=output_wav,
            play_device=play_device,
            voice_name=voice_name,
            speed=speed,
            volume=volume,
            bypass_cache=bypass_cache,
        )

    # กรณี core/tts_speaker.py บนเครื่องยังเป็นไฟล์เก่า ให้จัดการแคชเสียง .wav และเรียกใช้ VachanaTTS โดยตรงทันที
    t0 = time.perf_counter()
    tts_obj.last_cache_hit = False
    os.makedirs(os.path.dirname(os.path.abspath(output_wav)), exist_ok=True)
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    os.makedirs(VOICES_DIR, exist_ok=True)
    output_wav = os.path.abspath(output_wav)

    clean_text = text.replace("กรุงเทพฯ", "กรุงเทพมหานคร").replace("ฯลฯ", "และอื่นๆ")
    clean_text = clean_text.replace("ปชช.", "ประชาชน").replace("ภ.ด.ส.", "พอดอสอ").replace("ภ.ป.", "พอปอ")
    clean_text = clean_text.replace("น.ส.4", "นอสอสี่").replace("น.ส.3", "นอสอสาม").replace("GovNav", "กอฟแนฟ")
    clean_text = clean_text.replace("ครับผม", "ค่ะ").replace("นะครับ", "นะคะ").replace("ครับ", "ค่ะ")
    clean_text = re.sub(r"ROOM_(\d+)", r"ห้อง \1", clean_text)
    clean_text = re.sub(r"[\(\)\[\]\{\}\"\'\*\#\_\~\|•—–]", " ", clean_text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    key_raw = f"vachana|{voice_name}|{speed:.2f}|{volume:.2f}|{clean_text}"
    cache_path = os.path.join(AUDIO_CACHE_DIR, f"tts_{voice_name}_{hashlib.md5(key_raw.encode('utf-8')).hexdigest()[:16]}.wav")

    if (not bypass_cache) and os.path.exists(cache_path) and os.path.getsize(cache_path) > 512:
        if os.path.abspath(cache_path) != output_wav:
            shutil.copy2(cache_path, output_wav)
        tts_obj.last_cache_hit = True
        tts_obj.last_engine_used = f"Offline Cache ({voice_name})"
        tts_obj.last_tts_time_sec = round(time.perf_counter() - t0, 4)
        print(f"⚡ [TTS Cache Hit] ดึงไฟล์เสียงจากแคชทันที ({os.path.basename(cache_path)}) ใช้เวลา {tts_obj.last_tts_time_sec:.4f}s", flush=True)
    else:
        try:
            if not bypass_cache:
                print(f"🎙️ [VachanaTTS] กำลังสร้างเสียงใหม่และบันทึกลงแคช ({os.path.basename(cache_path)})...", flush=True)
            py_code = (
                "import sys, json; from vachanatts import TTS; d = json.loads(sys.argv[1]); "
                "TTS(d['t'], voice=d['v'], output=d['o'], volume=d['vol'], speed=d['spd'])"
            )
            arg_json = json.dumps({"t": clean_text, "v": voice_name, "o": output_wav, "vol": volume, "spd": speed})
            res_sub = subprocess.run([sys.executable, "-c", py_code, arg_json], cwd=BASE_DIR)
            if res_sub.returncode != 0 or not os.path.exists(output_wav):
                raise RuntimeError(f"vachanatts subprocess exit {res_sub.returncode}")
            if (not bypass_cache) and os.path.exists(output_wav) and os.path.getsize(output_wav) > 512:
                shutil.copy2(output_wav, cache_path)
            tts_obj.last_engine_used = f"VachanaTTS ({voice_name})"
        except Exception:
            if "play_device" in speak_params:
                out_fb = tts_obj.speak(
                    clean_text,
                    output_wav=output_wav,
                    play_device=play_device,
                    voice_name=voice_name,
                    speed=speed,
                    volume=volume,
                )
            else:
                out_fb = tts_obj.speak(clean_text, output_wav=output_wav)
            tts_obj.last_tts_time_sec = round(time.perf_counter() - t0, 4)
            return out_fb
        tts_obj.last_tts_time_sec = round(time.perf_counter() - t0, 4)

    if play_device and os.path.exists(output_wav):
        if sys.platform == "darwin" and shutil.which("afplay"):
            subprocess.Popen(["afplay", output_wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("aplay"):
            subprocess.Popen(["aplay", "-q", output_wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_wav


def safe_db_summary(db_obj) -> dict:
    if hasattr(db_obj, "get_summary_metrics"):
        return db_obj.get_summary_metrics()
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT COUNT(*) as total_visits, ROUND(AVG(latency_ms), 2) as avg_latency_ms, "
                "ROUND(AVG(visitor_distance_cm), 1) as avg_distance_cm FROM navigation_logs"
            ).fetchone()
            top_row = conn.execute(
                "SELECT matched_room_id, department_name, COUNT(*) as cnt FROM navigation_logs "
                "GROUP BY matched_room_id ORDER BY cnt DESC LIMIT 1"
            ).fetchone()
            return {
                "total_visits": row["total_visits"] if row else 0,
                "avg_latency_ms": row["avg_latency_ms"] if (row and row["avg_latency_ms"]) else 0.0,
                "avg_distance_cm": row["avg_distance_cm"] if (row and row["avg_distance_cm"]) else 0.0,
                "top_room_id": top_row["matched_room_id"] if top_row else "-",
                "top_department": top_row["department_name"] if top_row else "ยังไม่มีข้อมูล",
            }
    except Exception:
        return {"total_visits": 0, "avg_latency_ms": 0.0, "avg_distance_cm": 0.0, "top_room_id": "-", "top_department": "-"}


def safe_export_csv(db_obj) -> str:
    if hasattr(db_obj, "export_logs_csv"):
        return db_obj.export_logs_csv()
    logs = db_obj.get_recent_logs(limit=500)
    out = io.StringIO()
    out.write("\ufeff")
    if logs:
        writer = csv.DictWriter(out, fieldnames=list(logs[0].keys()))
        writer.writeheader()
        writer.writerows(logs)
    return out.getvalue()


def safe_clear_logs(db_obj):
    if hasattr(db_obj, "clear_logs"):
        db_obj.clear_logs()
        return
    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        conn.execute("DELETE FROM navigation_logs")
        conn.commit()


# -----------------------------------------------------------------------------
# โหลดโมดูลหลักแบบ Singleton Cache
# -----------------------------------------------------------------------------
@st.cache_resource
def init_services():
    nav = GovNavLLM()
    nav.map_renderer.generate_all_map_images()
    hw = GovNavIoTHardware()
    tts = create_tts_instance()
    db = GovNavDBLogger()
    return nav, hw, tts, db


nav_ai, iot_hw, tts_speaker, db_logger = init_services()


def render_audio_player(wav_path: str, autoplay: bool = False):
    if not wav_path or not os.path.exists(wav_path):
        return
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()
    audio_params = inspect.signature(st.audio).parameters
    if "autoplay" in audio_params:
        st.audio(audio_bytes, format="audio/wav", autoplay=autoplay)
    else:
        st.audio(audio_bytes, format="audio/wav")


def format_led_label(direction_code: str) -> str:
    mapping = {
        "LEFT": "⬅️ ไฟสีเขียวปีกซ้าย (เลี้ยวซ้าย ชั้น 1)",
        "RIGHT": "➡️ ไฟสีเขียวปีกขวา (เลี้ยวขวา ชั้น 1)",
        "STRAIGHT": "⬆️ ไฟสีเขียวตรงกลาง (เดินตรงผ่านโถงกลาง ชั้น 1)",
        "UPSTAIRS_LEFT": "🔼⬅️ ไฟชี้ขึ้นชั้น 2 + เลี้ยวซ้าย",
        "UPSTAIRS_RIGHT": "🔼➡️ ไฟชี้ขึ้นชั้น 2 + เลี้ยวขวา",
        "OFF": "⚪ ปิดสแตนด์บาย (รอผู้มาติดต่อ)",
    }
    return mapping.get(direction_code, f"💡 {direction_code}")


# -----------------------------------------------------------------------------
# รายการปุ่มด่วน 5 ห้องราชการยอดนิยม (ใช้ร่วมกันทั้งปุ่มหน้าจอและระบบแคชล่วงหน้า)
# -----------------------------------------------------------------------------
QUICK_PRESETS = [
    ("🪪 บัตร ปชช. / ทะเบียนบ้าน", "มาทำบัตรประชาชนใหม่ บัตรเดิมหาย และคัดสำเนาทะเบียนบ้าน ต้องไปห้องไหน"),
    ("👵 เบี้ยผู้สูงอายุ / บัตรคนจน", "ยายมาจากต่างอำเภอ จะมาลงทะเบียนเบี้ยคนชราและบัตรสวัสดิการแห่งรัฐ"),
    ("💰 ชำระภาษีที่ดิน / ภาษีป้าย", "มาจ่ายภาษีที่ดินและสิ่งปลูกสร้าง ต้องไปชำระเงินที่ห้องไหน"),
    ("🏡 โอนที่ดิน / ขออนุญาตก่อสร้าง", "มาโอนที่ดินมรดกและขออนุญาตก่อสร้างบ้าน ต้องขึ้นไปชั้นไหน"),
    ("⚖️ ร้องทุกข์ / ปรึกษากฎหมาย", "ต้องการร้องเรียนปัญหาความเดือดร้อนและปรึกษากฎหมายที่ศูนย์ดำรงธรรม"),
]

# -----------------------------------------------------------------------------
# จัดการ Session State เริ่มต้น
# -----------------------------------------------------------------------------
if "query_text" not in st.session_state:
    st.session_state.query_text = QUICK_PRESETS[1][1]
if "nav_result" not in st.session_state:
    st.session_state.nav_result = None
if "sensor_snapshot" not in st.session_state:
    st.session_state.sensor_snapshot = iot_hw.read_environment()
if "latest_audio_file" not in st.session_state:
    st.session_state.latest_audio_file = ""
if "autoplay_next" not in st.session_state:
    st.session_state.autoplay_next = False


def execute_navigation(query_str: str, enable_voice: bool, voice_id: str, speed: float, volume: float, play_os_speaker: bool):
    clean_q = re.sub(r"\s+", " ", query_str.strip())
    if not clean_q:
        return

    sensor_now = st.session_state.sensor_snapshot
    res = safe_navigate(nav_ai, clean_q, bypass_cache=False)
    iot_hw.activate_direction_led(res["direction_code"])
    sensor_now["active_led_direction"] = res["direction_code"]

    llm_sec = float(res.get("llm_time_sec", round(res.get("latency_ms", 0.0) / 1000.0, 4)))
    map_sec = float(res.get("map_routing_time_sec", 0.005))
    tts_sec = 0.0
    tts_cache_hit = False

    if enable_voice:
        out_wav = os.path.join(AUDIO_OUT_DIR, f"reply_{res['room_id']}.wav")
        t_tts0 = time.perf_counter()
        generated_wav = safe_tts_speak(
            tts_speaker,
            res["spoken_response"],
            output_wav=out_wav,
            play_device=play_os_speaker,
            voice_name=voice_id,
            speed=speed,
            volume=volume,
            bypass_cache=False,
        )
        elapsed_tts = round(time.perf_counter() - t_tts0, 4)
        tts_sec = float(getattr(tts_speaker, "last_tts_time_sec", elapsed_tts))
        tts_cache_hit = bool(getattr(tts_speaker, "last_cache_hit", False)) or (
            "Cache" in str(getattr(tts_speaker, "last_engine_used", ""))
        )
        st.session_state.latest_audio_file = generated_wav
        st.session_state.autoplay_next = True
    else:
        st.session_state.autoplay_next = False

    total_sec = round(llm_sec + map_sec + tts_sec, 4)
    res["llm_time_sec"] = llm_sec
    res["map_routing_time_sec"] = map_sec
    res["tts_time_sec"] = tts_sec
    res["tts_cache_hit"] = tts_cache_hit
    res["total_latency_sec"] = total_sec
    res["latency_ms"] = round(total_sec * 1000.0, 2)

    db_logger.log_interaction(res, sensor_now)

    llm_tag = "⚡ LLM Cache Hit" if res.get("llm_cache_hit") else "🧠 LLM Generated"
    tts_tag = getattr(tts_speaker, "last_engine_used", voice_id)

    # พิมพ์สรุปเวลาประมวลผลรายขั้นตอนออกทาง Terminal ของ Raspberry Pi 4 แบบสดๆ ควบคู่ไปด้วย (Dual Output)
    print(
        f"\n[GovNav Evaluation] คำถาม: \"{clean_q}\"\n"
        f"  -> จุดหมาย: {res['room_id']} ({res['department_name']}) | ไฟ LED: {res['direction_code']}\n"
        f"  • LLM & Fuzzy Matching Time : {llm_sec:.3f} วินาที ({llm_tag})\n"
        f"  • Path Finding & Map Image  : {map_sec:.3f} วินาที\n"
        f"  • TTS Generation Time       : {tts_sec:.3f} วินาที ({tts_tag})\n"
        f"  • เวลาประมวลผลรวม (Total)   : {total_sec:.3f} วินาที ({res['latency_ms']} ms)",
        flush=True,
    )

    st.session_state.query_text = clean_q
    st.session_state.nav_result = res
    st.session_state.sensor_snapshot = sensor_now


# -----------------------------------------------------------------------------
# Sidebar: แผงควบคุมเสียง VachanaTTS & เซนเซอร์ IoT
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚙️ ตั้งค่าระบบตู้คีออส")

    st.markdown("### 🔊 ระบบเสียงไทย (VachanaTTS)")
    enable_voice = st.toggle("เปิดเสียงพูดนำทางอัตโนมัติ", value=True)

    voice_options = list(AVAILABLE_VOICES.keys())
    selected_voice = st.selectbox(
        "เลือกเสียงผู้พากย์ (Offline ONNX):",
        options=voice_options,
        index=voice_options.index(TTS_MODEL) if TTS_MODEL in voice_options else 0,
        format_func=lambda v: AVAILABLE_VOICES.get(v, v),
    )

    col_sp, col_vl = st.columns(2)
    voice_speed = col_sp.slider("ความเร็วพูด", min_value=0.7, max_value=1.4, value=float(TTS_SPEED), step=0.05)
    voice_volume = col_vl.slider("ความดังเสียง", min_value=0.5, max_value=1.5, value=float(TTS_VOLUME), step=0.1)

    play_os_speaker = st.checkbox(
        "ส่งเสียงออกลำโพงบอร์ด RPi4 โดยตรง (aplay)",
        value=sys.platform.startswith("linux"),
        help="เปิดอัตโนมัติเมื่อรันบน Raspberry Pi 4 เพื่อให้เสียงออกลำโพงที่ต่อกับบอร์ดทันที",
    )

    tts_status = safe_tts_status(tts_speaker)
    if tts_status["vachanatts_installed"]:
        st.success(f"✅ เอนจิน: **{tts_status['engine_name']}**\n\nแคชเสียงพร้อมใช้: `{tts_status['cached_audio_count']}` ไฟล์")
    else:
        st.warning(
            f"⚠️ ขณะนี้ใช้เสียงสำรอง: **{tts_status['engine_name']}**\n\n"
            "ติดตั้ง VachanaTTS พูดชัดแบบ Offline ด้วยคำสั่ง:\n"
            "`pip install --break-system-packages vachanatts`"
        )

    btn_test_col, btn_cache_col = st.columns(2)
    if btn_test_col.button("🔈 ทดสอบเสียง", **STRETCH_KW):
        greeting_wav = os.path.join(AUDIO_OUT_DIR, "test_greeting.wav")
        safe_tts_speak(
            tts_speaker,
            "สวัสดีค่ะ ยินดีต้อนรับสู่ศูนย์บริการประชาชน กอฟแนฟ กรุณาเลือกเรื่องที่ต้องการติดต่อที่หน้าจอได้เลยนะคะ",
            output_wav=greeting_wav,
            play_device=play_os_speaker,
            voice_name=selected_voice,
            speed=voice_speed,
            volume=voice_volume,
        )
        st.session_state.latest_audio_file = greeting_wav
        st.toast("กำลังเล่นเสียงทดสอบภาษาไทย", icon="🔊")
        render_audio_player(greeting_wav, autoplay=True)

    if btn_cache_col.button("⚡ แคชทุกห้อง", help="สร้างแคชทั้งคำตอบ AI และไฟล์เสียงพูดของปุ่มด่วนทั้ง 5 ห้องไว้ล่วงหน้า", **STRETCH_KW):
        prog = st.progress(0, text="กำลังสร้างแคชคำตอบ AI และเสียงพูดทั้ง 5 ปุ่มบริการด่วน...")
        total_presets = len(QUICK_PRESETS)
        for idx_p, (p_label, p_query) in enumerate(QUICK_PRESETS, 1):
            pre_res = safe_navigate(nav_ai, p_query, bypass_cache=False)
            safe_tts_speak(
                tts_speaker,
                pre_res["spoken_response"],
                output_wav=os.path.join(AUDIO_OUT_DIR, f"cache_{pre_res['room_id']}.wav"),
                play_device=False,
                voice_name=selected_voice,
                speed=voice_speed,
                volume=voice_volume,
                bypass_cache=False,
            )
            prog.progress(idx_p / total_presets, text=f"แคช {p_label} สำเร็จ ({idx_p}/{total_presets})")
        st.success("เตรียมแคชคำตอบ AI + เสียงพูดทั้ง 5 ปุ่มด่วนครบแล้ว! กดปุ่มไหนก็ตอบทันทีใน 0.01 วินาที")
        st.rerun()

    st.divider()
    st.markdown("### 📡 เซนเซอร์ IoT & ฮาร์ดแวร์")
    if st.button("🔄 อ่านค่าเซนเซอร์โถงบริการใหม่", **STRETCH_KW):
        fresh = iot_hw.read_environment()
        fresh["active_led_direction"] = iot_hw.active_led_direction
        st.session_state.sensor_snapshot = fresh

    manual_sim = st.toggle("จำลองปรับระยะคนเดินเข้าใกล้ตู้", value=False)
    if manual_sim:
        sim_dist = st.slider("ระยะห่างผู้มาติดต่อ (cm):", min_value=20.0, max_value=260.0, value=95.0, step=5.0)
        st.session_state.sensor_snapshot["visitor_distance_cm"] = sim_dist
        st.session_state.sensor_snapshot["visitor_approaching"] = sim_dist <= APPROACH_DISTANCE_CM

    with st.expander("🔌 ผังพอร์ต GPIO บน Raspberry Pi 4"):
        gpio_rows = [{"อุปกรณ์ (Sensor / Actuator)": k, "GPIO Pin (BCM)": f"GPIO {v}"} for k, v in GPIO_PINS.items()]
        st.table(gpio_rows)

# -----------------------------------------------------------------------------
# รันคำถามเริ่มต้นอัตโนมัติในครั้งแรกที่เปิดหน้าจอ
# -----------------------------------------------------------------------------
if st.session_state.nav_result is None:
    initial_res = safe_navigate(nav_ai, st.session_state.query_text, bypass_cache=False)
    iot_hw.activate_direction_led(initial_res["direction_code"])
    st.session_state.sensor_snapshot["active_led_direction"] = initial_res["direction_code"]
    st.session_state.nav_result = initial_res

# -----------------------------------------------------------------------------
# ส่วนหัวเว็บไซต์ (Hero Banner)
# -----------------------------------------------------------------------------
llm_badge = "🧠 AI: Qwen Edge GGUF (Offline)" if nav_ai.llm is not None else "🧠 AI: Smart-Match RAG Engine (Offline)"
tts_badge = f"🔊 เสียงไทย: {safe_tts_status(tts_speaker)['engine_name']} [{selected_voice}]"
hw_badge = f"📡 ฮาร์ดแวร์: {st.session_state.sensor_snapshot['hardware_mode']}"

st.markdown(
    f"""
    <div class="govnav-hero">
        <h1>🏛️ GovNav (Government Navigator)</h1>
        <p>ระบบตู้คีออสผู้ช่วยแนะนำขั้นตอนราชการและนำทางอัจฉริยะสำหรับประชาชน ด้วย Edge AI & Multi-Sensor IoT</p>
        <div class="badge-row">
            <span class="gov-badge-gold">⚡ Offline 100% พร้อมใช้งาน</span>
            <span class="gov-badge">{llm_badge}</span>
            <span class="gov-badge">{tts_badge}</span>
            <span class="gov-badge">{hw_badge}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# แถบแสดงค่าเซนเซอร์สด (Live IoT Telemetry)
# -----------------------------------------------------------------------------
sensor_data = st.session_state.sensor_snapshot
m_col1, m_col2, m_col3, m_col4 = st.columns(4)
m_col1.metric(
    "📡 ระยะตรวจจับผู้มาติดต่อ (Ultrasonic)",
    f"{sensor_data['visitor_distance_cm']} cm",
    "🟢 มีผู้ยืนหน้าตู้ (<150 cm)" if sensor_data["visitor_approaching"] else "⚪ รอผู้มาติดต่อ",
)
m_col2.metric("🌡️ อุณหภูมิโถงบริการ (DHT22)", f"{sensor_data['ambient_temp_c']} °C", "สภาวะปกติ")
m_col3.metric("💧 ความชื้นสัมพัทธ์ (DHT22)", f"{sensor_data['ambient_humidity_pct']} %", "โถงในอาคาร")
m_col4.metric("💡 สถานะไฟ LED ชี้ทาง", sensor_data["active_led_direction"])

st.divider()

# -----------------------------------------------------------------------------
# ปุ่มด่วนเลือกบริการยอดนิยม 5 ห้องราชการ
# -----------------------------------------------------------------------------
st.subheader("👆 แตะเลือกบริการด่วน หรือพิมพ์สอบถามด้วยภาษาพูดปกติ")

q_cols = st.columns(5)
for idx, (btn_label, preset_q) in enumerate(QUICK_PRESETS):
    if q_cols[idx].button(btn_label, key=f"preset_btn_{idx}", **STRETCH_KW):
        execute_navigation(preset_q, enable_voice, selected_voice, voice_speed, voice_volume, play_os_speaker)

# -----------------------------------------------------------------------------
# ช่องพิมพ์คำถามอิสระ + ปุ่มเรียกเจ้าหน้าที่ฉุกเฉิน
# -----------------------------------------------------------------------------
form_col, buzzer_col = st.columns([3.6, 1.2])

with form_col:
    with st.form("govnav_search_form", clear_on_submit=False):
        input_col, submit_col = st.columns([4, 1.3])
        typed_query = input_col.text_input(
            "พิมพ์เรื่องที่ต้องการติดต่อราชการ:",
            value=st.session_state.query_text,
            placeholder="เช่น บัตรประชาชนหายต้องเตรียมอะไรบ้าง, จ่ายค่าขยะห้องไหน, โอนมรดกที่ดิน...",
            label_visibility="collapsed",
        )
        submitted = submit_col.form_submit_button("🔍 ค้นหาเส้นทาง", type="primary", **STRETCH_KW)
        if submitted and typed_query.strip():
            execute_navigation(typed_query, enable_voice, selected_voice, voice_speed, voice_volume, play_os_speaker)

with buzzer_col:
    if st.button("🚨 เรียกเจ้าหน้าที่ (Buzzer)", type="secondary", **STRETCH_KW):
        iot_hw.trigger_staff_buzzer()
        alert_wav = os.path.join(AUDIO_OUT_DIR, "staff_alert.wav")
        if enable_voice:
            safe_tts_speak(
                tts_speaker,
                "ส่งสัญญาณแจ้งเจ้าหน้าที่ประชาสัมพันธ์เรียบร้อยแล้ว กรุณารอสักครู่ค่ะ",
                output_wav=alert_wav,
                play_device=play_os_speaker,
                voice_name=selected_voice,
                speed=voice_speed,
                volume=voice_volume,
            )
            st.session_state.latest_audio_file = alert_wav
            st.session_state.autoplay_next = True
        st.warning("🔔 ส่งสัญญาณกริ่ง GPIO 18 เรียกเจ้าหน้าที่ประชาสัมพันธ์มาดูแลท่านแล้ว!")

# -----------------------------------------------------------------------------
# แสดงผลลัพธ์การนำทาง แผนผัง และเสียงพูดภาษาไทย
# -----------------------------------------------------------------------------
result = st.session_state.nav_result
if result:
    st.markdown(
        f"""
        <div class="ai-reply-card">
            <strong>🤖 คำแนะนำจาก GovNav AI:</strong><br>
            {result['spoken_response']}
        </div>
        """,
        unsafe_allow_html=True,
    )

    aud_col1, aud_col2, aud_col3 = st.columns([2.6, 1.1, 1.3])
    with aud_col1:
        if st.session_state.latest_audio_file and os.path.exists(st.session_state.latest_audio_file):
            render_audio_player(st.session_state.latest_audio_file, autoplay=st.session_state.autoplay_next)
            st.session_state.autoplay_next = False
        else:
            st.caption("🔈 กดปุ่ม **'ฟังเสียงคำแนะนำซ้ำ'** ด้านขวา หรือกดเลือกบริการเพื่อฟังเสียงพูดภาษาไทย")

    with aud_col2:
        if st.button("🔊 ฟังเสียงคำแนะนำซ้ำ", **STRETCH_KW):
            replay_wav = os.path.join(AUDIO_OUT_DIR, f"reply_{result['room_id']}.wav")
            generated = safe_tts_speak(
                tts_speaker,
                result["spoken_response"],
                output_wav=replay_wav,
                play_device=play_os_speaker,
                voice_name=selected_voice,
                speed=voice_speed,
                volume=voice_volume,
            )
            st.session_state.latest_audio_file = generated
            st.session_state.autoplay_next = True
            st.rerun()

    with aud_col3:
        total_sec_val = float(result.get("total_latency_sec", round(result.get("latency_ms", 0.0) / 1000.0, 3)))
        cache_badge = (
            "⚡ ดึงจากแคชความเร็วสูง"
            if (result.get("tts_cache_hit") or result.get("llm_cache_hit"))
            else "🆕 สร้างและบันทึกแคชใหม่แล้ว"
        )
        st.caption(
            f"⏱️ เวลาประมวลผลรวม: **{total_sec_val:.2f} วินาที** ({result['latency_ms']} ms)\n\n"
            f"🎙️ `{selected_voice}` &nbsp;|&nbsp; {cache_badge}"
        )

    with st.expander("⏱️ รายละเอียดเวลาตอบสนองรายขั้นตอน (6.2 Response Latency Breakdown)", expanded=False):
        llm_s = float(result.get("llm_time_sec", round(result.get("latency_ms", 0.0) / 1000.0, 3)))
        map_s = float(result.get("map_routing_time_sec", 0.005))
        tts_s = float(result.get("tts_time_sec", 0.0))
        tot_s = float(result.get("total_latency_sec", round(llm_s + map_s + tts_s, 3)))
        lat_c1, lat_c2, lat_c3, lat_c4 = st.columns(4)
        lat_c1.metric("🧠 LLM & Fuzzy Matching", f"{llm_s:.2f} วินาที")
        lat_c2.metric("🗺️ Path Finding & Map", f"{map_s:.3f} วินาที")
        lat_c3.metric("🔊 VachanaTTS Generation", f"{tts_s:.2f} วินาที")
        lat_c4.metric("⚡ เวลาประมวลผลรวมทั้งสิ้น", f"{tot_s:.2f} วินาที")
        st.markdown(
            f"- **LLM & Fuzzy Matching Time (llama.cpp on Pi 4):** `~{llm_s:.2f} วินาที`\n"
            f"- **Path Finding & Image Generation:** `~{map_s:.3f} วินาที`\n"
            f"- **TTS Generation Time (VachanaTTS ONNX):** `~{tts_s:.2f} วินาที`\n"
            f"- **เวลาประมวลผลรวมทั้งสิ้น (Total Latency):** `~{tot_s:.2f} วินาที`"
        )

    st.markdown(
        f"""
        <div class="led-banner">
            {format_led_label(result['direction_code'])} &nbsp;|&nbsp; 🚶 <strong>วิธีเดิน:</strong> {result['walk_steps']}
        </div>
        """,
        unsafe_allow_html=True,
    )

    info_col, map_img_col = st.columns([1.05, 1.35], gap="large")

    with info_col:
        st.markdown(
            f"""
            <div class="room-card">
                <h3 style="margin-top:0; color:#0f2942;">📍 เป้าหมาย: {result['room_id']}</h3>
                <p style="font-size:1.1rem; font-weight:600; margin-bottom:0.5rem;">{result['department_name']}</p>
                <ul style="margin-bottom:0; line-height:1.75;">
                    <li><strong>🏢 ชั้น / โซนอาคาร:</strong> ชั้น {result['floor']} ({result['wing']})</li>
                    <li><strong>👥 คิวรอปัจจุบัน:</strong> {result['queue_count']} คิว (รอประมาณ ~{result['estimated_wait_min']} นาที)</li>
                    <li><strong>💡 รหัสสัญญาณไฟ LED:</strong> <code>{result['direction_code']}</code></li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### 📋 ตรวจสอบเอกสารที่ต้องเตรียมก่อนเข้าช่องบริการ:")
        for doc_idx, doc in enumerate(result["required_docs"]):
            st.checkbox(doc, value=True, key=f"doc_chk_{result['room_id']}_{doc_idx}")

        st.markdown("#### 🗺️ แผนที่เส้นขีดสำหรับพิมพ์ใบนำทาง (ASCII Slip Map):")
        st.code(result["ascii_map"], language="text")

    with map_img_col:
        map_path = result["map_image_path"]
        st.markdown(f"#### 🖼️ แผนผังกราฟิกนำทางในอาคาร (`{os.path.basename(map_path)}`):")
        if os.path.exists(map_path):
            st.image(map_path, **STRETCH_KW)
            with open(map_path, "rb") as img_f:
                st.download_button(
                    label="📥 ดาวน์โหลดรูปแผนผังนำทาง (.png) เก็บไว้ในมือถือ",
                    data=img_f.read(),
                    file_name=os.path.basename(map_path),
                    mime="image/png",
                    **STRETCH_KW,
                )

st.divider()

# -----------------------------------------------------------------------------
# ส่วนผู้ดูแลระบบและสถิติฐานข้อมูล SQLite
# -----------------------------------------------------------------------------
st.subheader("📊 ระบบวิเคราะห์ข้อมูลผู้มาติดต่อราชการ (SQLite Local Analytics)")

summary = safe_db_summary(db_logger)
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("👥 จำนวนการสอบถามสะสม", f"{summary['total_visits']} ครั้ง")
kpi2.metric("🏆 หน่วยงานที่มีผู้ติดต่อสูงสุด", summary["top_room_id"], summary["top_department"][:28])
kpi3.metric("⚡ เวลาตอบสนองเฉลี่ย (Latency)", f"{summary['avg_latency_ms']} ms")
kpi4.metric("📏 ระยะยืนหน้าตู้เฉลี่ย", f"{summary['avg_distance_cm']} cm")

tab_eval, tab_stats, tab_logs, tab_directory = st.tabs([
    "🧪 ผลการทดลอง 6.1 & 6.2 (สำหรับรายงาน)",
    "📈 สถิติแยกตามห้องราชการ",
    "🕒 ประวัติการใช้งานล่าสุด (SQLite Logs)",
    "🏢 ทำเนียบห้องบริการทั้งหมด (5 หน่วยงาน)",
])

with tab_eval:
    st.markdown(
        "จำลองสถานการณ์ผู้มาติดต่อราชการภาษาชาวบ้าน **30 รูปแบบ** เพื่อสรุปตารางความแม่นยำ (**หัวข้อ 6.1**) "
        "และเวลาตอบสนองเฉลี่ยรายขั้นตอน (**หัวข้อ 6.2**) โดย **ไม่ลบและไม่เขียนทับไฟล์แคชเสียงเดิม** ในเครื่อง"
    )
    ev_col1, ev_col2, ev_col3 = st.columns([1.55, 1.15, 1.3])

    run_eval_limit = None
    with ev_col1:
        if st.button("▶️ รันวัดผลเต็มรูปแบบ 30 สถานการณ์", type="primary", **STRETCH_KW):
            run_eval_limit = 0
    with ev_col2:
        if st.button("⚡ ทดสอบด่วน 5 ข้อ", **STRETCH_KW):
            run_eval_limit = 5
    with ev_col3:
        if os.path.exists(EVAL_REPORT_CSV):
            with open(EVAL_REPORT_CSV, "rb") as csv_f:
                st.download_button(
                    "📥 ดาวน์โหลดผลรายข้อ (.csv เปิดใน Excel)",
                    data=csv_f.read(),
                    file_name="govnav_eval_30_scenarios.csv",
                    mime="text/csv",
                    **STRETCH_KW,
                )

    if run_eval_limit is not None:
        from evaluate_govnav import run_evaluation_suite, print_report_to_terminal

        prog_bar = st.progress(0)
        prog_txt = st.empty()

        def _ui_progress(cur_idx: int, total_items: int, rec: dict):
            pct = int((cur_idx / max(1, total_items)) * 100)
            prog_bar.progress(pct)
            prog_txt.caption(
                f"กำลังทดสอบข้อที่ {cur_idx}/{total_items}: \"{rec['query']}\" "
                f"→ `{rec['predicted_room']}` (รวม {rec['total_time_sec']:.2f} วินาที)"
            )

        rep_now = run_evaluation_suite(
            nav_ai=nav_ai,
            tts_speaker=tts_speaker,
            limit=run_eval_limit,
            voice_name=selected_voice,
            bypass_tts_cache=True,
            progress_callback=_ui_progress,
        )
        print_report_to_terminal(rep_now)
        prog_bar.empty()
        prog_txt.empty()
        st.toast("ประมวลผลและบันทึกตารางผลการทดลอง 6.1 & 6.2 เรียบร้อยแล้ว!", icon="✅")
        st.rerun()

    if os.path.exists(EVAL_REPORT_JSON):
        try:
            with open(EVAL_REPORT_JSON, "r", encoding="utf-8") as rf:
                rep = json.load(rf)

            rows_html = ""
            for r in rep.get("accuracy_table", []):
                rows_html += (
                    f"<tr>"
                    f"<td>{r['topic']}</td>"
                    f"<td>{r['total']}</td>"
                    f"<td>{r['passed']}</td>"
                    f"<td><strong>{r['accuracy_pct']}%</strong></td>"
                    f"</tr>"
                )

            lat = rep.get("latency_summary", {})
            st.markdown(
                f"""
                <div class="report-box">
                    <h3 style="margin-top:0; color:#0f2942;">6. ผลการทดลองและการวิเคราะห์ (Experimental Results & Discussion)</h3>
                    <p style="color:#475569; font-size:0.92rem; margin-bottom:1rem;">
                        🕒 อัปเดตผลล่าสุด: <code>{rep.get('evaluated_at', '-')}</code> &nbsp;|&nbsp;
                        🧠 โหมดประมวลผล: <code>{rep.get('llm_mode', '-')}</code> &nbsp;|&nbsp;
                        🔊 ระบบเสียง: <code>{rep.get('tts_engine', '-')}</code>
                    </p>
                    <h4 style="color:#1e293b; margin-bottom:0.35rem;">6.1 ผลการทดสอบความแม่นยำของระบบ (Accuracy Test)</h4>
                    <p style="margin-top:0; margin-bottom:0.5rem;">
                        จากการจำลองสถานการณ์ผู้มาติดต่อราชการจำนวน {rep.get('total_scenarios', 30)} รูปแบบคำถามภาษาชาวบ้าน สรุปความแม่นยำได้ดังนี้:
                    </p>
                    <table class="exp-table">
                        <thead>
                            <tr>
                                <th>หัวข้อการทดสอบ</th>
                                <th>จำนวนทดสอบ (ครั้ง)</th>
                                <th>ผ่าน (ครั้ง)</th>
                                <th>ความแม่นยำ (%)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                    <h4 style="color:#1e293b; margin-top:1.1rem; margin-bottom:0.35rem;">6.2 ผลการทดสอบเวลาตอบสนอง (Response Latency)</h4>
                    <p style="margin-top:0; margin-bottom:0.5rem;">
                        เวลาเฉลี่ยที่ใช้ในการประมวลผลตั้งแต่รับคำถามจนถึงการแสดงแผนที่และสังเคราะห์เสียงพูดบนอุปกรณ์:
                    </p>
                    <ul style="line-height:1.85; margin-bottom:0;">
                        <li><strong>LLM &amp; Fuzzy Matching Time (llama.cpp on Pi 4):</strong> ~{lat.get('llm_inference_sec', 0.0):.2f} วินาที</li>
                        <li><strong>Path Finding &amp; Image Generation:</strong> ~{lat.get('path_finding_map_sec', 0.0):.2f} วินาที</li>
                        <li><strong>TTS Generation Time (VachanaTTS ONNX):</strong> ~{lat.get('tts_generation_sec', 0.0):.2f} วินาที</li>
                        <li><strong>เวลาประมวลผลรวมทั้งสิ้น (Total Latency):</strong> <strong>~{lat.get('total_latency_sec', 0.0):.2f} วินาที</strong></li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.expander("📋 ดูตารางผลลัพธ์ละเอียดรายข้อ (เปรียบเทียบคำถาม เป้าหมาย และเวลารายข้อ)"):
                st.dataframe(rep.get("details", []), **STRETCH_KW)
        except Exception as exc:
            st.warning(f"ไม่สามารถอ่านไฟล์รายงานผลการทดลองได้ ({exc}) กรุณากดรันวัดผลใหม่อีกครั้ง")
    else:
        st.info(
            "💡 ยังไม่มีไฟล์ผลการทดลองบนเครื่องนี้ — กดปุ่ม **'▶️ รันวัดผลเต็มรูปแบบ 30 สถานการณ์'** ด้านบน "
            "หรือรันคำสั่ง `python3 evaluate_govnav.py` ใน Terminal ของ Raspberry Pi 4 เพื่อสร้างตารางสรุปผลสำหรับใส่เล่มรายงาน"
        )

with tab_stats:
    room_stats = db_logger.get_room_statistics()
    if room_stats:
        chart_col, table_col = st.columns([1.1, 1.3])
        with chart_col:
            chart_dict = {row["matched_room_id"]: row["visit_count"] for row in room_stats}
            st.bar_chart(chart_dict)
        with table_col:
            st.dataframe(room_stats, **STRETCH_KW)
    else:
        st.info("ยังไม่มีข้อมูลสถิติในฐานข้อมูล กดปุ่มเลือกบริการด้านบนเพื่อเริ่มบันทึกข้อมูลชุดแรก")

with tab_logs:
    recent_logs = db_logger.get_recent_logs(limit=25)
    act_col1, act_col2, _ = st.columns([1.4, 1.2, 2.4])
    with act_col1:
        csv_data = safe_export_csv(db_logger)
        st.download_button(
            "📥 ส่งออกประวัติทั้งหมดเป็น CSV (Excel)",
            data=csv_data.encode("utf-8"),
            file_name="govnav_visitor_logs.csv",
            mime="text/csv",
            **STRETCH_KW,
        )
    with act_col2:
        if st.button("🗑️ ล้างประวัติการทดสอบ", **STRETCH_KW):
            safe_clear_logs(db_logger)
            st.toast("ล้างประวัติในฐานข้อมูล SQLite เรียบร้อยแล้ว", icon="🗑️")
            st.rerun()

    if recent_logs:
        st.dataframe(recent_logs, **STRETCH_KW)
    else:
        st.info("ยังไม่มีประวัติการใช้งานล่าสุด")

with tab_directory:
    dir_rows = []
    for d in nav_ai.departments:
        dir_rows.append({
            "รหัสห้อง": d["room_id"],
            "ชื่อหน่วยงาน": d["name_th"],
            "ชั้น": f"ชั้น {d['floor']}",
            "โซนอาคาร": d["wing"],
            "คิวรอ": f"{d['queue_count']} คิว (~{d['estimated_wait_min']} นาที)",
            "บริการหลัก": ", ".join(d["services"][:4]),
        })
    st.dataframe(dir_rows, **STRETCH_KW)
