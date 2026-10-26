#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
GovNav (Government Navigator) - Main CLI & Raspberry Pi 4 Kiosk Runner
=============================================================================
ระบบผู้ช่วยแนะนำขั้นตอนราชการและนำทางอัจฉริยะสำหรับคนนอกพื้นที่บน Raspberry Pi 4
รองรับ:
1. ตอบกลับเป็นสถานที่ ห้อง ชั้น และรายการเอกสารที่ต้องเตรียม
2. วาดภาพแผนที่ด้วยตัวอักษรขีด (ASCII / Box-Drawing Map) แสดงเส้นทางเดินชัดเจน
3. ค้นหาไฟล์รูปภาพแผนที่ (.png) จากโฟลเดอร์ assets/maps/ และสั่งเปิดรูปขึ้นจอทันที
4. สังเคราะห์เสียงภาษาไทยแบบ Offline 100% ด้วย VachanaTTS (VITS + Piper ONNX)
5. แสดงผลเวลาตอบสนองแยกรายขั้นตอน (6.2 Response Latency) ทุกครั้งที่ประมวลผลเสร็จ
=============================================================================
"""

import argparse
import config
from core.llm_navigator import GovNavLLM
from core.iot_hardware import GovNavIoTHardware
from core.tts_speaker import GovNavTTSSpeaker
from core.db_logger import GovNavDBLogger

AVAILABLE_VOICES = getattr(
    config,
    "AVAILABLE_VOICES",
    {"th_f_2": "หญิง 2"},
)
raw_tts_model = getattr(config, "TTS_MODEL", "th_f_2")
TTS_MODEL = raw_tts_model if raw_tts_model in AVAILABLE_VOICES else "th_f_2"


def display_navigation_result(res: dict, sensor_data: dict, tts_time_sec: float = 0.0, tts_engine_label: str = ""):
    """แสดงผลลัพธ์การนำทาง แผนที่ตัวอักษรขีด และเวลาตอบสนองรายขั้นตอน (6.2 Response Latency)"""
    llm_sec = float(res.get("llm_time_sec", round(res.get("latency_ms", 0.0) / 1000.0, 3)))
    map_sec = float(res.get("map_routing_time_sec", 0.005))
    total_sec = round(llm_sec + map_sec + tts_time_sec, 3)

    print("\n" + "═" * 80)
    print(f"📡 [IoT Sensor] ระยะผู้มาติดต่อ: {sensor_data['visitor_distance_cm']} cm | "
          f"อุณหภูมิโถง: {sensor_data['ambient_temp_c']}°C | "
          f"ไฟ LED ชี้ทาง: [{res['direction_code']}]")
    print("═" * 80)
    print(f"🗣️  คำถามประชาชน : \"{res['query']}\"")
    print(f"🤖 คำตอบ GovNav  : {res['spoken_response']}")
    print("─" * 80)
    print(f"📍 สถานที่เป้าหมาย : {res['room_id']} — {res['department_name']}")
    print(f"🏢 ชั้น / โซน     : ชั้น {res['floor']} ({res['wing']}) | คิวรอปัจจุบัน: {res['queue_count']} คิว (~{res['estimated_wait_min']} นาที)")
    print("📋 เอกสารที่ต้องใช้ :")
    for idx, doc in enumerate(res["required_docs"], 1):
        print(f"   {idx}. {doc}")

    # 1. แสดงแผนผังวาดด้วยตัวอักษรขีด (ASCII / Unicode Map)
    print(res["ascii_map"])

    # 2. แสดงไฟล์รูปภาพแผนที่ที่ระบบค้นหามาให้
    print(f"🖼️  [Image Lookup] ค้นพบไฟล์รูปแผนที่พร้อมเปิดแสดงผล: {res['map_image_path']}")
    print("─" * 80)
    print("⏱️  ผลการวัดเวลาตอบสนองรายขั้นตอน (6.2 Response Latency):")
    print(f"   • LLM & Fuzzy Matching Time (llama.cpp on Pi 4) : {llm_sec:.3f} วินาที")
    print(f"   • Path Finding & Image Generation               : {map_sec:.3f} วินาที")
    print(f"   • TTS Generation Time ({tts_engine_label or 'Disabled'}) : {tts_time_sec:.3f} วินาที")
    print(f"   • เวลาประมวลผลรวมทั้งสิ้น (Total Latency)         : {total_sec:.3f} วินาที ({round(total_sec * 1000, 1)} ms)")
    print("═" * 80 + "\n")


def run_demo(open_image: bool = False, enable_tts: bool = False, model_path: str = "", voice: str = TTS_MODEL):
    """รันโหมดสาธิตการทำงานอัตโนมัติสำหรับทดสอบและอัดคลิปส่งอาจารย์"""
    nav_ai = GovNavLLM(model_path=model_path)
    iot_hw = GovNavIoTHardware()
    tts = GovNavTTSSpeaker(enabled=enable_tts, voice_name=voice)
    db = GovNavDBLogger()

    print("🔧 กำลังเตรียมไฟล์รูปภาพแผนที่ทุกห้องในโฟลเดอร์ assets/maps/ ...")
    generated_files = nav_ai.map_renderer.generate_all_map_images()
    print(f"✅ สร้างและตรวจสอบไฟล์รูปแผนที่สำเร็จ ({len(generated_files)} ไฟล์)")

    sample_queries = [
        "ยายมาจากต่างอำเภอ จะมาลงทะเบียนเบี้ยคนชรา ต้องไปติดต่อห้องไหนลูก",
        "ทำบัตรประชาชนใหม่ บัตรเดิมหาย ต้องไปทางไหนครับ",
        "มาโอนที่ดินมรดก ต้องขึ้นไปชั้นไหน เตรียมอะไรบ้าง"
    ]

    for i, q in enumerate(sample_queries, 1):
        sensor_data = iot_hw.read_environment()
        should_open = open_image and (i == 1)
        res = nav_ai.navigate(q, auto_open_image=should_open)
        iot_hw.activate_direction_led(res["direction_code"])
        tts.speak(res["spoken_response"])
        tts_sec = getattr(tts, "last_tts_time_sec", 0.0)
        res["latency_ms"] = round((res.get("llm_time_sec", 0.0) + res.get("map_routing_time_sec", 0.0) + tts_sec) * 1000.0, 2)
        db.log_interaction(res, sensor_data)
        display_navigation_result(res, sensor_data, tts_time_sec=tts_sec, tts_engine_label=getattr(tts, "last_engine_used", voice))

    iot_hw.cleanup()


def run_interactive(open_image: bool = True, enable_tts: bool = True, model_path: str = "", voice: str = TTS_MODEL):
    """โหมดถาม-ตอบสดผ่าน Terminal บน Raspberry Pi 4 / Mac"""
    nav_ai = GovNavLLM(model_path=model_path)
    iot_hw = GovNavIoTHardware()
    tts = GovNavTTSSpeaker(enabled=enable_tts, voice_name=voice)
    db = GovNavDBLogger()

    nav_ai.map_renderer.generate_all_map_images()

    print("\n" + "┏" + "━" * 78 + "┓")
    print("┃   🏛️  ยินดีต้อนรับสู่ระบบ GovNav (Government Navigator) — Offline Edge AI    ┃")
    print("┃   พิมพ์เรื่องที่ต้องการติดต่อราชการ (หรือพิมพ์ 'exit' เพื่อออกจากโปรแกรม)          ┃")
    print("┗" + "━" * 78 + "┛")

    try:
        while True:
            user_q = input("\n🎤 กรุณาระบุเรื่องที่มาติดต่อราชการ: ").strip()
            if not user_q or user_q.lower() in ("exit", "quit", "q"):
                print("ขอบคุณที่ใช้บริการ GovNav ค่ะ สวัสดีค่ะ!")
                break

            sensor_data = iot_hw.read_environment()
            res = nav_ai.navigate(user_q, auto_open_image=open_image)
            iot_hw.activate_direction_led(res["direction_code"])
            tts.speak(res["spoken_response"])
            tts_sec = getattr(tts, "last_tts_time_sec", 0.0)
            res["latency_ms"] = round((res.get("llm_time_sec", 0.0) + res.get("map_routing_time_sec", 0.0) + tts_sec) * 1000.0, 2)
            db.log_interaction(res, sensor_data)
            display_navigation_result(res, sensor_data, tts_time_sec=tts_sec, tts_engine_label=getattr(tts, "last_engine_used", voice))
    except KeyboardInterrupt:
        print("\nปิดการทำงานระบบ GovNav เรียบร้อยแล้ว")
    finally:
        iot_hw.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GovNav (Government Navigator) - RPi4 Smart Wayfinding System")
    parser.add_argument("--demo", action="store_true", help="รันโหมดสาธิตคำถามตัวอย่าง 3 ข้ออัตโนมัติ")
    parser.add_argument("--eval", action="store_true", help="รันชุดทดสอบความแม่นยำ 30 สถานการณ์ (6.1 & 6.2) ทันที")
    parser.add_argument("--open-image", action="store_true", help="สั่งเปิดไฟล์รูปภาพแผนที่ (.png) ขึ้นหน้าจออัตโนมัติ")
    parser.add_argument("--tts", action="store_true", help="เปิดเสียงพูดภาษาไทย VachanaTTS (Offline)")
    parser.add_argument(
        "--voice",
        type=str,
        default=TTS_MODEL,
        choices=list(AVAILABLE_VOICES.keys()),
        help="เลือกเสียงพูด VachanaTTS (ค่าเริ่มต้น: th_f_2 เสียงผู้หญิงที่ 2)",
    )
    parser.add_argument("--model", type=str, default="", help="ระบุพาธไฟล์โมเดล .gguf (ถ้าไม่ระบุจะค้นหาโมเดล 1B ใน ../models/ อัตโนมัติ)")
    args = parser.parse_args()

    if args.eval:
        from evaluate_govnav import run_evaluation_suite, print_report_to_terminal
        rep = run_evaluation_suite(voice_name=args.voice, bypass_tts_cache=True)
        print_report_to_terminal(rep)
    elif args.demo:
        run_demo(open_image=args.open_image, enable_tts=args.tts, model_path=args.model, voice=args.voice)
    else:
        run_interactive(open_image=args.open_image, enable_tts=args.tts, model_path=args.model, voice=args.voice)
