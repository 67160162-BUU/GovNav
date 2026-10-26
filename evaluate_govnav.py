#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
GovNav - Experimental Evaluation & Benchmarking Suite (Section 6.1 & 6.2)
=============================================================================
สคริปต์สำหรับวัดผลความแม่นยำ 30 สถานการณ์ (6.1 Accuracy Test)
และวัดเวลาตอบสนองแยกรายขั้นตอน (6.2 Response Latency) สำหรับใส่เล่มรายงาน

* ปลอดภัย 100%: ไม่ลบไฟล์แคชเสียงเดิมใน assets/audio_cache/ *

วิธีรันบน Raspberry Pi 4:
    python3 evaluate_govnav.py
=============================================================================
"""

import os
import csv
import json
import time
import inspect
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

import config
from core.llm_navigator import GovNavLLM
from core.tts_speaker import GovNavTTSSpeaker

BASE_DIR = getattr(config, "BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = getattr(config, "DATA_DIR", os.path.join(BASE_DIR, "data"))
AUDIO_OUT_DIR = getattr(config, "AUDIO_OUT_DIR", os.path.join(BASE_DIR, "assets", "audio_out"))
SCENARIOS_FILE = os.path.join(DATA_DIR, "eval_scenarios_30.json")
EVAL_REPORT_JSON = os.path.join(DATA_DIR, "eval_report.json")
EVAL_REPORT_CSV = os.path.join(DATA_DIR, "eval_report_details.csv")


def load_scenarios(limit: int = 0) -> List[Dict[str, Any]]:
    with open(SCENARIOS_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)["scenarios"]
    return items[:limit] if limit and limit > 0 else items


def run_evaluation_suite(
    nav_ai: Optional[GovNavLLM] = None,
    tts_speaker: Optional[GovNavTTSSpeaker] = None,
    limit: int = 0,
    voice_name: str = "th_f_2",
    bypass_tts_cache: bool = True,
    progress_callback: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """รันชุดทดสอบความแม่นยำและเวลาตอบสนอง พร้อมบันทึกไฟล์รายงาน JSON และ CSV"""
    if nav_ai is None:
        nav_ai = GovNavLLM()
    nav_ai.map_renderer.generate_all_map_images()

    if tts_speaker is None:
        init_params = inspect.signature(GovNavTTSSpeaker.__init__).parameters
        if "voice_name" in init_params:
            tts_speaker = GovNavTTSSpeaker(enabled=True, voice_name=voice_name)
        else:
            tts_speaker = GovNavTTSSpeaker(enabled=True)

    nav_params = inspect.signature(nav_ai.navigate).parameters
    speak_params = inspect.signature(tts_speaker.speak).parameters

    scenarios = load_scenarios(limit=limit)
    total_n = len(scenarios)

    os.makedirs(AUDIO_OUT_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_eval_wav = os.path.join(AUDIO_OUT_DIR, "_eval_probe_temp.wav")

    llm_pass_count = 0
    routing_pass_count = 0
    tts_map_pass_count = 0

    details: List[Dict[str, Any]] = []
    sum_llm_sec = 0.0
    sum_map_sec = 0.0
    sum_tts_sec = 0.0
    sum_total_sec = 0.0

    for idx, item in enumerate(scenarios, 1):
        query = item["query"]
        exp_room = item["expected_room_id"]
        exp_dir = item["expected_direction"]

        t_all_start = time.perf_counter()

        # 1 & 2: LLM & Fuzzy Matching + Path Finding & Map Lookup
        if "bypass_cache" in nav_params:
            res = nav_ai.navigate(query, auto_open_image=False, bypass_cache=bypass_tts_cache)
        else:
            res = nav_ai.navigate(query, auto_open_image=False)
        llm_sec = float(res.get("llm_time_sec", round(res.get("latency_ms", 0.0) / 1000.0, 4)))
        map_sec = float(res.get("map_routing_time_sec", 0.005))

        # 3: TTS Generation (ข้ามการอ่านแคชชั่วคราวเพื่อวัดเวลาสังเคราะห์เสียงจริง โดยไม่ลบแคชเดิม)
        if os.path.exists(temp_eval_wav):
            os.remove(temp_eval_wav)

        t_tts_start = time.perf_counter()
        if "bypass_cache" in speak_params:
            out_wav = tts_speaker.speak(
                res["spoken_response"],
                output_wav=temp_eval_wav,
                play_device=False,
                voice_name=voice_name,
                bypass_cache=bypass_tts_cache,
            )
        elif "play_device" in speak_params:
            out_wav = tts_speaker.speak(
                res["spoken_response"],
                output_wav=temp_eval_wav,
                play_device=False,
                voice_name=voice_name,
            )
        else:
            out_wav = tts_speaker.speak(res["spoken_response"], output_wav=temp_eval_wav)
        tts_sec = getattr(tts_speaker, "last_tts_time_sec", 0.0) or round(time.perf_counter() - t_tts_start, 4)
        total_sec = round(time.perf_counter() - t_all_start, 4)

        # ตรวจสอบความถูกต้องแต่ละหัวข้อ
        is_llm_match_ok = (res["room_id"] == exp_room)
        is_routing_ok = (res["direction_code"] == exp_dir and bool(res.get("walk_steps")))
        has_valid_wav = bool(out_wav and os.path.exists(out_wav) and os.path.getsize(out_wav) > 512)
        has_valid_map = bool(res.get("map_image_path") and os.path.exists(res["map_image_path"]) and res.get("ascii_map"))
        is_tts_map_ok = has_valid_wav and has_valid_map

        if is_llm_match_ok:
            llm_pass_count += 1
        if is_routing_ok:
            routing_pass_count += 1
        if is_tts_map_ok:
            tts_map_pass_count += 1

        sum_llm_sec += llm_sec
        sum_map_sec += map_sec
        sum_tts_sec += tts_sec
        sum_total_sec += total_sec

        row_record = {
            "id": item["id"],
            "category": item["category"],
            "query": query,
            "expected_room": exp_room,
            "predicted_room": res["room_id"],
            "llm_match_pass": is_llm_match_ok,
            "routing_pass": is_routing_ok,
            "tts_map_pass": is_tts_map_ok,
            "llm_time_sec": round(llm_sec, 3),
            "map_time_sec": round(map_sec, 3),
            "tts_time_sec": round(tts_sec, 3),
            "total_time_sec": round(total_sec, 3),
        }
        details.append(row_record)

        if progress_callback is not None:
            progress_callback(idx, total_n, row_record)

    # ลบเฉพาะไฟล์ชั่วคราวของการทดสอบ (ไฟล์แคชเดิมทั้งหมดอยู่ครบ 100%)
    if os.path.exists(temp_eval_wav):
        try:
            os.remove(temp_eval_wav)
        except OSError:
            pass

    avg_llm = round(sum_llm_sec / max(1, total_n), 2)
    avg_map = round(sum_map_sec / max(1, total_n), 2)
    avg_tts = round(sum_tts_sec / max(1, total_n), 2)
    avg_total = round(sum_total_sec / max(1, total_n), 2)

    accuracy_table = [
        {
            "topic": "ความแม่นยำ LLM & Fuzzy Matching (ระบุจุดหมาย)",
            "total": total_n,
            "passed": llm_pass_count,
            "accuracy_pct": round((llm_pass_count / max(1, total_n)) * 100, 1),
        },
        {
            "topic": "ความถูกต้องในการคำนวณเส้นทาง (Routing & LED Direction)",
            "total": total_n,
            "passed": routing_pass_count,
            "accuracy_pct": round((routing_pass_count / max(1, total_n)) * 100, 1),
        },
        {
            "topic": "การสังเคราะห์เสียงและการแสดงภาพแผนที่ (VachanaTTS & Map)",
            "total": total_n,
            "passed": tts_map_pass_count,
            "accuracy_pct": round((tts_map_pass_count / max(1, total_n)) * 100, 1),
        },
    ]

    report_data = {
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_scenarios": total_n,
        "llm_mode": "Qwen GGUF (llama.cpp)" if nav_ai.llm is not None else "Smart Keyword & Fuzzy RAG",
        "tts_engine": getattr(tts_speaker, "last_engine_used", f"VachanaTTS ({voice_name})"),
        "accuracy_table": accuracy_table,
        "latency_summary": {
            "llm_inference_sec": avg_llm,
            "path_finding_map_sec": avg_map,
            "tts_generation_sec": avg_tts,
            "total_latency_sec": avg_total,
        },
        "details": details,
    }

    with open(EVAL_REPORT_JSON, "w", encoding="utf-8") as jf:
        json.dump(report_data, jf, ensure_ascii=False, indent=2)

    with open(EVAL_REPORT_CSV, "w", encoding="utf-8-sig", newline="") as cf:
        if details:
            writer = csv.DictWriter(cf, fieldnames=list(details[0].keys()))
            writer.writeheader()
            writer.writerows(details)

    return report_data


def print_report_to_terminal(report: Dict[str, Any]):
    """พิมพ์ตารางสรุปผล 6.1 และ 6.2 ออกทางหน้าจอ Terminal ให้ตรงตามรูปแบบรายงาน"""
    print("\n" + "═" * 84)
    print("📊 6. ผลการทดลองและการวิเคราะห์ (Experimental Results & Discussion)")
    print(f"   เวลาที่ทำการทดสอบ: {report['evaluated_at']} | จำนวนสถานการณ์: {report['total_scenarios']} ข้อ")
    print(f"   โหมดประมวลผล: {report['llm_mode']} + {report['tts_engine']}")
    print("═" * 84)

    print("\n6.1 ผลการทดสอบความแม่นยำของระบบ (Accuracy Test)")
    print("┌" + "─" * 52 + "┬" + "─" * 10 + "┬" + "─" * 10 + "┬" + "─" * 11 + "┐")
    print(f"│ {'หัวข้อการทดสอบ':<50} │ {'ทดสอบ':^8} │ {'ผ่าน':^8} │ {'แม่นยำ(%)':^9} │")
    print("├" + "─" * 52 + "┼" + "─" * 10 + "┼" + "─" * 10 + "┼" + "─" * 11 + "┤")
    for row in report["accuracy_table"]:
        print(
            f"│ {row['topic']:<50} │ {row['total']:^8} │ {row['passed']:^8} │ "
            f"{str(row['accuracy_pct']) + '%':^9} │"
        )
    print("└" + "─" * 52 + "┴" + "─" * 10 + "┴" + "─" * 10 + "┴" + "─" * 11 + "┘")

    lat = report["latency_summary"]
    print("\n6.2 ผลการทดสอบเวลาตอบสนองเฉลี่ย (Response Latency)")
    print(f"  • LLM & Fuzzy Matching Time (llama.cpp on Pi 4) : ~{lat['llm_inference_sec']:.2f} วินาที")
    print(f"  • Path Finding & Image Generation               : ~{lat['path_finding_map_sec']:.2f} วินาที")
    print(f"  • TTS Generation Time (VachanaTTS ONNX)         : ~{lat['tts_generation_sec']:.2f} วินาที")
    print(f"  • เวลาประมวลผลรวมทั้งสิ้น (Total Latency)         : ~{lat['total_latency_sec']:.2f} วินาที")
    print("─" * 84)
    print(f"💾 บันทึกผลสำหรับแสดงบนเว็บ Streamlit แล้วที่ : {EVAL_REPORT_JSON}")
    print(f"📄 บันทึกตารางละเอียดเปิดใน Excel แล้วที่     : {EVAL_REPORT_CSV}")
    print("═" * 84 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GovNav 30-Scenario Accuracy & Latency Evaluator")
    parser.add_argument("--limit", type=int, default=0, help="จำกัดจำนวนข้อทดสอบ (0 = รันครบทั้ง 30 สถานการณ์)")
    parser.add_argument("--voice", type=str, default="th_f_2", help="เสียง VachanaTTS ที่ใช้วัดผล")
    parser.add_argument("--use-cache", action="store_true", help="เปิดอ่านจากแคชเสียง (ค่าเริ่มต้นคือปิดแคชเพื่อวัดเวลาสร้างเสียงจริง)")
    args = parser.parse_args()

    print("🚀 เริ่มต้นการทดสอบความแม่นยำและเวลาตอบสนองของระบบ GovNav...")

    def _on_step(idx: int, total: int, rec: Dict[str, Any]):
        mark = "✅ PASS" if (rec["llm_match_pass"] and rec["routing_pass"] and rec["tts_map_pass"]) else "❌ FAIL"
        print(
            f"[{idx:02d}/{total:02d}] {mark} | เป้าหมาย: {rec['expected_room']} -> ตอบ: {rec['predicted_room']} | "
            f"LLM: {rec['llm_time_sec']:.2f}s | Map: {rec['map_time_sec']:.2f}s | "
            f"TTS: {rec['tts_time_sec']:.2f}s | รวม: {rec['total_time_sec']:.2f}s"
        )

    final_report = run_evaluation_suite(
        limit=args.limit,
        voice_name=args.voice,
        bypass_tts_cache=not args.use_cache,
        progress_callback=_on_step,
    )
    print_report_to_terminal(final_report)
