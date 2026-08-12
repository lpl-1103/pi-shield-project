#!/usr/bin/env python3
"""
Pi3 Shield 鍵盤控制程式

在互動式終端機執行，用單一按鍵直接控制：
- 兩顆燈泡（LED1 / LED2）：長亮、閃爍，各自獨立或一起
- 蜂鳴器：Do Re Mi Fa So 音符，以及一鍵播放《粉刷匠》
- 繼電器：開 / 關

按下 x 或 Ctrl+C 結束並釋放 GPIO。
參考: ~/it_shield_led_keyboard.py（同樣的 raw-terminal 按鍵讀取方式）
"""

from __future__ import annotations

import sys
import termios
import threading
import time
import tty

try:
    import RPi.GPIO as GPIO
except ImportError:
    # Fallback for development or editing on non-Raspberry Pi systems.
    class MockGPIO:
        BCM = 'BCM'
        OUT = 'OUT'
        IN = 'IN'
        HIGH = 1
        LOW = 0

        def __init__(self):
            self.pins = {}

        def setwarnings(self, flag):
            pass

        def setmode(self, mode):
            self.mode = mode

        def setup(self, pin, mode):
            self.pins[pin] = self.LOW

        def output(self, pin, value):
            self.pins[pin] = value
            print(f"[MOCK GPIO] pin {pin} -> {value}")

        def input(self, pin):
            return self.pins.get(pin, self.LOW)

        def PWM(self, pin, frequency):
            print(f"[MOCK GPIO] PWM create pin={pin}, freq={frequency}")
            return self.MockPWM(pin, frequency)

        def cleanup(self):
            print("[MOCK GPIO] cleanup")

        class MockPWM:
            def __init__(self, pin, freq):
                self.pin = pin
                self.freq = freq
                self.duty = 0

            def start(self, duty_cycle):
                self.duty = duty_cycle
                print(f"[MOCK PWM] start on pin={self.pin} duty={duty_cycle}")

            def ChangeFrequency(self, freq):
                self.freq = freq
                print(f"[MOCK PWM] change freq={freq}")

            def ChangeDutyCycle(self, duty_cycle):
                self.duty = duty_cycle
                print(f"[MOCK PWM] change duty={duty_cycle}")

            def stop(self):
                print("[MOCK PWM] stop")

    GPIO = MockGPIO()

# Pin definitions from it_shield.h
LED1 = 5
LED2 = 6
COM = 22
RELAY = 27
BUZZER = 16

NOTE_FREQUENCIES = {
    'do': 523,
    're': 587,
    'mi': 659,
    'fa': 698,
    'so': 784,
    'la': 880,
    'xi': 988,
    'do_high': 1047,
}

# 按鍵 -> 音符
NOTE_KEYS = {
    'q': 'do',
    'w': 're',
    'e': 'mi',
    'r': 'fa',
    't': 'so',
}

# 《粉刷匠》簡譜（使用者提供）：數字 1~7 為 do~xi，"-" 為空一拍（休止）。
# 要調整旋律只要改這串數字即可，不用動下面的產生邏輯。
PAINTER_SONG_JIANPU = (
    "5353531-24325---"
    "5353531-24321---"
    "2244325-24325---"
    "5353531-24321---"
)

# 簡譜數字 -> 音符名稱
JIANPU_DIGIT_TO_NOTE = {
    '1': 'do', '2': 're', '3': 'mi', '4': 'fa',
    '5': 'so', '6': 'la', '7': 'xi',
}

BEAT_SECONDS = 0.3


def _build_song_from_jianpu(jianpu, beat=BEAT_SECONDS):
    sequence = []
    for ch in jianpu:
        if ch == '-':
            sequence.append(('rest', beat))
        else:
            note = JIANPU_DIGIT_TO_NOTE.get(ch)
            if note:
                sequence.append((note, beat))
    return sequence


PAINTER_SONG = _build_song_from_jianpu(PAINTER_SONG_JIANPU)


