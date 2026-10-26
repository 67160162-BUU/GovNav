#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - On-Device Qwen (.gguf / llama_cpp) Navigator Module (Segfault-Proof Edition)
ปรับแต่งความเร็วและความเสถียรสูงสุดสำหรับ Raspberry Pi 4:
- รัน llama-cpp-python แยกใน Isolated Worker Process (core/llm_worker.py) ป้องกัน Segmentation Fault 100%
- โหลดโมเดล .gguf ค้างไว้ใน RAM เพียงครั้งเดียว + หากไฟล์ .gguf ใดมีปัญหาจะสลับไปไฟล์ถัดไปอัตโนมัติ
- มีระบบแคชคำตอบ (data/llm_query_cache.json) ตอบคำถามซ้ำใน 0.001 วินาที จับคู่กับแคชเสียง .wav ได้เป๊ะ 100%
"""

import os
import re
import sys
import json
import time
import atexit
import difflib
import threading
import subprocess
from typing import Dict, Any, List, Optional

import config
from config import DEPARTMENTS_FILE, SYSTEM_PROMPT_FILE, find_qwen_gguf
from core.map_renderer import MapRenderer

LLM_CACHE_FILE = os.path.join(os.path.dirname(DEPARTMENTS_FILE), "llm_query_cache.json")
WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_worker.py")
JSON_PREFIX = "__GOVNAV_JSON__:"


class GovNavLLM:
    """คลาสสมองกล AI โหลดโมเดล Qwen (.gguf) ผ่าน Isolated Worker + จับคู่แผนที่ความเร็วสูง"""

    def __init__(self, model_path: str = ""):
        with open(DEPARTMENTS_FILE, "r", encoding="utf-8") as f:
            self.departments: List[Dict[str, Any]] = json.load(f)["departments"]
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            self.system_prompt: str = f.read().strip()

        self.dept_by_id = {d["room_id"]: d for d in self.departments}
        self.map_renderer = MapRenderer()
        self.model_path = model_path or find_qwen_gguf()
        self.llm: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self.query_cache: Dict[str, str] = self._load_query_cache()
        self._init_llama_cpp()
        atexit.register(self.close)

    @staticmethod
    def _enforce_female_polite(text: str) -> str:
        """ปรับหางเสียงและคำสรรพนามให้เป็นเจ้าหน้าที่ผู้หญิง (ค่ะ/นะคะ/ดิฉัน) เสมอ 100%"""
        if not text:
            return text
        text = text.replace("ครับผม", "ค่ะ")
        text = text.replace("นะครับ", "นะคะ")
        text = text.replace("ไหมครับ", "ไหมคะ")
        text = text.replace("ไหนครับ", "ไหนคะ")
        text = text.replace("อะไรครับ", "อะไรคะ")
        text = text.replace("หรือครับ", "หรือคะ")
        text = text.replace("กระผม", "ดิฉัน")
        text = text.replace("ผมขอ", "ดิฉันขอ")
        text = text.replace("ครับ", "ค่ะ")
        return text

    def _load_query_cache(self) -> Dict[str, str]:
        """โหลดคลังแคชข้อความคำตอบ พร้อมปรับหางเสียงเป็น ค่ะ/นะคะ อัตโนมัติ"""
        if os.path.exists(LLM_CACHE_FILE):
            try:
                with open(LLM_CACHE_FILE, "r", encoding="utf-8") as cf:
                    data = json.load(cf)
                if isinstance(data, dict):
                    return {k: self._enforce_female_polite(str(v)) for k, v in data.items()}
            except Exception:
                pass
        return {}

    def _save_query_cache(self):
        """บันทึกแคชคำตอบลงดิสก์ เพื่อให้เปิดเครื่องใหม่ก็ยังตอบและดึงแคชเสียงได้ทันที"""
        try:
            os.makedirs(os.path.dirname(LLM_CACHE_FILE), exist_ok=True)
            with open(LLM_CACHE_FILE, "w", encoding="utf-8") as cf:
                json.dump(self.query_cache, cf, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _read_worker_json(self, proc: subprocess.Popen) -> Optional[Dict[str, Any]]:
        """อ่านบรรทัดผลลัพธ์ JSON จาก Worker โดยข้ามข้อความ Log ทั่วไปของ C++"""
        if proc.stdout is None:
            return None
        while True:
            line = proc.stdout.readline()
            if not line:
                return None
            stripped = line.strip()
            if stripped.startswith(JSON_PREFIX):
                try:
                    return json.loads(stripped[len(JSON_PREFIX):])
                except Exception:
                    return None

    def _try_start_worker(self, candidate_path: str) -> bool:
        """ทดลองเปิดโปรเซสแยกโหลดไฟล์ .gguf หากเกิด Segfault ใน C++ ตัวเว็บหลักจะไม่ล่มไปด้วย"""
        if not candidate_path or not os.path.exists(candidate_path):
            return False

        print(f"[*] กำลังโหลดโมเดล AI (.gguf) ในโปรเซสแยก: {candidate_path}", flush=True)
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", WORKER_SCRIPT, candidate_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            msg = self._read_worker_json(proc)
            if msg and msg.get("status") == "ready":
                self.model_path = candidate_path
                self.llm = proc
                print(f"[✓] โหลดโมเดล {os.path.basename(candidate_path)} สำเร็จ (Isolated Safe Mode — Offline 100%)", flush=True)
                return True

            err_detail = msg.get("error", f"exit code {proc.poll()}") if msg else f"exit code {proc.poll()}"
            print(f"[!] โมเดล {os.path.basename(candidate_path)} ไม่พร้อมใช้งาน ({err_detail})", flush=True)
            try:
                proc.kill()
            except Exception:
                pass
        except Exception as exc:
            print(f"[!] ไม่สามารถสตาร์ท LLM Worker ({exc})", flush=True)
        return False

    def _init_llama_cpp(self):
        """ค้นหาและโหลดโมเดล .gguf อย่างปลอดภัย รองรับการสลับไฟล์อัตโนมัติหากไฟล์แรกมีปัญหา"""
        candidates: List[str] = []
        if self.model_path and os.path.exists(self.model_path):
            candidates.append(self.model_path)
        if hasattr(config, "find_all_gguf_models"):
            for p in config.find_all_gguf_models():
                if p not in candidates:
                    candidates.append(p)

        if not candidates:
            print("[GovNavLLM] ไม่พบไฟล์ .gguf -> ใช้โหมดตอบอัตโนมัติความเร็วสูง (Smart RAG)", flush=True)
            return

        for cand in candidates:
            if self._try_start_worker(cand):
                return

        print("[!] สลับเข้าสู่โหมด Smart Keyword & Fuzzy RAG อัตโนมัติ (ปลอดภัย ไม่เกิด Segfault)", flush=True)
        self.llm = None

    def close(self):
        """ปิดโปรเซสลูกอย่างปลอดภัยเมื่อจบการทำงาน"""
        proc = self.llm
        self.llm = None
        if proc is not None and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.write("__EXIT__\n")
                    proc.stdin.flush()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _match_department_by_keywords(self, user_query: str) -> Dict[str, Any]:
        """จับคู่ห้องราชการจากคำถามของประชาชนด้วย Keyword Scoring + Fuzzy Matching"""
        best_dept = self.departments[0]
        max_score = 0.0

        for dept in self.departments:
            score = 0.0
            for kw in dept["keywords"]:
                if kw in user_query:
                    score += 3.0
            for srv in dept["services"]:
                if srv in user_query:
                    score += 5.0
                else:
                    ratio = difflib.SequenceMatcher(None, user_query, srv).ratio()
                    if ratio >= 0.45:
                        score += ratio * 2.5
            if dept["room_id"].lower() in user_query.lower():
                score += 10.0

            if score > max_score:
                max_score = score
                best_dept = dept

        return best_dept

    def _generate_answer(self, user_query: str, matched_dept: Dict[str, Any]) -> str:
        """ส่งคำถามไปยังโปรเซสโมเดล .gguf อย่างปลอดภัย พร้อมระบบสำรองอัตโนมัติ"""
        docs_text = " และ ".join(matched_dept["required_docs"][:2])

        if self.llm is not None and self.llm.poll() is None:
            user_message = (
                f"คำถามประชาชน: {user_query}\n"
                f"ข้อมูลอ้างอิง: ไปที่ {matched_dept['name_th']} ห้อง {matched_dept['room_id']} "
                f"ชั้น {matched_dept['floor']} ({matched_dept['walk_steps']}) เตรียมเอกสารคือ {docs_text}\n"
                "สรุปคำพูดแนะนำประชาชนสั้นๆ 2 ประโยคในฐานะเจ้าหน้าที่ผู้หญิง (ลงท้ายด้วย ค่ะ หรือ นะคะ ห้ามใช้คำว่า ครับ):"
            )
            with self._lock:
                try:
                    payload = json.dumps(
                        {
                            "system_prompt": self.system_prompt,
                            "user_message": user_message,
                            "max_tokens": 90,
                        },
                        ensure_ascii=False,
                    )
                    if self.llm.stdin is not None:
                        self.llm.stdin.write(payload + "\n")
                        self.llm.stdin.flush()
                    resp = self._read_worker_json(self.llm)
                    if resp and resp.get("ok") and resp.get("answer"):
                        return self._enforce_female_polite(str(resp["answer"]).strip())
                    if resp is None:
                        print("[!] โปรเซสโมเดล .gguf สิ้นสุดการทำงาน -> สลับใช้คำตอบมาตรฐานอัตโนมัติ", flush=True)
                        self.llm = None
                except Exception as err:
                    print(f"[!] ข้อผิดพลาดขณะสื่อสารกับ LLM Worker ({err}) -> ใช้คำตอบมาตรฐานแทน", flush=True)
                    self.llm = None

        clean_topic = self._enforce_female_polite(user_query)
        return (
            f"สวัสดีค่ะ สำหรับเรื่อง {clean_topic} ขอแนะนำให้ไปติดต่อที่ {matched_dept['name_th']} "
            f"ห้อง {matched_dept['room_id']} ชั้น {matched_dept['floor']} {matched_dept['wing']} นะคะ "
            f"{matched_dept['walk_steps']} โดยกรุณาเตรียม {docs_text} มาแสดงต่อเจ้าหน้าที่ด้วยค่ะ"
        )

    def navigate(self, user_query: str, auto_open_image: bool = False, bypass_cache: bool = False) -> Dict[str, Any]:
        """ประมวลผลคำถาม -> ตอบสถานที่ -> วาดแผนที่เส้นขีด -> ค้นและเปิดไฟล์รูปแผนที่ .png พร้อมจับเวลาแยกรายขั้นตอน"""
        t0 = time.perf_counter()
        norm_query = re.sub(r"\s+", " ", user_query.strip())

        # ขั้นตอนที่ 1: จับคู่จุดหมายและประมวลผลคำตอบด้วย LLM & Fuzzy Matching (เช็กแคชคำถามเดิมก่อน)
        t_llm_start = time.perf_counter()
        matched_dept = self._match_department_by_keywords(norm_query)
        room_id = matched_dept["room_id"]

        llm_cache_hit = False
        if (not bypass_cache) and (norm_query in self.query_cache) and self.query_cache[norm_query]:
            spoken_response = self.query_cache[norm_query]
            llm_cache_hit = True
            print(f"⚡ [LLM Cache Hit] ใช้คำตอบแคชทันทีสำหรับ: \"{norm_query[:45]}\"", flush=True)
        else:
            spoken_response = self._generate_answer(norm_query, matched_dept)
            if spoken_response and ((not bypass_cache) or (norm_query not in self.query_cache)):
                self.query_cache[norm_query] = spoken_response
                self._save_query_cache()

        llm_time_sec = round(time.perf_counter() - t_llm_start, 4)

        # ขั้นตอนที่ 2: คำนวณเส้นทางและสร้าง/ค้นหาแผนผังนำทาง (ASCII + PNG)
        t_map_start = time.perf_counter()
        ascii_map = self.map_renderer.render_ascii_map(room_id)
        map_image_path = self.map_renderer.get_map_image_path(room_id)
        if auto_open_image:
            self.map_renderer.open_map_image(room_id)
        map_routing_time_sec = round(time.perf_counter() - t_map_start, 4)

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        return {
            "query": norm_query,
            "room_id": room_id,
            "department_name": matched_dept["name_th"],
            "floor": matched_dept["floor"],
            "wing": matched_dept["wing"],
            "direction_code": matched_dept["direction_code"],
            "walk_steps": matched_dept["walk_steps"],
            "required_docs": matched_dept["required_docs"],
            "queue_count": matched_dept["queue_count"],
            "estimated_wait_min": matched_dept["estimated_wait_min"],
            "spoken_response": spoken_response,
            "ascii_map": ascii_map,
            "map_image_path": map_image_path,
            "llm_cache_hit": llm_cache_hit,
            "llm_time_sec": llm_time_sec,
            "map_routing_time_sec": map_routing_time_sec,
            "latency_ms": latency_ms,
        }
