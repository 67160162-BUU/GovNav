#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - Isolated Qwen (.gguf) Worker Process
รัน llama-cpp-python แยกโปรเซสบน Main Thread ของตัวเอง:
1. ป้องกันปัญหา Segmentation Fault จากการชนกันของ C++ Shared Libraries (pyarrow / onnxruntime / libllama)
2. โหลดโมเดล .gguf ค้างไว้ใน RAM เพียงครั้งเดียว ตอบกลับความเร็วสูงผ่าน Pipe
"""

import os
import sys
import json

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

PREFIX = "__GOVNAV_JSON__:"


def main():
    if len(sys.argv) < 2:
        print(PREFIX + json.dumps({"status": "error", "error": "missing model_path"}), flush=True)
        return

    model_path = sys.argv[1]
    try:
        from llama_cpp import Llama
        llm = Llama(
            model_path=model_path,
            n_ctx=512,
            n_threads=3,
            n_batch=128,
            verbose=False,
        )
        print(
            PREFIX + json.dumps({"status": "ready", "model": os.path.basename(model_path)}, ensure_ascii=False),
            flush=True,
        )
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
            sys_prompt = req.get("system_prompt", "")
            user_msg = req.get("user_message", "")
            max_tokens = int(req.get("max_tokens", 90))

            sys.stderr.write("⏳ [AI กำลังประมวลผลคำตอบ...] ")
            sys.stderr.flush()

            stream = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
                stream=True,
            )
            collected = []
            for chunk in stream:
                delta = chunk["choices"][0].get("delta", {}).get("content", "")
                if delta:
                    sys.stderr.write(delta)
                    sys.stderr.flush()
                    collected.append(delta)
            sys.stderr.write("\n")
            sys.stderr.flush()

            answer = "".join(collected).strip()
            print(PREFIX + json.dumps({"ok": True, "answer": answer}, ensure_ascii=False), flush=True)
        except Exception as err:
            print(PREFIX + json.dumps({"ok": False, "error": str(err)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
