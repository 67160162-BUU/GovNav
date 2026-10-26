#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - SQLite Database Logger & Analytics Module
บันทึกประวัติการสอบถามเส้นทางของผู้มาติดต่อราชการ ค่าเซนเซอร์ และสถิติความหนาแน่นแต่ละแผนก
"""

import os
import csv
import io
import sqlite3
from datetime import datetime
from typing import Dict, Any, List

from config import SQLITE_DB_PATH


class GovNavDBLogger:
    """คลาสจัดการฐานข้อมูล SQLite สำหรับบันทึกสถิติการใช้งานตู้ GovNav"""

    def __init__(self, db_path: str = SQLITE_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS navigation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    visitor_query TEXT NOT NULL,
                    matched_room_id TEXT NOT NULL,
                    department_name TEXT NOT NULL,
                    floor INTEGER,
                    direction_code TEXT,
                    visitor_distance_cm REAL,
                    ambient_temp_c REAL,
                    latency_ms REAL
                )
            """)
            conn.commit()

    def log_interaction(self, nav_result: Dict[str, Any], sensor_data: Dict[str, Any]):
        """บันทึกข้อมูลการถามทางและสถานะเซนเซอร์ลงตาราง SQLite"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO navigation_logs (
                    timestamp, visitor_query, matched_room_id, department_name,
                    floor, direction_code, visitor_distance_cm, ambient_temp_c, latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                nav_result["query"],
                nav_result["room_id"],
                nav_result["department_name"],
                nav_result["floor"],
                nav_result["direction_code"],
                sensor_data.get("visitor_distance_cm", 0.0),
                sensor_data.get("ambient_temp_c", 25.0),
                nav_result.get("latency_ms", 0.0)
            ))
            conn.commit()

    def get_recent_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """ดึงประวัติการถามทางล่าสุด"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM navigation_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_room_statistics(self) -> List[Dict[str, Any]]:
        """สรุปจำนวนผู้มาติดต่อแยกตามห้องราชการ"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT matched_room_id, department_name, COUNT(*) as visit_count,
                       ROUND(AVG(latency_ms), 2) as avg_latency_ms
                FROM navigation_logs
                GROUP BY matched_room_id, department_name
                ORDER BY visit_count DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_summary_metrics(self) -> Dict[str, Any]:
        """ดึงค่าสถิติภาพรวมทั้งหมดสำหรับแสดงบน Dashboard"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT COUNT(*) as total_visits,
                       ROUND(AVG(latency_ms), 2) as avg_latency_ms,
                       ROUND(AVG(visitor_distance_cm), 1) as avg_distance_cm
                FROM navigation_logs
            """).fetchone()
            top_row = conn.execute("""
                SELECT matched_room_id, department_name, COUNT(*) as cnt
                FROM navigation_logs
                GROUP BY matched_room_id
                ORDER BY cnt DESC
                LIMIT 1
            """).fetchone()

            return {
                "total_visits": row["total_visits"] if row else 0,
                "avg_latency_ms": row["avg_latency_ms"] if (row and row["avg_latency_ms"]) else 0.0,
                "avg_distance_cm": row["avg_distance_cm"] if (row and row["avg_distance_cm"]) else 0.0,
                "top_room_id": top_row["matched_room_id"] if top_row else "-",
                "top_department": top_row["department_name"] if top_row else "ยังไม่มีข้อมูล",
            }

    def export_logs_csv(self) -> str:
        """ส่งออกข้อมูลประวัติทั้งหมดในรูปแบบ CSV (UTF-8 with BOM สำหรับเปิดใน Excel ภาษาไทยไม่เพี้ยน)"""
        logs = self.get_recent_logs(limit=1000)
        output = io.StringIO()
        output.write("\ufeff")
        if not logs:
            return output.getvalue()
        writer = csv.DictWriter(output, fieldnames=list(logs[0].keys()))
        writer.writeheader()
        writer.writerows(logs)
        return output.getvalue()

    def clear_logs(self):
        """ล้างประวัติการเข้าใช้งานทั้งหมด"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM navigation_logs")
            conn.commit()
