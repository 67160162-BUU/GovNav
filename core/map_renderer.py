#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - Map Renderer Module (ฉบับภาษาไทยสมบูรณ์)
รองรับการแสดงแผนที่นำทาง 2 รูปแบบควบคู่กัน:
1. ASCII / Unicode Box-Drawing Map (วาดแผนที่ด้วยตัวอักษรขีดและลูกศรนำทางใน Terminal/ใบนำทาง)
2. Image Map Lookup & Dynamic Route Overlay (สร้างและเปิดไฟล์รูปภาพแผนที่ .png ภาษาไทยของห้องเป้าหมาย)
"""

import os
import sys
import json
import subprocess
from typing import Optional

from config import BASE_DIR, MAPS_DIR, DEPARTMENTS_FILE

plt = None
patches = None


def _ensure_matplotlib():
    """โหลด Matplotlib แบบ Lazy เฉพาะกรณีที่ยังไม่มีไฟล์รูป .png เพื่อไม่ให้เปลือง RAM หรือเกิด Segfault ตอนเปิดเว็บ"""
    global plt, patches
    if plt is not None and patches is not None:
        return
    if sys.platform == "darwin":
        _mpl_cache = os.path.join(BASE_DIR, ".mplcache")
        os.makedirs(_mpl_cache, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", _mpl_cache)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt
    import matplotlib.patches as _patches

    _plt.rcParams["font.family"] = "sans-serif"
    _plt.rcParams["font.sans-serif"] = [
        "Tahoma", "Thonburi", "Sukhumvit Set", "Ayuthaya",
        "Loma", "Waree", "Garuda", "Norasi", "Noto Sans Thai",
        "FreeSans", "DejaVu Sans"
    ]
    _plt.rcParams["axes.unicode_minus"] = False
    plt = _plt
    patches = _patches


class MapRenderer:
    """คลาสจัดการการวาดแผนที่ตัวอักษรขีด (ASCII Map) และการค้นหา/เปิดไฟล์รูปแผนที่ภาษาไทย (.png)"""

    def __init__(self):
        os.makedirs(MAPS_DIR, exist_ok=True)
        with open(DEPARTMENTS_FILE, "r", encoding="utf-8") as f:
            self.departments = {
                d["room_id"]: d for d in json.load(f)["departments"]
            }

    def render_ascii_map(self, target_room_id: str) -> str:
        """
        สร้างแผนที่อาคารด้วยเส้นตัวอักษรขีด (Box-Drawing Characters)
        พร้อมไฮไลต์ดาว ★ ที่ห้องเป้าหมาย และวาดลูกศรเส้นทางเดินจากตู้ GovNav
        """
        dept = self.departments.get(target_room_id)
        if not dept:
            return "[ไม่พบแผนผังของห้องที่ระบุ]"

        m201 = "★ [เป้าหมายของคุณ!] ★" if target_room_id == "ROOM_201" else "   (โอนที่ดิน/ช่างโยธา)  "
        m202 = "★ [เป้าหมายของคุณ!] ★" if target_room_id == "ROOM_202" else "  (ร้องทุกข์/ปรึกษากฎหมาย) "
        m103 = "★ [เป้าหมายของคุณ!] ★" if target_room_id == "ROOM_103" else "   (ชำระภาษีที่ดิน/ป้าย)   "
        m101 = "★ [เป้าหมายของคุณ!] ★" if target_room_id == "ROOM_101" else " (บัตรประชาชน/ทะเบียนบ้าน)"
        m102 = "★ [เป้าหมายของคุณ!] ★" if target_room_id == "ROOM_102" else " (เบี้ยผู้สูงอายุ/บัตรคนจน) "

        arr_2l = "◄══════╬" if target_room_id == "ROOM_201" else "       ║"
        arr_2r = "╬══════►" if target_room_id == "ROOM_202" else "║       "
        arr_up = "║ ▲ขึ้นชั้น2 ║" if target_room_id in ("ROOM_201", "ROOM_202") else "║ บันได/ลิฟต์║"

        arr_1c = "▲ เดินตรงไป" if target_room_id in ("ROOM_103", "ROOM_201", "ROOM_202") else "│         "
        arr_1l = "◄══════╬" if target_room_id == "ROOM_101" else "       │"
        arr_1r = "╬══════►" if target_room_id == "ROOM_102" else "│       "

        ascii_map = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                 🗺️  แผนผังนำทางศูนย์ราชการ GovNav (ASCII Map)                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  [ ชั้น 2 : อาคารบริการประชาชน ]                                              ║
║  ┌──────────────────────────┐                  ┌──────────────────────────┐  ║
║  │ ROOM_201: สำนักงานที่ดิน   │   {arr_2l}{arr_2r}   │ ROOM_202: ศูนย์ดำรงธรรม   │  ║
║  │ {m201} │    {arr_up}    │ {m202} │  ║
║  └──────────────────────────┘        ║║        └──────────────────────────┘  ║
╟──────────────────────────────────────╫╫──────────────────────────────────────╢
║  [ ชั้น 1 : โถงบริการหลัก ]            ║║                                      ║
║                        ┌─────────────╨╨─────────────┐                        ║
║                        │ ROOM_103: กองคลังและภาษี   │                        ║
║                        │ {m103}  │                        ║
║                        └─────────────┬──────────────┘                        ║
║                                      {arr_1c}                             ║
║  ┌──────────────────────────┐        │         ┌──────────────────────────┐  ║
║  │ ROOM_101: ทะเบียนราษฎร   │  {arr_1l}{arr_1r} │ ROOM_102: พัฒนาสังคม     │  ║
║  │ {m101} │        ▲         │ {m102} │  ║
║  └──────────────────────────┘        ║         └──────────────────────────┘  ║
║                            ┏━━━━━━━━━┻━━━━━━━━━┓                             ║
║                            ┃ ● จุดที่คุณยืนอยู่ตอนนี้ ┃                             ║
║                            ┃  [ ตู้คีออส GovNav ] ┃                             ║
║                            ┗━━━━━━━━━━━━━━━━━━━┛                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
  ➔ ห้องเป้าหมาย : {dept['room_id']} — {dept['name_th']} (ชั้น {dept['floor']} {dept['wing']})
  ➔ เส้นทางเดิน   : {dept['walk_steps']}
"""
        return ascii_map

    def get_map_image_path(self, target_room_id: str) -> str:
        """
        ค้นหาพาธไฟล์รูปภาพแผนที่ (.png) ของห้องเป้าหมาย
        หากยังไม่มีไฟล์รูปในโฟลเดอร์ assets/maps/ ระบบจะวาดและบันทึกให้อัตโนมัติ
        """
        dept = self.departments.get(target_room_id)
        if not dept:
            raise ValueError(f"Unknown room_id: {target_room_id}")

        img_filename = dept.get("map_image", f"map_{target_room_id}.png")
        img_path = os.path.join(MAPS_DIR, img_filename)

        if not os.path.exists(img_path):
            self.generate_floorplan_image(target_room_id, img_path)

        return img_path

    def generate_all_map_images(self, force: bool = False):
        """สร้างไฟล์รูปแผนที่ .png ภาษาไทยของทุกห้องเก็บไว้ใน assets/maps/"""
        generated = []
        for room_id, dept in self.departments.items():
            img_path = os.path.join(MAPS_DIR, dept["map_image"])
            if force or not os.path.exists(img_path):
                self.generate_floorplan_image(room_id, img_path)
            generated.append(img_path)
        return generated

    def _draw_room(self, ax, x, y, w, h, text, fontsize=10.5, bold=False,
                   is_target=False, facecolor="#ffffff", edgecolor="#000000", lw=1.3):
        """วาดช่องห้องสี่เหลี่ยมแบบผังอาคารเส้นสีดำพื้นขาว (ไฮไลต์สีเขียวอ่อนเฉพาะห้องเป้าหมาย)"""
        if is_target:
            facecolor = "#dcfce7"
            edgecolor = "#15803d"
            lw = 2.8
        rect = patches.Rectangle((x, y), w, h, linewidth=lw, edgecolor=edgecolor, facecolor=facecolor, zorder=2)
        ax.add_patch(rect)
        if text:
            weight = "bold" if (bold or is_target) else "normal"
            color = "#065f46" if is_target else "#000000"
            ax.text(x + w / 2, y + h / 2, text, fontsize=fontsize, fontweight=weight,
                    color=color, ha="center", va="center", zorder=4)

    def _draw_restroom(self, ax, x, y, w, h):
        """วาดห้องน้ำ ช | ญ ตามสไตล์ผังอาคารมาตรฐาน"""
        rect = patches.Rectangle((x, y), w, h, linewidth=1.3, edgecolor="#000000", facecolor="#ffffff", zorder=2)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h * 0.65, "ห้องน้ำ", fontsize=10, color="#000000", ha="center", va="center", zorder=4)
        # เส้นแบ่ง ช | ญ ด้านล่าง
        ax.plot([x + w / 2, x + w / 2], [y, y + h * 0.38], color="#000000", linewidth=1.1, zorder=3)
        ax.text(x + w * 0.25, y + h * 0.2, "ช", fontsize=9.5, color="#000000", ha="center", va="center", zorder=4)
        ax.text(x + w * 0.75, y + h * 0.2, "ญ", fontsize=9.5, color="#000000", ha="center", va="center", zorder=4)

    def _draw_stairs(self, ax, x, y, w, h):
        """วาดสัญลักษณ์บันไดพร้อมขั้นบันไดและลูกศรขึ้น-ลง แบบผังอาคาร"""
        rect = patches.Rectangle((x, y), w, h, linewidth=1.3, edgecolor="#000000", facecolor="#ffffff", zorder=2)
        ax.add_patch(rect)
        # เส้นแบ่งครึ่งซ้าย-ขวา (ขาขึ้น / ขาลง)
        ax.plot([x + w / 2, x + w / 2], [y, y + h], color="#000000", linewidth=1.1, zorder=3)
        # เส้นขั้นบันไดแนวนอน
        steps = 6
        for i in range(1, steps):
            sy = y + (h / steps) * i
            ax.plot([x, x + w], [sy, sy], color="#000000", linewidth=0.9, zorder=3)
        # ลูกศรขึ้น (ฝั่งซ้าย) และ ลูกศรลง (ฝั่งขวา)
        arr_props = dict(arrowstyle="-|>,head_width=0.35,head_length=0.45", lw=1.3, color="#000000")
        ax.annotate("", xy=(x + w * 0.25, y + h * 0.85), xytext=(x + w * 0.25, y + h * 0.15),
                    arrowprops=arr_props, zorder=4)
        ax.annotate("", xy=(x + w * 0.75, y + h * 0.15), xytext=(x + w * 0.75, y + h * 0.85),
                    arrowprops=arr_props, zorder=4)

    def generate_floorplan_image(self, target_room_id: str, save_path: str):
        """วาดไฟล์รูปแผนผังอาคาร (.png) พื้นขาวเส้นดำสไตล์ผังอาคารมาตรฐาน มองง่าย สบายตา"""
        _ensure_matplotlib()
        dept = self.departments[target_room_id]
        room_num = target_room_id.replace("ROOM_", "")

        fig, ax = plt.subplots(figsize=(11, 12), dpi=200)
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#ffffff")

        # ==================== หัวข้อแผนผังด้านบน ====================
        ax.text(500, 968, f"แผนผังอาคารศูนย์ราชการ (GovNav) — เส้นทางไปห้อง {room_num}",
                fontsize=15, fontweight="bold", color="#000000", ha="center", va="center")
        ax.text(500, 936, f"จุดหมาย: {dept['name_th']} ({dept['wing']})",
                fontsize=11.5, fontweight="bold", color="#15803d", ha="center", va="center")
        ax.text(500, 908, f"วิธีเดิน: {dept['walk_steps']}",
                fontsize=10.5, color="#1e293b", ha="center", va="center")

        # =========================================================================
        # บล็อกที่ 1 (ด้านบน) : ผังอาคาร ชั้น ๑ (โถงบริการประชาชนหลัก) [x=40..960, y=500..865]
        # =========================================================================
        f1_x, f1_y, f1_w, f1_h = 40, 500, 920, 365
        ax.add_patch(patches.Rectangle((f1_x, f1_y), f1_w, f1_h,
                                       linewidth=1.8, edgecolor="#000000", facecolor="#ffffff", zorder=1))
        # เส้นระเบียงทางเดินด้านบนสุด (2 เส้นขนานตามแบบผังอาคาร)
        ax.add_patch(patches.Rectangle((f1_x, f1_y + f1_h), f1_w, 16,
                                       linewidth=1.3, edgecolor="#000000", facecolor="#ffffff", zorder=2))
        ax.plot([f1_x, f1_x + f1_w], [f1_y + f1_h + 8, f1_y + f1_h + 8], color="#000000", linewidth=0.9, zorder=3)

        # ซุ้มโค้งหน้าห้อง 103 (ชั้น 1)
        arc1 = patches.Arc((500, 745), 180, 38, angle=0, theta1=180, theta2=360,
                           linewidth=1.2, edgecolor="#000000", zorder=3)
        ax.add_patch(arc1)
        ax.text(500, 712, "ช่องบริการรับชำระค่าธรรมเนียม", fontsize=9.5, color="#334155", ha="center", va="center")

        # ฝั่งซ้าย ชั้น 1 (x=40..280, w=240)
        self._draw_room(ax, 40, 745, 240, 120, "จุดประชาสัมพันธ์\nและรับบัตรคิว", fontsize=10.5)
        self._draw_room(ax, 40, 500, 240, 245,
                        "ห้อง 101\nฝ่ายทะเบียนราษฎร\nและบัตรประชาชน\n(ทำบัตร ปชช. / ทะเบียนบ้าน)"
                        + ("\n\n>>> ห้องเป้าหมาย <<<" if target_room_id == "ROOM_101" else ""),
                        fontsize=10.5, is_target=(target_room_id == "ROOM_101"))

        # ด้านบนกลาง ชั้น 1 (x=280..720, w=440)
        self._draw_room(ax, 280, 745, 440, 120,
                        "ห้อง 103 : กองคลังและงานจัดเก็บรายได้\n(ชำระภาษีที่ดิน / ภาษีป้าย / ค่าธรรมเนียม)"
                        + ("\n>>> ห้องเป้าหมาย <<<" if target_room_id == "ROOM_103" else ""),
                        fontsize=10.5, is_target=(target_room_id == "ROOM_103"))

        # ฝั่งขวา ชั้น 1 (x=720..960, w=240): ห้องน้ำ, ห้อง 102, ลิฟต์ และบันได
        self._draw_restroom(ax, 720, 775, 240, 90)
        self._draw_room(ax, 720, 595, 240, 180,
                        "ห้อง 102\nฝ่ายพัฒนาสังคมและสวัสดิการ\n(เบี้ยผู้สูงอายุ / บัตรคนจน / ผู้พิการ)"
                        + ("\n\n>>> ห้องเป้าหมาย <<<" if target_room_id == "ROOM_102" else ""),
                        fontsize=10, is_target=(target_room_id == "ROOM_102"))
        self._draw_room(ax, 720, 500, 110, 95, "ลิฟต์\nโดยสาร", fontsize=10,
                        facecolor=("#fef9c3" if target_room_id in ("ROOM_201", "ROOM_202") else "#ffffff"))
        self._draw_stairs(ax, 830, 500, 130, 95)

        # โถงกลางชั้น 1
        ax.text(500, 660, "ชั้น ๑", fontsize=14, fontweight="bold", color="#000000", ha="center", va="center")
        ax.text(500, 628, "โถงบริการประชาชนหลัก", fontsize=11.5, color="#000000", ha="center", va="center")

        # จุดที่ยืนอยู่ (ตู้คีออส GovNav) บริเวณทางเข้าชั้น 1
        kiosk_rect = patches.Rectangle((390, 500), 220, 56, linewidth=2.0,
                                       edgecolor="#0284c7", facecolor="#e0f2fe", zorder=4)
        ax.add_patch(kiosk_rect)
        ax.text(500, 528, "● จุดที่คุณยืนอยู่ตอนนี้\nตู้คีออส GovNav (ทางเข้าหลัก)",
                fontsize=9.5, fontweight="bold", color="#0369a1", ha="center", va="center", zorder=5)

        # =========================================================================
        # บล็อกที่ 2 (ด้านล่าง) : ผังอาคาร ชั้น ๒ (อาคารบริการประชาชน) [x=40..960, y=75..440]
        # =========================================================================
        f2_x, f2_y, f2_w, f2_h = 40, 75, 920, 365
        ax.add_patch(patches.Rectangle((f2_x, f2_y), f2_w, f2_h,
                                       linewidth=1.8, edgecolor="#000000", facecolor="#ffffff", zorder=1))
        # กรอบป้ายระเบียงชั้น 2 ด้านบน
        ax.add_patch(patches.Rectangle((390, f2_y + f2_h - 8), 220, 22,
                                       linewidth=1.2, edgecolor="#000000", facecolor="#ffffff", zorder=3))
        arc2 = patches.Arc((500, f2_y + f2_h - 8), 180, 36, angle=0, theta1=180, theta2=360,
                           linewidth=1.2, edgecolor="#000000", zorder=3)
        ax.add_patch(arc2)
        ax.text(500, f2_y + f2_h - 40, "โถงระเบียงชั้น ๒", fontsize=9.5, color="#334155", ha="center", va="center")

        # ฝั่งซ้าย ชั้น 2 (x=40..280, w=240) : ห้องสารบบ + ห้อง 201 (ที่ดินและช่างโยธา)
        self._draw_room(ax, 40, 345, 240, 95, "ห้องสารบบที่ดิน\nและตรวจแบบแปลน", fontsize=10)
        self._draw_room(ax, 40, 75, 240, 270,
                        "ห้อง 201\nสำนักงานที่ดิน\nและงานช่างโยธา\n(โอนที่ดิน / ขออนุญาตก่อสร้าง)"
                        + ("\n\n>>> ห้องเป้าหมาย <<<" if target_room_id == "ROOM_201" else ""),
                        fontsize=10.5, is_target=(target_room_id == "ROOM_201"))

        # ด้านล่างกลาง ชั้น 2 (x=280..720, w=440) : จุดพักคอย + โถงหน้าลิฟต์
        self._draw_room(ax, 280, 75, 300, 95, "จุดพักคอยผู้มาติดต่อราชการชั้น ๒", fontsize=10)
        self._draw_room(ax, 580, 75, 140, 95, "โถงหน้าลิฟต์\nชั้น ๒", fontsize=10)

        # ฝั่งขวา ชั้น 2 (x=720..960, w=240) : ห้องน้ำ, ห้อง 202 (ศูนย์ดำรงธรรม), ลิฟต์ และบันได
        self._draw_restroom(ax, 720, 345, 240, 95)
        self._draw_room(ax, 720, 170, 240, 175,
                        "ห้อง 202\nศูนย์ดำรงธรรมและงานนิติการ\n(ร้องเรียน / ไกล่เกลี่ย / กฎหมาย)"
                        + ("\n\n>>> ห้องเป้าหมาย <<<" if target_room_id == "ROOM_202" else ""),
                        fontsize=10, is_target=(target_room_id == "ROOM_202"))
        self._draw_room(ax, 720, 75, 110, 95, "ลิฟต์\nโดยสาร", fontsize=10,
                        facecolor=("#fef9c3" if target_room_id in ("ROOM_201", "ROOM_202") else "#ffffff"))
        self._draw_stairs(ax, 830, 75, 130, 95)

        # ข้อความกลางโถงชั้น 2
        ax.text(500, 285, "ชั้น ๒", fontsize=14, fontweight="bold", color="#000000", ha="center", va="center")
        ax.text(500, 253, "อาคารบริการประชาชน", fontsize=11.5, color="#000000", ha="center", va="center")

        # =========================================================================
        # วาดเส้นลูกศรนำทางสีแดงชัดเจน (จากตู้ GovNav ไปยังห้องเป้าหมาย)
        # =========================================================================
        route_line = dict(color="#dc2626", linewidth=3.0, linestyle="--", zorder=6)
        route_arrow = dict(arrowstyle="-|>,head_width=0.5,head_length=0.65", lw=3.0, color="#dc2626")

        if target_room_id == "ROOM_101":
            ax.plot([500, 500], [556, 600], **route_line)
            ax.annotate("", xy=(282, 600), xytext=(500, 600), arrowprops=route_arrow, zorder=6)
        elif target_room_id == "ROOM_102":
            ax.plot([500, 500], [556, 685], **route_line)
            ax.annotate("", xy=(718, 685), xytext=(500, 685), arrowprops=route_arrow, zorder=6)
        elif target_room_id == "ROOM_103":
            ax.annotate("", xy=(500, 743), xytext=(500, 556), arrowprops=route_arrow, zorder=6)
        elif target_room_id in ("ROOM_201", "ROOM_202"):
            # เส้นทางในชั้น 1: เดินจากตู้ GovNav ไปที่ลิฟต์/บันไดชั้น 1
            ax.plot([500, 500], [556, 575], **route_line)
            ax.annotate("", xy=(718, 575), xytext=(500, 575), arrowprops=route_arrow, zorder=6)
            ax.text(605, 590, "๑. เดินไปขึ้นลิฟต์/บันได", fontsize=9.5, fontweight="bold", color="#dc2626", ha="center", zorder=6)

            # เส้นทางในชั้น 2: ออกจากลิฟต์/บันไดชั้น 2 ไปยังห้องเป้าหมาย
            if target_room_id == "ROOM_201":
                ax.plot([650, 650, 480], [170, 205, 205], **route_line)
                ax.annotate("", xy=(282, 205), xytext=(480, 205), arrowprops=route_arrow, zorder=6)
                ax.text(490, 185, "๒. ออกจากลิฟต์เดินไปทางซ้าย เข้าห้อง 201", fontsize=9.5, fontweight="bold", color="#dc2626", ha="center", zorder=6)
            else:
                ax.plot([650, 650], [170, 225], **route_line)
                ax.annotate("", xy=(718, 225), xytext=(650, 225), arrowprops=route_arrow, zorder=6)
                ax.text(535, 210, "๒. ออกจากลิฟต์เลี้ยวขวาเข้าห้อง 202", fontsize=9.5, fontweight="bold", color="#dc2626", ha="center", zorder=6)

        # แถบสรุปด้านล่างสุด (จำกัดความกว้างให้อยู่ในกรอบภาพเสมอ)
        docs_short = ", ".join(dept["required_docs"][:2])
        ax.text(500, 32, f"คิวรอปัจจุบัน: {dept['queue_count']} คิว (~{dept['estimated_wait_min']} นาที)  |  เอกสารหลัก: {docs_short}",
                fontsize=10, fontweight="bold", color="#0f172a", ha="center", va="center")

        ax.set_xlim(0, 1000)
        ax.set_ylim(0, 1000)
        ax.axis("off")
        plt.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)
        plt.savefig(save_path, facecolor="#ffffff", edgecolor="none")
        plt.close()

    def open_map_image(self, target_room_id: str) -> Optional[str]:
        """
        ค้นหาไฟล์รูปแผนที่ของห้องเป้าหมาย และสั่งเปิดรูปภาพขึ้นบนหน้าจอทันที
        - บน Raspberry Pi OS (Linux Desktop): ใช้ xdg-open หรือ feh
        - บน macOS: ใช้คำสั่ง open
        """
        img_path = self.get_map_image_path(target_room_id)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", img_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform.startswith("linux"):
                if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                    subprocess.Popen(["xdg-open", img_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return img_path
        except Exception as e:
            print(f"[MapRenderer] ไม่สามารถเปิดโปรแกรมดูรูปภาพอัตโนมัติได้: {e}")
            return img_path
