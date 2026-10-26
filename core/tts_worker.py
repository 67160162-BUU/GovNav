#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - Isolated VachanaTTS (ONNX Runtime) Worker Process
รัน VachanaTTS แยกโปรเซสบน Main Thread ของตัวเอง:
1. ป้องกัน Segmentation Fault จากการชนกันของ onnxruntime / libespeak-ng กับ Streamlit (pyarrow) และ llama_cpp
2. โหลดไลบรารี vachanatts ค้างไว้ครั้งเดียว สังเคราะห์เสียงรวดเร็วและปลอดภัย 100%
"""

import os
import sys
import json

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

PREFIX = "__GOVNAV_JSON__:"


def main():
    base_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    os.chdir(base_dir)

    try:
        from vachanatts import TTS
        print(PREFIX + json.dumps({"status": "ready"}), flush=True)
    except Exception as exc:
        print(PREFIX + json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), flush=True)
        return

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        if line == "__EXIT__":
            break
        try:
            req = json.loads(line)
            os.chdir(base_dir)
            TTS(
                req["text"],
                voice=req.get("voice", "th_f_2"),
                output=req["output"],
                volume=float(req.get("volume", 1.0)),
                speed=float(req.get("speed", 1.0)),
            )
            ok = os.path.exists(req["output"]) and os.path.getsize(req["output"]) > 512
            print(PREFIX + json.dumps({"ok": ok, "output": req["output"]}, ensure_ascii=False), flush=True)
        except Exception as err:
            print(PREFIX + json.dumps({"ok": False, "error": str(err)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