class Pi3Shield:
    def __init__(self, debug=False):
        self.debug = debug
        self.pwm = None
        self._led_stop_event = None
        self._led_thread = None
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LED1, GPIO.OUT)
        GPIO.setup(LED2, GPIO.OUT)
        GPIO.setup(COM, GPIO.OUT)
        GPIO.setup(RELAY, GPIO.OUT)
        GPIO.setup(BUZZER, GPIO.OUT)
        GPIO.output(COM, GPIO.HIGH)
        self.led_all_off()
        self.relay_off()

    # ---------- LED (兩顆燈泡) ----------
    def _set_bulbs(self, bulb1, bulb2):
        GPIO.output(LED1, GPIO.HIGH if bulb1 else GPIO.LOW)
        GPIO.output(LED2, GPIO.HIGH if bulb2 else GPIO.LOW)

    def _stop_led_thread(self):
        if self._led_stop_event is not None:
            self._led_stop_event.set()
        if self._led_thread is not None and self._led_thread.is_alive():
            self._led_thread.join(timeout=0.3)
        self._led_stop_event = None
        self._led_thread = None

    def led_all_off(self):
        self._stop_led_thread()
        self._set_bulbs(False, False)

    def led_steady(self, bulb1=False, bulb2=False):
        """設定兩顆燈泡的長亮狀態，未指定的燈泡會關閉。"""
        self._stop_led_thread()
        self._set_bulbs(bulb1, bulb2)
        if self.debug:
            print(f"led_steady(bulb1={bulb1}, bulb2={bulb2})")

    def led_blink(self, bulb1=False, bulb2=False, interval=0.4):
        """讓指定燈泡閃爍（同步閃爍），未指定的燈泡會關閉。"""
        self._stop_led_thread()
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._blink_worker,
            args=(stop_event,),
            kwargs={'bulb1': bulb1, 'bulb2': bulb2, 'interval': interval},
            daemon=True,
        )
        self._led_stop_event = stop_event
        self._led_thread = thread
        thread.start()
        if self.debug:
            print(f"led_blink(bulb1={bulb1}, bulb2={bulb2}, interval={interval})")

    def _blink_worker(self, stop_event, bulb1=False, bulb2=False, interval=0.4):
        state = False
        while not stop_event.is_set():
            state = not state
            self._set_bulbs(bulb1 and state, bulb2 and state)
            time.sleep(interval)
        self._set_bulbs(False, False)

    # ---------- 蜂鳴器 ----------
    def _ensure_pwm(self, frequency):
        if self.pwm is None:
            self.pwm = GPIO.PWM(BUZZER, frequency)
            self.pwm.start(50)
        else:
            self.pwm.ChangeFrequency(frequency)
            self.pwm.ChangeDutyCycle(50)

    def stop_buzzer(self):
        if self.pwm:
            self.pwm.stop()
            self.pwm = None
        GPIO.output(BUZZER, GPIO.LOW)

    def play_tone(self, frequency, duration=0.3):
        if frequency <= 0:
            time.sleep(duration)
            return
        self._ensure_pwm(frequency)
        time.sleep(duration)
        self.stop_buzzer()

    def play_note(self, note_name, duration=0.3):
        note_name = note_name.lower()
        if note_name == 'rest':
            if self.debug:
                print(f"play_note(rest, duration={duration})")
            time.sleep(duration)
            return
        if note_name not in NOTE_FREQUENCIES:
            raise ValueError(f"Unknown note: {note_name}")
        if self.debug:
            print(f"play_note({note_name}, duration={duration})")
        self.play_tone(NOTE_FREQUENCIES[note_name], duration)

    def play_song(self, sequence, gap=0.03):
        for note_name, duration in sequence:
            self.play_note(note_name, duration)
            time.sleep(gap)

    # ---------- 繼電器 ----------
    def relay_on(self):
        GPIO.output(RELAY, GPIO.HIGH)
        if self.debug:
            print("relay_on()")

    def relay_off(self):
        GPIO.output(RELAY, GPIO.LOW)
        if self.debug:
            print("relay_off()")

    # ---------- 收尾 ----------
    def cleanup(self):
        self.led_all_off()
        self.stop_buzzer()
        self.relay_off()
        GPIO.cleanup()


MENU = """\
==================== Pi3 Shield 鍵盤控制 ====================
  燈泡 (LED1 / LED2)
    1 = 燈泡1 長亮      2 = 燈泡2 長亮      3 = 兩顆一起長亮
    4 = 燈泡1 閃爍      5 = 燈泡2 閃爍      6 = 兩顆一起閃爍
    0 = 燈泡全部熄滅

  蜂鳴器 (音符)
    q = Do   w = Re   e = Mi   r = Fa   t = So
    p = 播放《粉刷匠》

  繼電器
    o = 開啟 (ON)      k = 關閉 (OFF)

  x 或 Ctrl+C = 離開程式並釋放 GPIO
==============================================================
"""


def main():
    if not sys.stdin.isatty():
        print("請在互動式終端機執行本程式。", file=sys.stderr)
        return 2

    parser_debug = '--debug' in sys.argv

    print(MENU)
    shield = Pi3Shield(debug=parser_debug)
    saved_terminal = termios.tcgetattr(sys.stdin.fileno())
    status = "尚未操作"

    try:
        tty.setraw(sys.stdin.fileno())
        sys.stdout.write(f"\r> 目前狀態: {status}     ")
        sys.stdout.flush()
        while True:
            key = sys.stdin.read(1)
            if key in ('x', 'X', '\x03'):
                break
            elif key == '1':
                shield.led_steady(bulb1=True)
                status = "燈泡1 長亮"
            elif key == '2':
                shield.led_steady(bulb2=True)
                status = "燈泡2 長亮"
            elif key == '3':
                shield.led_steady(bulb1=True, bulb2=True)
                status = "燈泡1+2 一起長亮"
            elif key == '4':
                shield.led_blink(bulb1=True)
                status = "燈泡1 閃爍中"
            elif key == '5':
                shield.led_blink(bulb2=True)
                status = "燈泡2 閃爍中"
            elif key == '6':
                shield.led_blink(bulb1=True, bulb2=True)
                status = "燈泡1+2 一起閃爍中"
            elif key == '0':
                shield.led_all_off()
                status = "燈泡全部熄滅"
            elif key in NOTE_KEYS:
                note = NOTE_KEYS[key]
                shield.play_note(note, duration=0.4)
                status = f"播放音符 {note.upper()}"
            elif key == 'p':
                status = "播放《粉刷匠》中..."
                sys.stdout.write(f"\r> 目前狀態: {status}     ")
                sys.stdout.flush()
                shield.play_song(PAINTER_SONG)
                status = "《粉刷匠》播放完成"
            elif key == 'o':
                shield.relay_on()
                status = "繼電器 開啟"
            elif key == 'k':
                shield.relay_off()
                status = "繼電器 關閉"
            else:
                continue
            sys.stdout.write(f"\r> 目前狀態: {status}     ")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, saved_terminal)
        shield.cleanup()
        print("\n已釋放 GPIO，程式結束。")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
