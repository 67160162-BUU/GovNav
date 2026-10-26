#!/usr/bin/env bash
# =============================================================================
# GovNav - สคริปต์ติดตั้งและรันหน้าจอ Web Kiosk Dashboard บน Raspberry Pi 4
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# หากเผลอวางสคริปต์ไว้ในโฟลเดอร์ย่อย core/ ให้ถอยออกมาที่โฟลเดอร์หลัก GovNav/ อัตโนมัติ
if [ "$(basename "$SCRIPT_DIR")" = "core" ]; then
    cd ..
fi

echo "======================================================================"
echo "  กำลังเริ่มต้นระบบ GovNav (Government Navigator) บน Raspberry Pi 4"
echo "======================================================================"

# 1. ค้นหาและเปิดใช้งาน Virtual Environment (venv) อัตโนมัติจากทุกตำแหน่งที่เป็นไปได้
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
        source "$VENV_PATH"
        VENV_FOUND=1
        break
    fi
done

# 2. ตรวจสอบว่าติดตั้ง vachanatts หรือยัง ถ้ายังจะติดตั้งให้อัตโนมัติ (รองรับทั้งใน venv และนอก venv)
if ! python3 -c "import vachanatts" >/dev/null 2>&1; then
    echo "[*] กำลังติดตั้งไลบรารี VachanaTTS (Offline ONNX) สำหรับ Raspberry Pi 4..."
    if [ "$VENV_FOUND" -eq 1 ]; then
        pip install -r requirements.txt
    else
        pip3 install --break-system-packages -r requirements.txt
    fi
fi

# 3. ตรวจสอบไฟล์โมเดลเสียง .onnx ในโฟลเดอร์ voices/
if [ ! -f "voices/th_f_1.onnx" ]; then
    echo "[*] กำลังดาวน์โหลดโมเดลเสียงภาษาไทยเก็บไว้ใน voices/ สำหรับโหมด Offline 100%..."
    python3 download_voices_offline.py
fi

# 4. แสดง IP Address ของบอร์ด Raspberry Pi 4
RPI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "----------------------------------------------------------------------"
echo "[OK] เปิดหน้าจอ GovNav Kiosk Dashboard พร้อมใช้งาน!"
echo "   - เปิดบนจอที่ต่อกับ RPi4 : http://localhost:8501"
if [ -n "$RPI_IP" ]; then
    echo "   - เปิดจากคอม/มือถือในวงแลน : http://${RPI_IP}:8501"
fi
echo "----------------------------------------------------------------------"

python3 -m streamlit run app_dashboard.py --server.address 0.0.0.0 --server.port 8501
