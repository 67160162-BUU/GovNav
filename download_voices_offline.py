#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - Offline Voice Model Downloader (th_f_2 Female Voice Edition)
ดาวน์โหลดเฉพาะโมเดลเสียงผู้หญิงที่ 2 (th_f_2.onnx) เก็บไว้ใน GovNav/voices/ สำหรับใช้งาน Offline 100%
"""

import os
import re
import shutil
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
AUDIO_OUT_DIR = os.path.join(ASSETS_DIR, "audio_out")
AUDIO_CACHE_DIR = os.path.join(ASSETS_DIR, "audio_cache")
VOICES_DIR = os.path.join(BASE_DIR, "voices")

TARGET_VOICE = "th_f_2"
TARGET_DESC = "👩 หญิง 2 (th_f_2) — สดใส สุภาพ ชัดเจน"


def clean_speech_text(text: str) -> str:
    text = text.replace("กรุงเทพฯ", "กรุงเทพมหานคร").replace("ฯลฯ", "และอื่นๆ")
    text = text.replace("นะครับ", "นะคะ").replace("ครับ", "ค่ะ")
    text = text.replace("GovNav", "กอฟแนฟ")
    text = re.sub(r"ROOM_(\d+)", r"ห้อง \1", text)
    text = re.sub(r"[\(\)\[\]\{\}\"\'\*\#\_\~\|•—–]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def main():
    print("=" * 72)
    print(f"[*] กำลังดาวน์โหลดเฉพาะโมเดลเสียงผู้หญิงที่ 2 ({TARGET_VOICE}.onnx) สำหรับโหมด Offline")
    print("=" * 72)

    try:
        from vachanatts import TTS
    except ImportError as err:
        print(f"\n[!] ยังไม่ได้ติดตั้งไลบรารี vachanatts ({err}) กรุณารันคำสั่งนี้ก่อน:")
        print("    pip install --break-system-packages -r requirements.txt")
        return

    os.makedirs(AUDIO_OUT_DIR, exist_ok=True)
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    os.makedirs(VOICES_DIR, exist_ok=True)

    welcome_text = clean_speech_text(
        "สวัสดีค่ะ ยินดีต้อนรับสู่ศูนย์บริการประชาชน กอฟแนฟ กรุณาเลือกเรื่องที่ต้องการติดต่อที่หน้าจอได้เลยนะคะ"
    )
    test_out = os.path.join(AUDIO_OUT_DIR, "test_greeting.wav")

    prev_cwd = os.getcwd()
    try:
        os.chdir(BASE_DIR)
        TTS(welcome_text, voice=TARGET_VOICE, output=test_out, volume=1.0, speed=1.0)
    finally:
        os.chdir(prev_cwd)

    if os.path.exists(test_out) and os.path.getsize(test_out) > 512:
        key_raw = f"vachana|{TARGET_VOICE}|1.00|1.00|{welcome_text}"
        digest = hashlib.md5(key_raw.encode("utf-8")).hexdigest()[:16]
        cache_path = os.path.join(AUDIO_CACHE_DIR, f"tts_{TARGET_VOICE}_{digest}.wav")
        shutil.copy2(test_out, cache_path)
        print(f"\n[✓] ดาวน์โหลดโมเดลเสียงสำเร็จพร้อมใช้งาน Offline 100%: voices/{TARGET_VOICE}.onnx")
    else:
        print(f"\n[!] ไม่พบไฟล์เสียงขาออก กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตสำหรับโหลดครั้งแรก")


if __name__ == "__main__":
    main()
