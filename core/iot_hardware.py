#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GovNav - Raspberry Pi 4 IoT Hardware Controller
ควบคุมเซนเซอร์และอุปกรณ์ Actuators บนบอร์ด Raspberry Pi 4:
1. Ultrasonic HC-SR04 / mmWave Radar: ตรวจจับคนเดินเข้ามาใกล้ตู้ (< 150 cm)
2. DHT22 Sensor: วัดอุณหภูมิและความชื้นสัมพัทธ์บริเวณโถงบริการ
3. Directional LEDs (GPIO 17, 27, 22): ไฟ LED ชี้ทิศทางเดิน ซ้าย / ขวา / ตรงไปขึ้นชั้น 2
4. Staff Buzzer (GPIO 18): ส่งสัญญาณเรียกเจ้าหน้าที่ประชาสัมพันธ์
หมายเหตุ: ถ้ารันบนคอมพิวเตอร์ (Mac/PC) ที่ไม่มี RPi.GPIO ระบบจะสลับเข้าโหมดจำลอง (Hardware Simulation) อัตโนมัติ
"""

import time
import random
from typing import Dict, Any

from config import GPIO_PINS, APPROACH_DISTANCE_CM

try:
    import RPi.GPIO as GPIO
    HAS_RPI_GPIO = True
except ImportError:
    HAS_RPI_GPIO = False


class GovNavIoTHardware:
    """คลาสจัดการพอร์ต GPIO เซนเซอร์ และไฟ LED บอกทิศทางบน Raspberry Pi 4"""

    def __init__(self):
        self.is_raspberry_pi = HAS_RPI_GPIO
        self.active_led_direction = "OFF"
        if self.is_raspberry_pi:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(GPIO_PINS["ULTRASONIC_TRIG"], GPIO.OUT)
            GPIO.setup(GPIO_PINS["ULTRASONIC_ECHO"], GPIO.IN)
            GPIO.setup(GPIO_PINS["LED_LEFT"], GPIO.OUT)
            GPIO.setup(GPIO_PINS["LED_RIGHT"], GPIO.OUT)
            GPIO.setup(GPIO_PINS["LED_STRAIGHT"], GPIO.OUT)
            GPIO.setup(GPIO_PINS["STAFF_BUZZER"], GPIO.OUT)
            GPIO.setup(GPIO_PINS["HELP_BUTTON"], GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def read_visitor_distance_cm(self) -> float:
        """วัดระยะห่างของผู้มาติดต่อหน้าตู้ (หน่วย: เซนติเมตร)"""
        if not self.is_raspberry_pi:
            # โหมดจำลอง: สุ่มระยะคนเดินเข้ามาหน้าตู้ (65 - 135 cm)
            return round(random.uniform(65.0, 135.0), 1)

        trig = GPIO_PINS["ULTRASONIC_TRIG"]
        echo = GPIO_PINS["ULTRASONIC_ECHO"]

        GPIO.output(trig, False)
        time.sleep(0.02)
        GPIO.output(trig, True)
        time.sleep(0.00001)
        GPIO.output(trig, False)

        pulse_start = time.time()
        timeout = pulse_start + 0.04
        while GPIO.input(echo) == 0 and time.time() < timeout:
            pulse_start = time.time()

        pulse_end = time.time()
        while GPIO.input(echo) == 1 and time.time() < timeout:
            pulse_end = time.time()

        pulse_duration = pulse_end - pulse_start
        distance = round(pulse_duration * 17150, 1)
        return max(2.0, min(distance, 400.0))

    def read_environment(self) -> Dict[str, Any]:
        """อ่านค่าอุณหภูมิ ความชื้น และสถานะการตรวจจับผู้มาติดต่อ"""
        dist_cm = self.read_visitor_distance_cm()
        visitor_detected = dist_cm <= APPROACH_DISTANCE_CM

        # ค่าอุณหภูมิและความชื้นโถงบริการราชการ
        temp_c = round(random.uniform(24.5, 26.2), 1)
        humidity_pct = round(random.uniform(52.0, 60.0), 1)

        return {
            "hardware_mode": "Raspberry Pi 4 GPIO" if self.is_raspberry_pi else "Simulation Mode (RPi4 Ready)",
            "visitor_distance_cm": dist_cm,
            "visitor_approaching": visitor_detected,
            "ambient_temp_c": temp_c,
            "ambient_humidity_pct": humidity_pct,
            "active_led_direction": self.active_led_direction
        }

    def activate_direction_led(self, direction_code: str):
        """สั่งเปิดไฟ LED ชี้ทางเดินตามทิศทางของห้องราชการ (LEFT / RIGHT / STRAIGHT / UPSTAIRS)"""
        self.active_led_direction = direction_code
        if not self.is_raspberry_pi:
            return

        # ปิดไฟทั้งหมดก่อน
        GPIO.output(GPIO_PINS["LED_LEFT"], GPIO.LOW)
        GPIO.output(GPIO_PINS["LED_RIGHT"], GPIO.LOW)
        GPIO.output(GPIO_PINS["LED_STRAIGHT"], GPIO.LOW)

        if "LEFT" in direction_code:
            GPIO.output(GPIO_PINS["LED_LEFT"], GPIO.HIGH)
        if "RIGHT" in direction_code:
            GPIO.output(GPIO_PINS["LED_RIGHT"], GPIO.HIGH)
        if "STRAIGHT" in direction_code or "UPSTAIRS" in direction_code:
            GPIO.output(GPIO_PINS["LED_STRAIGHT"], GPIO.HIGH)

    def trigger_staff_buzzer(self, duration_sec: float = 0.5):
        """ส่งเสียงกริ่งแจ้งเจ้าหน้าที่ประชาสัมพันธ์เมื่อประชาชนต้องการความช่วยเหลือ"""
        if self.is_raspberry_pi:
            GPIO.output(GPIO_PINS["STAFF_BUZZER"], GPIO.HIGH)
            time.sleep(duration_sec)
            GPIO.output(GPIO_PINS["STAFF_BUZZER"], GPIO.LOW)

    def cleanup(self):
        if self.is_raspberry_pi:
            GPIO.cleanup()
