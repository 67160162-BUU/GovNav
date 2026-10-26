#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav (Government Navigator) - Configuration File
รองรับทั้งโมเดลขนาด 1B (เช่น Qwen / Llama 3.2 1B .gguf) และ 0.5B
พร้อม VachanaTTS (VITS + Piper ONNX) สังเคราะห์เสียงภาษาไทยแบบ Offline 100% บน Raspberry Pi 4 & Mac
"""

import os
import glob

# Base Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)  # คือ /home/fablab-rpi-13/qwen_rpi4
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
MAPS_DIR = os.path.join(ASSETS_DIR, "maps")
AUDIO_OUT_DIR = os.path.join(ASSETS_DIR, "audio_out")
AUDIO_CACHE_DIR = os.path.join(ASSETS_DIR, "audio_cache")
VOICES_DIR = os.path.join(BASE_DIR, "voices")

DEPARTMENTS_FILE = os.path.join(DATA_DIR, "departments.json")
SYSTEM_PROMPT_FILE = os.path.join(DATA_DIR, "system_prompt.txt")
SQLITE_DB_PATH = os.path.join(DATA_DIR, "govnav_logs.db")

# ตั้งค่าโมเดลเริ่มต้น (ใช้เฉพาะเสียงผู้หญิงที่ 2: th_f_2)
MODEL_NAME = "Local-1B-GGUF"
TTS_MODEL = "th_f_2"
TTS_VOLUME = 1.0
TTS_SPEED = 1.0

AVAILABLE_VOICES = {
    "th_f_2": "👩 หญิง 2 (th_f_2) — สดใส สุภาพ ชัดเจน",
}


def find_all_gguf_models() -> list:
    """
    ค้นหาไฟล์โมเดล .gguf ทั้งหมดใน /home/fablab-rp-13/qwen_rpi4/models/
    เรียงลำดับจากโมเดล Qwen / ขนาดกะทัดรัดที่เสถียรบน Raspberry Pi 4 ก่อน
    """
    priority_patterns = [
        os.path.join(PARENT_DIR, "models", "*.gguf"),
        os.path.join(BASE_DIR, "models", "*.gguf"),
        "/home/fablab-rp-13/qwen_rpi4/models/*.gguf",
        "/home/fablab-rpi-13/qwen_rpi4/models/*.gguf",
        os.path.join(PARENT_DIR, "*.gguf"),
        os.path.join(BASE_DIR, "*.gguf"),
    ]
    all_gguf = []
    for pattern in priority_patterns:
        for f in sorted(glob.glob(pattern)):
            if os.path.isfile(f) and f not in all_gguf:
                all_gguf.append(f)

    if not all_gguf:
        for p in sorted(glob.glob(os.path.join(PARENT_DIR, "**", "*.gguf"), recursive=True)):
            if "llama.cpp" not in p and os.path.isfile(p) and p not in all_gguf:
                all_gguf.append(p)

    # เรียงลำดับให้โมเดลตระกูล Qwen และขนาดเหมาะกับ RPi4 (0.5B / 1B / 1.5B) ขึ้นก่อน
    def _rank(path: str) -> tuple:
        name = os.path.basename(path).lower()
        is_qwen = 0 if "qwen" in name else 1
        is_small = 0 if any(k in name for k in ("0.5b", "1b", "1.5b", "3.2")) else 1
        return (is_qwen, is_small, os.path.getsize(path))

    all_gguf.sort(key=_rank)
    return all_gguf


def find_qwen_gguf() -> str:
    """คืนค่าไฟล์โมเดล .gguf ตัวแรกที่เหมาะสมที่สุด"""
    candidates = find_all_gguf_models()
    return candidates[0] if candidates else ""


# Raspberry Pi 4 GPIO Pin Assignments (BCM Mode)
GPIO_PINS = {
    "ULTRASONIC_TRIG": 23,     # ขา Trigger เซนเซอร์วัดระยะตรวจจับคนเดินเข้ามา
    "ULTRASONIC_ECHO": 24,     # ขา Echo เซนเซอร์วัดระยะ
    "DHT22_PIN": 4,            # เซนเซอร์วัดอุณหภูมิ/ความชื้นโถงบริการ
    "LED_LEFT": 17,            # ไฟ LED ชี้ทางไปปีกซ้าย
    "LED_RIGHT": 27,           # ไฟ LED ชี้ทางไปปีกขวา
    "LED_STRAIGHT": 22,        # ไฟ LED ชี้ทางเดินตรง/ขึ้นชั้น 2
    "STAFF_BUZZER": 18,        # กริ่งเรียกเจ้าหน้าที่ประชาสัมพันธ์
    "HELP_BUTTON": 25          # ปุ่มกดขอความช่วยเหลือสำหรับผู้สูงอายุ/ผู้พิการ
}

APPROACH_DISTANCE_CM = 150.0   # ระยะตรวจจับผู้มาติดต่อเดินเข้าใกล้ตู้ (1.5 เมตร)
