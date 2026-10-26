#!/usr/bin/env bash
# =============================================================================
# GovNav - สคริปต์ติดตั้งและรันหน้าจอ Web Kiosk Dashboard บน Raspberry Pi 4
# (ฉบับป้องกัน Segmentation Fault / RAM Exhaustion / C++ Thread Collision 100%)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# หากเผลอวางสคริปต์ไว้ในโฟลเดอร์ย่อย core/ ให้ถอยออกมาที่โฟลเดอร์หลัก GovNav/ อัตโนมัติ
if [ "$(basename "$SCRIPT_DIR")" = "core" ]; then
    cd .. || exit 1
fi

echo "======================================================================"
echo "  กำลังเริ่มต้นระบบ GovNav (Government Navigator) บน Raspberry Pi 4"
echo "======================================================================"

# 0. เคลียร์โปรเซสค้างเก่า (ป้องกันการกิน RAM ซ้ำซ้อนจนเกิด Segfault)
pkill -f "streamlit run app_dashboard.py" 2>/dev/null || true
pkill -f "core/llm_worker.py" 2>/dev/null || true
pkill -f "core/tts_worker.py" 2>/dev/null || true
sleep 0.5

# ตั้งค่าตัวแปรระดับระบบสำหรับ ARM64 (Raspberry Pi 4) ป้องกัน jemalloc / OpenMP Segfault
export OMP_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export MKL_NUM_THREADS=2
export NUMEXPR_NUM_THREADS=2
export VECLIB_MAXIMUM_THREADS=2
export TOKENIZERS_PARALLELISM=false
export ARROW_DEFAULT_MEMORY_POOL=system
export MALLOC_ARENA_MAX=2

# 1. ค้นหาและเปิดใช้งาน Virtual Environment (venv) อัตโนมัติ
VENV_FOUND=0
for VENV_PATH in \
    "$HOME/qwen_rpi4/venv/bin/activate" \
    "$HOME/venv/bin/activate" \
    "../venv/bin/activate" \
    "../../venv/bin/activate" \
    "./venv/bin/activate" \
    "$HOME/qwen_rpi4/.venv/bin/activate" \
    "../.venv/bin/activate"; do
    if [ -f "$VENV_PATH" ]; then
        echo "[OK] เปิดใช้งาน Virtual Environment: $VENV_PATH"
        # shellcheck disable=SC1090
        source "$VENV_PATH"
        VENV_FOUND=1
        break
    fi
done

PYTHON_BIN="$(command -v python3 || command -v python)"

# 2. ตรวจสอบว่าติดตั้ง vachanatts หรือยัง
if ! "$PYTHON_BIN" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('vachanatts') else 1)" >/dev/null 2>&1; then
    echo "[*] กำลังติดตั้งไลบรารี VachanaTTS (Offline ONNX) สำหรับ Raspberry Pi 4..."
    if [ "$VENV_FOUND" -eq 1 ]; then
        pip install -r requirements.txt
    else
        pip3 install --break-system-packages -r requirements.txt
    fi
fi

# 3. ทดสอบว่า import streamlit ผ่านปกติหรือไม่ (ซ่อมแซมกรณี NumPy 2.x ชนกับ PyArrow บน ARM64)
if ! "$PYTHON_BIN" -c "import streamlit" >/dev/null 2>&1; then
    echo "[!] ตรวจพบความไม่เข้ากันของ C++ Binary ใน Streamlit/NumPy กำลังปรับรุ่นให้อัตโนมัติ..."
    if [ "$VENV_FOUND" -eq 1 ]; then
        pip install "numpy<2.0"
    else
        pip3 install --break-system-packages "numpy<2.0"
    fi
fi

# 4. ตรวจสอบไฟล์โมเดลเสียงผู้หญิงที่ 2 (th_f_2.onnx) ในโฟลเดอร์ voices/
if [ ! -f "voices/th_f_2.onnx" ]; then
    echo "[*] กำลังดาวน์โหลดโมเดลเสียงผู้หญิงที่ 2 (th_f_2.onnx) เก็บไว้ใน voices/ สำหรับโหมด Offline 100%..."
    "$PYTHON_BIN" download_voices_offline.py || true
fi

# 5. แสดง IP Address ของบอร์ด Raspberry Pi 4
RPI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "----------------------------------------------------------------------"
echo "[OK] เปิดหน้าจอ GovNav Kiosk Dashboard พร้อมใช้งาน! (ไม่ต้องกรอกอีเมล)"
echo "   - เปิดบนจอที่ต่อกับ RPi4 : http://localhost:8501"
if [ -n "$RPI_IP" ]; then
    echo "   - เปิดจากคอม/มือถือในวงแลน : http://${RPI_IP}:8501"
fi
echo "----------------------------------------------------------------------"

exec "$PYTHON_BIN" -m streamlit run app_dashboard.py \
    --server.address 0.0.0.0 \
    --server.port 8501 \
    --server.headless true \
    --browser.gatherUsageStats false
