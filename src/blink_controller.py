#!/usr/bin/env python3
"""
Blink controller that issues eye-close/open commands to a ServoController.
Implements blink suppression while the mouth is active. Accepts an optional
mouth_servo to decide when blinking should be suppressed.
"""
import threading
import time
import random
from src.logger import get_logger

class BlinkController:
    def __init__(self, eyes_servo,
                 mouth_servo=None,
                 mean_interval_s: float = 6.0,
                 duration_ms: int = 160,
                 suppress_mouth_on: float = 0.25,
                 suppress_mouth_off: float = 0.10,
                 suppress_off_ms: int = 200):
        """
        eyes_servo: ServoController used to blink (move eyelids)
        mouth_servo: optional ServoController to read mouth level (0..1)
        mean_interval_s: average interval between blinks (exponential)
        duration_ms: blink duration (close->open)
        suppress_mouth_on: mouth level above which blinking is disabled
        suppress_mouth_off: mouth level below which blinking may be enabled after hold
        suppress_off_ms: required ms of mouth_level < suppress_mouth_off before blinks resume
        """
        self.eyes = eyes_servo
        self.mouth = mouth_servo
        self.mean = mean_interval_s
        self.duration = duration_ms / 1000.0
        self.suppress_on = float(suppress_mouth_on)
        self.suppress_off = float(suppress_mouth_off)
        self.suppress_off_ms = int(suppress_off_ms)
        self._running = False
        self._thread = None
        self.log = get_logger()
        self._last_mouth_low_ts = 0.0

    def start(self):
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)

    def _mouth_level(self):
        """
        Returns mouth normalized level (0..1) based on mouth servo angle.
        If mouth servo unavailable, returns 0.0 (allow blinking).
        """
        try:
            if self.mouth is None:
                return 0.0
            min_a = float(self.mouth.min_angle)
            max_a = float(self.mouth.max_angle)
            if max_a <= min_a:
                return 0.0
            level = (float(self.mouth.angle) - min_a) / max(1e-6, (max_a - min_a))
            return max(0.0, min(1.0, level))
        except Exception:
            return 0.0

    def _perform_blink(self):
        try:
            close_angle = self.eyes.min_angle
            open_angle = getattr(self.eyes, "neutral", self.eyes.max_angle)
            # close
            self.eyes.set_target_angle(close_angle, duration_s=self.duration)
            time.sleep(self.duration)
            # open
            self.eyes.set_target_angle(open_angle, duration_s=max(0.01, self.duration / 1.5))
        except Exception as e:
            self.log.debug("Blink perform error: %s", e)

    def _can_blink_now(self):
        """
        Return True if blinks are allowed now: mouth has been low for suppress_off_ms.
        """
        if self.mouth is None:
            return True
        lvl = self._mouth_level()
        now = time.time()
        if lvl <= self.suppress_off:
            # if first time low, record timestamp
            if self._last_mouth_low_ts == 0.0:
                self._last_mouth_low_ts = now
        else:
            # if above suppress_on reset low timer
            if lvl > self.suppress_on:
                self._last_mouth_low_ts = 0.0
        if self._last_mouth_low_ts == 0.0:
            return False
        # require sustained low for configured ms
        held_ms = (now - self._last_mouth_low_ts) * 1000.0
        return held_ms >= self.suppress_off_ms

    def _loop(self):
        while self._running:
            # random wait between blink attempts
            wait = random.expovariate(1.0 / max(0.1, self.mean))
            time.sleep(wait)
            try:
                if self._can_blink_now():
                    self._perform_blink()
                else:
                    # skip blink attempt; continue loop
                    continue
            except Exception as e:
                self.log.debug("Blink loop error: %s", e)