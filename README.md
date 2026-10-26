# 🏛️ GovNav (Government Navigator)
**ระบบผู้ช่วยแนะนำขั้นตอนราชการและนำทางในอาคารอัจฉริยะสำหรับคนนอกพื้นที่ด้วย Edge AI, VachanaTTS (Offline 100%) และ Multi-Sensor IoT บน Raspberry Pi 4**

---

## 📁 โครงสร้างโฟลเดอร์บน Raspberry Pi 4

```text
/home/fablab-rpi-13/qwen_rpi4/
├── models/                        # โฟลเดอร์เก็บไฟล์โมเดล Qwen (.gguf)
├── venv/                          # Virtual Environment ของ Raspberry Pi 4
└── GovNav/                        # โฟลเดอร์โปรเจกต์หลัก (ก๊อปปี้ไปวางทั้งโฟลเดอร์ได้เลย)
    ├── setup_and_run_rpi.sh       # สคริปต์รันคำสั่งเดียวบน RPi4 (เช็ก venv + โหลดเสียง + เปิด Dashboard)
    ├── download_voices_offline.py # สคริปต์โหลดโมเดลเสียง .onnx ทั้ง 4 เสียงเก็บไว้ใช้ Offline 100%
    ├── requirements.txt           # รายการไลบรารีทั้งหมดของระบบ (รวม vachanatts & onnxruntime)
    ├── config.py                  # ตั้งค่าพอร์ต GPIO, โมเดล Qwen (.gguf) และเสียง VachanaTTS
    ├── main_cli.py                # โปรแกรมหลักรันผ่าน Terminal (ASCII Map + รูป .png + เสียงไทย)
    ├── app_dashboard.py           # หน้าจอ Interactive Web Kiosk & Dashboard ฉบับสมบูรณ์ (Streamlit)
    ├── evaluate_govnav.py         # สคริปต์วัดผลความแม่นยำ 30 สถานการณ์ (6.1) และเวลาตอบสนอง (6.2)
    ├── voices/                    # โฟลเดอร์เก็บไฟล์โมเดลเสียง VachanaTTS (.onnx) แบบ Offline
    ├── data/
    │   ├── system_prompt.txt      # ข้อมูล System Prompt สำหรับสอนโมเดล Qwen
    │   ├── departments.json       # ข้อมูลห้องราชการ เอกสารที่ต้องเตรียม และคีย์เวิร์ด
    │   ├── eval_scenarios_30.json # ชุดคำถามจำลองภาษาชาวบ้าน 30 สถานการณ์สำหรับวัดผล
    │   └── govnav_logs.db         # ฐานข้อมูล SQLite บันทึกประวัติและสถิติผู้มาติดต่ออัตโนมัติ
    ├── assets/
    │   ├── maps/                  # ไฟล์รูปแผนผังอาคาร (.png) ภาษาไทยของแต่ละห้องราชการ
    │   ├── audio_out/             # ไฟล์เสียงพูดล่าสุด (.wav) สำหรับสั่งเล่นออกลำโพง aplay
    │   └── audio_cache/           # คลังแคชไฟล์เสียงพูด (.wav) โหลดซ้ำความเร็วสูงใน 0.01 วินาที
    └── core/
        ├── llm_navigator.py       # โมดูลประมวลผล Qwen (.gguf) ผ่าน llama_cpp + Smart RAG
        ├── map_renderer.py        # โมดูลวาดแผนที่ตัวอักษรขีด (ASCII) และสร้างรูปแผนผัง (.png)
        ├── iot_hardware.py        # โมดูลควบคุมเซนเซอร์ Ultrasonic, DHT22, ไฟ LED บอกทาง, Buzzer
        ├── tts_speaker.py         # โมดูลสังเคราะห์เสียงภาษาไทย VachanaTTS (VITS + Piper ONNX)
        └── db_logger.py           # โมดูลบันทึกข้อมูล วิเคราะห์สถิติ และส่งออก CSV จาก SQLite
```

---

## 🍓 วิธีติดตั้งและรันใช้งานบน Raspberry Pi 4 (ผ่าน SSH หรือ Terminal)

หลังจากก๊อปปี้โฟลเดอร์ `GovNav` ไปวางไว้ที่ `/home/fablab-rpi-13/qwen_rpi4/GovNav` บนบอร์ด Raspberry Pi 4 แล้ว เลือกรันได้ 2 วิธีครับ:

### วิธีลัด (รันคำสั่งเดียวจบ):
```bash
cd /home/fablab-rpi-13/qwen_rpi4/GovNav
bash setup_and_run_rpi.sh
```
*(สคริปต์จะเปิด `../venv` ให้อัตโนมัติ ติดตั้ง `vachanatts` หากยังไม่มี ดาวน์โหลดโมเดลเสียงเก็บลง `voices/` เพื่อใช้ Offline แล้วรันหน้าจอ Dashboard พร้อมบอก IP ของบอร์ดให้ทันที)*

---

### วิธีรันทีละขั้นตอนด้วยตนเอง:

#### 1. เปิดใช้งาน `venv` และติดตั้งไลบรารี
```bash
cd /home/fablab-rpi-13/qwen_rpi4
source venv/bin/activate
cd GovNav
pip install -r requirements.txt
```

#### 2. ดาวน์โหลดโมเดลเสียงเก็บไว้ใช้ Offline 100% (ทำครั้งเดียวตอนต่อเน็ต)
```bash
python download_voices_offline.py
```
*(หลังจากขั้นตอนนี้ ไฟล์ `th_f_1.onnx`, `th_f_2.onnx`, `th_m_1.onnx`, `th_m_2.onnx` จะอยู่ใน `GovNav/voices/` ถอดเน็ตออกแล้วใช้งานแบบ Offline 100% ได้ตลอดไป)*

#### 3. สั่งรันโปรแกรม (เลือกได้ทั้ง 3 โหมด)

* **โหมดที่ 1 — หน้าจอ Interactive Web Kiosk & Dashboard ฉบับสมบูรณ์:**
  ```bash
  streamlit run app_dashboard.py --server.address 0.0.0.0 --server.port 8501
  ```
  *(เปิดดูผ่านจอของ RPi4 ได้ที่ `http://localhost:8501` หรือเปิดจากโน้ตบุ๊ก/แท็บเล็ตในวง Wi-Fi เดียวกันได้ที่ `http://<IP-ของ-RPi4>:8501`)*

* **โหมดที่ 2 — ถาม-ตอบสดผ่าน Terminal พร้อมเสียงพูดไทยออกลำโพง (`aplay`):**
  ```bash
  python main_cli.py --open-image --tts --voice th_f_1
  ```

* **โหมดที่ 3 — สาธิตอัตโนมัติ 3 คำถาม (สำหรับทดสอบระบบและอัดคลิปส่งอาจารย์):**
  ```bash
  python main_cli.py --demo --open-image --tts
  ```

* **โหมดที่ 4 — วัดผลการทดลองครบ 30 สถานการณ์สำหรับใส่เล่มรายงาน (หัวข้อ 6.1 & 6.2):**
  ```bash
  python evaluate_govnav.py
  ```
  *(สรุปตารางความแม่นยำและเวลาประมวลผลรายขั้นตอนออกทาง Terminal พร้อมบันทึกไฟล์ `data/eval_report.json` แสดงบนหน้าเว็บแท็บ `🧪 ผลการทดลอง 6.1 & 6.2` และไฟล์ Excel `data/eval_report_details.csv` โดยไม่ลบแคชเสียงเดิม)*
