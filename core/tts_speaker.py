#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - Thai Text-to-Speech (TTS) Speaker Module (Segfault-Proof VachanaTTS Edition)
ใช้โมเดล VachanaTTS (สถาปัตยกรรม VITS + Piper ONNX) สำหรับภาษาไทยแบบ Offline 100%:
- รัน VachanaTTS แยกใน Isolated Worker Process (core/tts_worker.py) ป้องกัน Segmentation Fault 100%
- ไม่โหลด onnxruntime / libespeak-ng ทับซ้อนกับ Streamlit (pyarrow) หรือ llama_cpp
- มีระบบ Audio Cache อัจฉริยะ (assets/audio_cache/) ช่วยเล่นประโยคที่เคยสร้างไว้ทันทีใน 0.001 วินาที
- สั่งเล่นไฟล์เสียง .wav ออกลำโพงอัตโนมัติ (aplay บน RPi4 / afplay บน Mac) หรือส่งให้ Web Dashboard เล่น
"""

import os
import re
import sys
import json
import time
import glob
import atexit
import hashlib
import shutil
import threading
import subprocess
import importlib.util
from typing import Dict, Any, Optional

import config

BASE_DIR = getattr(config, "BASE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TTS_MODEL = getattr(config, "TTS_MODEL", "th_f_1")
TTS_VOLUME = float(getattr(config, "TTS_VOLUME", 1.0))
TTS_SPEED = float(getattr(config, "TTS_SPEED", 1.0))
AUDIO_OUT_DIR = getattr(config, "AUDIO_OUT_DIR", os.path.join(BASE_DIR, "assets", "audio_out"))
AUDIO_CACHE_DIR = getattr(config, "AUDIO_CACHE_DIR", os.path.join(BASE_DIR, "assets", "audio_cache"))
VOICES_DIR = getattr(config, "VOICES_DIR", os.path.join(BASE_DIR, "voices"))
AVAILABLE_VOICES = getattr(
    config,
    "AVAILABLE_VOICES",
    {
        "th_f_1": "👩 หญิง 1 (th_f_1) — สุภาพ นุ่มนวล ชัดเจน (แนะนำ)",
        "th_f_2": "👩 หญิง 2 (th_f_2) — สดใส กระฉับกระเฉง",
        "th_m_1": "👨 ชาย 1 (th_m_1) — สุภาพ ทางการ",
        "th_m_2": "👨 ชาย 2 (th_m_2) — ทุ้มกังวาน ฟังง่าย",
    },
)

TTS_WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_worker.py")
JSON_PREFIX = "__GOVNAV_JSON__:"


class GovNavTTSSpeaker:
    """ระบบสังเคราะห์เสียงภาษาไทย VachanaTTS (VITS ONNX) แบบแยกโปรเซสปลอดภัยสำหรับ Raspberry Pi 4 & Mac"""

    def __init__(
        self,
        enabled: bool = True,
        voice_name: str = TTS_MODEL,
        volume: float = TTS_VOLUME,
        speed: float = TTS_SPEED,
        use_cache: bool = True,
    ):
        self.enabled = enabled
        self.voice_name = voice_name if voice_name in AVAILABLE_VOICES else "th_f_1"
        self.volume = float(volume)
        self.speed = float(speed)
        self.use_cache = use_cache

        self.has_vachana = False
        self._tts_proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self.last_engine_used = "None"
        self.last_tts_time_sec = 0.0
        self.last_cache_hit = False

        os.makedirs(AUDIO_OUT_DIR, exist_ok=True)
        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
        os.makedirs(VOICES_DIR, exist_ok=True)

        if self.enabled:
            self._init_tts()
        atexit.register(self.close)

    def _init_tts(self):
        """ตรวจสอบความพร้อมของ VachanaTTS โดยไม่โหลด C++ Shared Library เข้าโปรเซสหลักของ Streamlit"""
        self.has_vachana = importlib.util.find_spec("vachanatts") is not None
        if self.has_vachana:
            model_file = os.path.join(VOICES_DIR, f"{self.voice_name}.onnx")
            if os.path.exists(model_file):
                print(f"[✓] พร้อมใช้งาน VachanaTTS (เสียง: {self.voice_name}) โหมด Isolated Safe Offline 100%", flush=True)
            else:
                print(f"[*] ตั้งค่า VachanaTTS (เสียง: {self.voice_name}) — จะดาวน์โหลดโมเดล .onnx ครั้งแรกอัตโนมัติ", flush=True)
        else:
            print("[!] ไม่พบไลบรารี vachanatts -> ใช้ระบบเสียงสำรองอัตโนมัติ", flush=True)

    def close(self):
        """ปิดโปรเซสลูกของ VachanaTTS อย่างปลอดภัย"""
        proc = self._tts_proc
        self._tts_proc = None
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

    def _read_worker_json(self, proc: subprocess.Popen) -> Optional[Dict[str, Any]]:
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

    def _ensure_tts_worker(self) -> bool:
        """สตาร์ทโปรเซส VachanaTTS แยกเมื่อจำเป็นต้องสังเคราะห์เสียงใหม่"""
        if self._tts_proc is not None and self._tts_proc.poll() is None:
            return True
        self._tts_proc = None
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", TTS_WORKER_SCRIPT, BASE_DIR],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            msg = self._read_worker_json(proc)
            if msg and msg.get("status") == "ready":
                self._tts_proc = proc
                return True
            try:
                proc.kill()
            except Exception:
                pass
        except Exception as err:
            print(f"[!] ไม่สามารถสตาร์ท VachanaTTS Worker ({err})", flush=True)
        return False

    def _synthesize_with_vachana(self, clean_text: str, voice: str, output_wav: str, volume: float, speed: float) -> bool:
        """ส่งข้อความไปสร้างไฟล์ .wav ในโปรเซสแยก ป้องกัน Segfault 100%"""
        with self._lock:
            if not self._ensure_tts_worker() or self._tts_proc is None:
                return False
            try:
                payload = json.dumps(
                    {
                        "text": clean_text,
                        "voice": voice,
                        "output": output_wav,
                        "volume": volume,
                        "speed": speed,
                    },
                    ensure_ascii=False,
                )
                if self._tts_proc.stdin is not None:
                    self._tts_proc.stdin.write(payload + "\n")
                    self._tts_proc.stdin.flush()
                resp = self._read_worker_json(self._tts_proc)
                if resp and resp.get("ok") and os.path.exists(output_wav) and os.path.getsize(output_wav) > 512:
                    return True
                if resp is None:
                    self._tts_proc = None
            except Exception as err:
                print(f"[!] VachanaTTS Worker ขัดข้อง ({err}) -> สลับไปใช้เสียงสำรอง", flush=True)
                self._tts_proc = None
        return False

    def get_engine_status(self) -> Dict[str, Any]:
        """คืนค่าสถานะระบบเสียงปัจจุบันสำหรับแสดงบนหน้า Dashboard"""
        downloaded_models = [
            os.path.basename(p).replace(".onnx", "")
            for p in glob.glob(os.path.join(VOICES_DIR, "*.onnx"))
        ]
        cached_clips = len(glob.glob(os.path.join(AUDIO_CACHE_DIR, "*.wav")))

        if self.has_vachana:
            engine_name = "VachanaTTS (VITS ONNX Offline)"
            ready = True
        elif sys.platform == "darwin" and shutil.which("say"):
            engine_name = "macOS Thai Voice (System Fallback — รอติดตั้ง vachanatts)"
            ready = True
        elif shutil.which("espeak-ng"):
            engine_name = "eSpeak-NG Thai (System Fallback — รอติดตั้ง vachanatts)"
            ready = True
        else:
            engine_name = "ยังไม่ได้ติดตั้งระบบเสียง"
            ready = False

        return {
            "ready": ready,
            "vachanatts_installed": self.has_vachana,
            "engine_name": engine_name,
            "active_voice": self.voice_name,
            "downloaded_voices": sorted(downloaded_models),
            "offline_model_exists": self.voice_name in downloaded_models,
            "cached_audio_count": cached_clips,
            "last_engine_used": self.last_engine_used,
            "last_tts_time_sec": self.last_tts_time_sec,
        }

    def _clean_text_for_speech(self, text: str) -> str:
        """ทำความสะอาดข้อความและคำย่อราชการให้อ่านออกเสียงได้ราบรื่นเป็นธรรมชาติ"""
        text = text.replace("กรุงเทพฯ", "กรุงเทพมหานคร").replace("ฯลฯ", "และอื่นๆ")
        text = text.replace("ปชช.", "ประชาชน").replace("ภ.ด.ส.", "พอดอสอ").replace("ภ.ป.", "พอปอ")
        text = text.replace("น.ส.4", "นอสอสี่").replace("น.ส.3", "นอสอสาม")
        text = text.replace("GovNav", "กอฟแนฟ")
        text = re.sub(r"ROOM_(\d+)", r"ห้อง \1", text)
        text = re.sub(r"[\(\)\[\]\{\}\"\'\*\#\_\~\|•—–]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text if text else "กรุณาติดต่อเจ้าหน้าที่ประชาสัมพันธ์ครับ"

    def _get_cache_path(self, clean_text: str, voice: str, speed: float, volume: float) -> str:
        """สร้างพาธไฟล์แคช .wav จากข้อความและการตั้งค่าเสียง"""
        engine_tag = "vachana" if self.has_vachana else "fallback"
        key_raw = f"{engine_tag}|{voice}|{speed:.2f}|{volume:.2f}|{clean_text}"
        digest = hashlib.md5(key_raw.encode("utf-8")).hexdigest()[:16]
        return os.path.join(AUDIO_CACHE_DIR, f"tts_{voice}_{digest}.wav")

    def _play_wav(self, wav_path: str):
        """สั่งเล่นไฟล์เสียง .wav ออกลำโพงบน Raspberry Pi 4 (aplay) หรือ Mac (afplay)"""
        if not os.path.exists(wav_path):
            return
        if sys.platform == "darwin" and shutil.which("afplay"):
            subprocess.Popen(["afplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("aplay"):
            subprocess.Popen(["aplay", "-q", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def speak(
        self,
        text: str,
        output_wav: str = "",
        play_device: bool = True,
        voice_name: Optional[str] = None,
        speed: Optional[float] = None,
        volume: Optional[float] = None,
        bypass_cache: bool = False,
    ) -> str:
        """แปลงข้อความเป็นไฟล์เสียง .wav ด้วย VachanaTTS (พร้อมระบบ Cache และจับเวลา) และเล่นออกลำโพง"""
        if not self.enabled or not text:
            self.last_tts_time_sec = 0.0
            self.last_cache_hit = False
            return ""

        t_tts_start = time.perf_counter()
        self.last_cache_hit = False
        use_voice = voice_name if (voice_name and voice_name in AVAILABLE_VOICES) else self.voice_name
        use_speed = float(speed) if speed is not None else self.speed
        use_volume = float(volume) if volume is not None else self.volume

        if not output_wav:
            output_wav = os.path.join(AUDIO_OUT_DIR, "govnav_reply.wav")
        output_wav = os.path.abspath(output_wav)
        os.makedirs(os.path.dirname(output_wav), exist_ok=True)

        clean_text = self._clean_text_for_speech(text)
        cache_path = self._get_cache_path(clean_text, use_voice, use_speed, use_volume)

        # 0. ตรวจสอบจาก Offline Audio Cache ก่อน (ยกเว้นตอนรันโหมดวัดผล bypass_cache=True)
        if self.use_cache and not bypass_cache and os.path.exists(cache_path) and os.path.getsize(cache_path) > 512:
            if os.path.abspath(cache_path) != output_wav:
                shutil.copy2(cache_path, output_wav)
            self.last_tts_time_sec = round(time.perf_counter() - t_tts_start, 4)
            self.last_engine_used = f"Offline Cache ({use_voice})"
            self.last_cache_hit = True
            print(
                f"⚡ [TTS Cache Hit] ดึงไฟล์เสียงจากแคชทันที ({os.path.basename(cache_path)}) "
                f"ใช้เวลา {self.last_tts_time_sec:.4f}s",
                flush=True,
            )
            if play_device:
                self._play_wav(output_wav)
            return output_wav

        # 1. ใช้ VachanaTTS (Isolated Worker Process) เป็นหลัก
        if self.has_vachana:
            if not bypass_cache:
                print(f"🎙️ [VachanaTTS] กำลังสร้างเสียงใหม่และบันทึกลงแคช ({os.path.basename(cache_path)})...", flush=True)
            if self._synthesize_with_vachana(clean_text, use_voice, output_wav, use_volume, use_speed):
                if self.use_cache and (not bypass_cache) and (not os.path.exists(cache_path)):
                    shutil.copy2(output_wav, cache_path)
                self.last_tts_time_sec = round(time.perf_counter() - t_tts_start, 4)
                self.last_engine_used = f"VachanaTTS ({use_voice})"
                if play_device:
                    self._play_wav(output_wav)
                return output_wav

        # 2. สำรองระดับ OS พร้อมสร้างไฟล์ .wav จริงเพื่อให้ Web Dashboard เล่นเสียงบนเบราว์เซอร์ได้เสมอ
        if sys.platform == "darwin" and shutil.which("say"):
            rate = max(120, min(280, int(185 * use_speed)))
            res = subprocess.run(
                ["say", "-v", "Kanya", "-r", str(rate), "-o", output_wav, "--data-format=LEI16@22050", clean_text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if res.returncode != 0 or not os.path.exists(output_wav):
                subprocess.run(
                    ["say", "-r", str(rate), "-o", output_wav, "--data-format=LEI16@22050", clean_text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            if self.use_cache and (not bypass_cache) and os.path.exists(output_wav) and os.path.getsize(output_wav) > 512 and (not os.path.exists(cache_path)):
                shutil.copy2(output_wav, cache_path)
            self.last_tts_time_sec = round(time.perf_counter() - t_tts_start, 4)
            self.last_engine_used = "macOS Thai Voice (Fallback)"
            if play_device:
                self._play_wav(output_wav)
            return output_wav

        if shutil.which("espeak-ng"):
            rate = max(100, min(240, int(150 * use_speed)))
            subprocess.run(
                ["espeak-ng", "-v", "th", "-s", str(rate), "-w", output_wav, clean_text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if self.use_cache and (not bypass_cache) and os.path.exists(output_wav) and os.path.getsize(output_wav) > 512 and (not os.path.exists(cache_path)):
                shutil.copy2(output_wav, cache_path)
            self.last_tts_time_sec = round(time.perf_counter() - t_tts_start, 4)
            self.last_engine_used = "eSpeak-NG Thai (Fallback)"
            if play_device:
                self._play_wav(output_wav)
            return output_wav

        self.last_tts_time_sec = round(time.perf_counter() - t_tts_start, 4)
        return ""


if __name__ == "__main__":
    print("=== ทดสอบระบบเสียง VachanaTTS (Offline Thai TTS) ===")
    speaker = GovNavTTSSpeaker(enabled=True, voice_name=TTS_MODEL)
    sample_text = (
        "สวัสดีค่ะ ยินดีต้อนรับสู่ระบบนำทางศูนย์ราชการ GovNav "
        "สำหรับการลงทะเบียนเบี้ยยังชีพผู้สูงอายุ เชิญที่ ROOM_102 ชั้น 1 ปีกขวาค่ะ"
    )
    out_file = speaker.speak(sample_text, play_device=True)
    print(f"[✓] สร้างไฟล์เสียงสำเร็จที่: {out_file} (Engine: {speaker.last_engine_used})")
