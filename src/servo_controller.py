#!/usr/bin/env python3
"""
Servo controller with pigpio if available, otherwise simulated.
Implements symmetric ease-in / ease-out when a duration is specified.
Exposes start(), set_target_angle(angle, duration_s=None) and stop().
"""
import math
import time
from threading import Thread, Event
from src.logger import get_logger

try:
    import pigpio
except Exception:
    pigpio = None

class ServoController:
    def __init__(self, pin:int, min_angle:int=0, max_angle:int=180, neutral:int=90,
                 pulse_min_ms:float=0.5, pulse_max_ms:float=2.5, max_speed_deg_per_s:float=180.0):
        self.pin = int(pin)
        self.min_angle = int(min_angle)
        self.max_angle = int(max_angle)
        self.angle = int(neutral)
        self.target = int(neutral)
        self.pulse_min_ms = float(pulse_min_ms)
        self.pulse_max_ms = float(pulse_max_ms)
        self.max_speed = float(max_speed_deg_per_s)
        self.log = get_logger()

        # Move/easing state
        self._move_start_angle = self.angle
        self._move_target_angle = self.angle
        self._move_start_ts = None
        self._move_duration = None

        # Thread control (do NOT start thread here)
        self._stop_event = Event()
        self._thread = None

        # pigpio handle if available
        self._pi = None
        if pigpio:
            try:
                self._pi = pigpio.pi()
                if not self._pi.connected:
                    self._pi = None
            except Exception:
                self._pi = None

    def start(self):
        """Start the background servo worker thread. Safe to call multiple times."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._thread_run, daemon=True)
        self._thread.start()
        self.log.debug("Servo(pin=%s) thread started", self.pin)

    def _angle_to_pulse(self, angle):
        # map angle to microseconds
        frac = (angle - self.min_angle) / max(1.0, (self.max_angle - self.min_angle))
        ms = self.pulse_min_ms + frac * (self.pulse_max_ms - self.pulse_min_ms)
        return int(ms * 1000)

    def set_target_angle(self, angle:int, duration_s:float=None):
        """
        Set a new target angle. If duration_s is provided and >0, perform
        an ease-in/ease-out move over that duration.
        """
        angle = max(self.min_angle, min(self.max_angle, int(angle)))
        if duration_s and duration_s > 0.0:
            # start a duration-based eased move from current angle -> angle
            self._move_start_angle = int(self.angle)
            self._move_target_angle = int(angle)
            self._move_start_ts = time.time()
            self._move_duration = float(duration_s)
            # Keep target in sync for fallback
            self.target = int(angle)
        else:
            # immediate / speed-limited move to target angle
            self._move_duration = None
            self.target = int(angle)
        self.log.debug("Servo(pin=%s) set_target_angle target=%s duration=%s", self.pin, angle, duration_s)

    def _apply_pulse(self, angle):
        pulse = self._angle_to_pulse(angle)
        if self._pi:
            try:
                self._pi.set_servo_pulsewidth(self.pin, pulse)
            except Exception:
                # don't spam errors; leave simulation logging
                pass
        else:
            # simulated: occasional debug log
            self.log.debug("Servo(pin=%s) -> angle=%s pulse=%s us", self.pin, angle, pulse)

    def _thread_run(self):
        prev = time.time()
        while not self._stop_event.is_set():
            now = time.time()
            dt = now - prev
            prev = now
            try:
                if self._move_duration and self._move_start_ts is not None:
                    # duration-based ease-in/ease-out move
                    elapsed = now - self._move_start_ts
                    t = min(1.0, elapsed / max(1e-6, self._move_duration))
                    # symmetric ease in / ease out: ease = 0.5 - 0.5*cos(pi * t)
                    ease = 0.5 - 0.5 * math.cos(math.pi * t)
                    new_angle = int(round(self._move_start_angle + (self._move_target_angle - self._move_start_angle) * ease))
                    self.angle = new_angle
                    self._apply_pulse(self.angle)
                    if t >= 1.0:
                        # complete
                        self._move_duration = None
                        self._move_start_ts = None
                        self.target = self._move_target_angle
                else:
                    # velocity-limited stepping toward self.target
                    if self.angle != self.target:
                        max_step = self.max_speed * dt
                        diff = self.target - self.angle
                        if abs(diff) <= max_step:
                            self.angle = self.target
                        else:
                            step = max_step if diff > 0 else -max_step
                            # angles are ints
                            self.angle = int(round(self.angle + step))
                        self._apply_pulse(self.angle)
                # sleep a little for responsive control
                time.sleep(0.02)
            except Exception as e:
                self.log.exception("Servo thread exception: %s", e)
                time.sleep(0.05)

    def stop(self):
        """Stop the background thread and release pigpio resources if any."""
        self._stop_event.set()
        try:
            if self._thread:
                self._thread.join(timeout=0.5)
        except Exception:
            pass
        self._thread = None
        if self._pi:
            try:
                self._pi.set_servo_pulsewidth(self.pin, 0)
                self._pi.stop()
            except Exception:
                pass
        self.log.debug("Servo(pin=%s) stopped", self.pin)
