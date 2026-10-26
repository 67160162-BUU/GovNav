#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - Offline Voice Model & Audio Cache Downloader (Standalone Resilient Edition)
ไม่ยุ่งหรือติดตั้งโมเดล LLM ใหม่ใดๆ ทั้งสิ้น และไม่พึ่งพาเวอร์ชันเก่าของ tts_speaker.py
รันสคริปต์นี้เพียงครั้งเดียวขณะต่ออินเทอร์เน็ต เพื่อ:
1. ดาวน์โหลดโมเดลเสียง VachanaTTS (.onnx) เก็บไว้ในโฟลเดอร์ GovNav/voices/
2. สร้างไฟล์เสียงแนะนำเส้นทางพื้นฐานของทั้ง 5 ห้องราชการเก็บไว้ใน GovNav/assets/audio_out/ และ audio_cache/
"""

import os
import re
import glob
import json
import shutil
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
AUDIO_OUT_DIR = os.path.join(ASSETS_DIR, "audio_out")
AUDIO_CACHE_DIR = os.path.join(ASSETS_DIR, "audio_cache")
VOICES_DIR = os.path.join(BASE_DIR, "voices")
DEPARTMENTS_FILE = os.path.join(DATA_DIR, "departments.json")

AVAILABLE_VOICES = {
    "th_f_1": "หญิง 1 (th_f_1) — สุภาพ นุ่มนวล ชัดเจน (แนะนำ)",
    "th_f_2": "หญิง 2 (th_f_2) — สดใส กระฉับกระเฉง",
    "th_m_1": "ชาย 1 (th_m_1) — สุภาพ ทางการ",
    "th_m_2": "ชาย 2 (th_m_2) — ทุ้มกังวาน ฟังง่าย",
}


def clean_speech_text(text: str) -> str:
    text = text.replace("กรุงเทพฯ", "กรุงเทพมหานคร").replace("ฯลฯ", "และอื่นๆ")
    text = text.replace("ปชช.", "ประชาชน").replace("ภ.ด.ส.", "พอดอสอ").replace("ภ.ป.", "พอปอ")
    text = text.replace("น.ส.4", "นอสอสี่").replace("น.ส.3", "นอสอสาม")
    text = text.replace("GovNav", "กอฟแนฟ")
    text = re.sub(r"ROOM_(\d+)", r"ห้อง \1", text)
    text = re.sub(r"[\(\)\[\]\{\}\"\'\*\#\_\~\|•—–]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def synthesize_direct(tts_fn, text: str, voice_id: str, output_wav: str):
    clean_text = clean_speech_text(text)
    output_wav = os.path.abspath(output_wav)
    os.makedirs(os.path.dirname(output_wav), exist_ok=True)
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    os.makedirs(VOICES_DIR, exist_ok=True)

    prev_cwd = os.getcwd()
    try:
        os.chdir(BASE_DIR)
        tts_fn(clean_text, voice=voice_id, output=output_wav, volume=1.0, speed=1.0)
    finally:
        os.chdir(prev_cwd)

    if os.path.exists(output_wav) and os.path.getsize(output_wav) > 512:
        key_raw = f"vachana|{voice_id}|1.00|1.00|{clean_text}"
        digest = hashlib.md5(key_raw.encode("utf-8")).hexdigest()[:16]
        cache_path = os.path.join(AUDIO_CACHE_DIR, f"tts_{voice_id}_{digest}.wav")
        shutil.copy2(output_wav, cache_path)


def main():
    print("=" * 72)
    print("[*] กำลังดาวน์โหลดเฉพาะโมเดลเสียง VachanaTTS (.onnx) สำหรับโหมด Offline")
    print("=" * 72)

    try:
        from vachanatts import TTS
    except ImportError as err:
        print(f"\n[!] ยังไม่ได้ติดตั้งไลบรารี vachanatts ({err}) กรุณารันคำสั่งนี้ก่อน:")
        print("    pip install --break-system-packages -r requirements.txt")
        return

    with open(DEPARTMENTS_FILE, "r", encoding="utf-8") as f:
        departments = json.load(f)["departments"]

    # 1. ดาวน์โหลดทั้ง 4 เสียง (หญิง 2 / ชาย 2) เก็บไว้ใน GovNav/voices/
    for voice_id, desc in AVAILABLE_VOICES.items():
        print(f"\n[*] กำลังเตรียมโมเดลเสียง: {desc}")
        test_out = os.path.join(AUDIO_OUT_DIR, f"welcome_{voice_id}.wav")
        synthesize_direct(
            TTS,
            "สวัสดีค่ะ ยินดีต้อนรับสู่ศูนย์บริการประชาชน กอฟแนฟ",
            voice_id=voice_id,
            output_wav=test_out,
        )
        print(f"    [OK] พร้อมใช้งาน Offline: voices/{voice_id}.onnx")

    # 2. สร้างแคชเสียงแนะนำพื้นฐานทั้ง 5 ห้องสำหรับเสียงหลัก th_f_1
    print("\n[*] กำลังสร้างไฟล์แคชเสียงนำทางพื้นฐานทั้ง 5 ห้องราชการ...")
    for dept in departments:
        docs_text = " และ ".join(dept["required_docs"][:2])
        reply_text = (
            f"สวัสดีค่ะ สำหรับเรื่อง {dept['services'][0]} ขอแนะนำให้ไปที่ {dept['name_th']} "
            f"ห้อง {dept['room_id']} ชั้น {dept['floor']} {dept['wing']} ค่ะ "
            f"{dept['walk_steps']} โดยกรุณาเตรียม {docs_text} มาแสดงต่อเจ้าหน้าที่ด้วยค่ะ"
        )
        room_wav = os.path.join(AUDIO_OUT_DIR, f"reply_{dept['room_id']}.wav")
        synthesize_direct(TTS, reply_text, voice_id="th_f_1", output_wav=room_wav)
        print(f"    [OK] แคชเสียงสำเร็จ: {dept['room_id']} — {dept['name_th']}")

    onnx_count = len(glob.glob(os.path.join(VOICES_DIR, "*.onnx")))
    cache_count = len(glob.glob(os.path.join(AUDIO_CACHE_DIR, "*.wav")))
    print("\n" + "=" * 72)
    print(f"[DONE] ดาวน์โหลดเสียงครบ {onnx_count} โมเดล และแคชเสียงพร้อมใช้ {cache_count} ไฟล์")
    print("=" * 72)


if __name__ == "__main__":
    main()
