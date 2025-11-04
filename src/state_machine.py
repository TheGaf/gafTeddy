#!/usr/bin/env python3
"""
Very small Teddy state machine (Round 3 refinements):
- Integrates the updated speech_detector and blink suppression
- Emits speech_confidence in telemetry
- Enforces min-open time for mouth and checks eyes proximity before SLEEP
"""
import time
import json
from src.logger import get_logger, log_throttle
from src.audio_capture import AudioCapture
from src.speech_detector import SpeechDetector
from src.servo_controller import ServoController
from src.blink_controller import BlinkController
from src.bt_manager import BTManager

class TeddyStateMachine:
    def __init__(self, config):
        self.config = config
        self.log = get_logger()
        self.audio = AudioCapture(config)
        self.detector = SpeechDetector(config)
        serv_cfg = config.get("servos", {})
        mouth_cfg = serv_cfg.get("mouth", {})
        eyes_cfg = serv_cfg.get("eyes", {})

        # Create controllers but DO NOT start threads here
        self.mouth = ServoController(pin=mouth_cfg.get("pin", 18),
                                     min_angle=mouth_cfg.get("min_angle", 20),
                                     max_angle=mouth_cfg.get("max_angle", 120),
                                     neutral=mouth_cfg.get("neutral", 20),
                                     pulse_min_ms=serv_cfg.get("pulse_min_ms", 0.5),
                                     pulse_max_ms=serv_cfg.get("pulse_max_ms", 2.5),
                                     max_speed_deg_per_s=serv_cfg.get("max_speed_deg_per_s", {}).get("mouth", 180))
        self.eyes = ServoController(pin=eyes_cfg.get("pin", 23),
                                    min_angle=eyes_cfg.get("min_angle", 10),
                                    max_angle=eyes_cfg.get("max_angle", 90),
                                    neutral=eyes_cfg.get("neutral", 10),
                                    pulse_min_ms=serv_cfg.get("pulse_min_ms", 0.5),
                                    pulse_max_ms=serv_cfg.get("pulse_max_ms", 2.5),
                                    max_speed_deg_per_s=serv_cfg.get("max_speed_deg_per_s", {}).get("eyes", 90))

        # BlinkController now accepts mouth_servo for suppression
        blink_cfg = config.get("blink", {})
        blink_params = {
            "mean_interval_s": blink_cfg.get("mean_interval_s", 6.0),
            "duration_ms": blink_cfg.get("duration_ms", 160),
            "suppress_mouth_on": config.get("blink", {}).get("suppress_mouth_on", 0.25),
            "suppress_mouth_off": config.get("blink", {}).get("suppress_mouth_off", 0.10),
            "suppress_off_ms": config.get("blink", {}).get("suppress_off_ms", 200),
        }
        self.blinker = BlinkController(self.eyes,
                                       mouth_servo=self.mouth,
                                       mean_interval_s=blink_params["mean_interval_s"],
                                       duration_ms=blink_params["duration_ms"],
                                       suppress_mouth_on=blink_params["suppress_mouth_on"],
                                       suppress_mouth_off=blink_params["suppress_mouth_off"],
                                       suppress_off_ms=blink_params["suppress_off_ms"])

        self.bt = BTManager(config)
        self.running = False
        self.state = "INIT"

        # speech/mouth timing
        self.last_vocal_ts = 0.0
        self.min_open_ms = config.get("speech",{}).get("min_open_time_ms", 160)
        self.idle_timeout = config.get("speech",{}).get("idle_timeout_s", 10)
        self.tick_s = config.get("main_loop",{}).get("tick_s", 0.04)

        # telemetry
        telemetry_cfg = config.get("telemetry", {})
        self._status_path = telemetry_cfg.get("status_path", "/tmp/teddy_status.json")
        self._status_write_interval = telemetry_cfg.get("write_interval_s", 1.0)
        self._last_status_write_ts = 0.0
        self._last_vocalness = 0.0

    def start_subsystems(self):
        # Start servo threads first so blink controller has servo state available
        try:
            self.mouth.start()
        except Exception as e:
            self.log.debug("Failed to start mouth servo: %s", e)
        try:
            self.eyes.start()
        except Exception as e:
            self.log.debug("Failed to start eyes servo: %s", e)
        # Start audio and BT
        self.audio.start()
        self.bt.start()
        # Start blinker after servos
        self.blinker.start()

    def stop_subsystems(self):
        # stop in reverse order
        try:
            self.blinker.stop()
        except Exception:
            pass
        try:
            self.audio.stop()
        except Exception:
            pass
        try:
            self.bt.stop()
        except Exception:
            pass
        try:
            self.mouth.stop()
        except Exception:
            pass
        try:
            self.eyes.stop()
        except Exception:
            pass

    def _write_status(self):
        try:
            status = {
                "state": self.state,
                "bt_connected": self.bt.is_connected(),
                "last_vocal_ts": self.last_vocal_ts,
                "speech_confidence": self._last_vocalness,
                "mouth_angle": self.mouth.angle,
                "eyes_angle": self.eyes.angle,
                "ts": time.time()
            }
            with open(self._status_path, "w") as f:
                json.dump(status, f)
        except Exception as e:
            self.log.debug("Failed to write status: %s", e)

    def run(self):
        self.running = True
        self.start_subsystems()
        self.state = "RUNNING"
        self.log.info("Teddy state machine started")
        try:
            while self.running:
                levels = self.audio.get_levels()
                raw = levels.get("raw", b"")
                det_res = self.detector.is_vocal(raw)
                vocal_now = det_res.get("vocal", False)
                info = det_res.get("info", {})
                self._last_vocalness = info.get("vocalness", 0.0)

                now = time.time()
                if vocal_now:
                    # register vocal and open mouth
                    self.last_vocal_ts = now
                    # quick open when speaking; duration small to follow plosives
                    self.mouth.set_target_angle(self.mouth.max_angle, duration_s=0.05)
                    log_throttle("vocal", self.config.get("logging",{}).get("throttle_s",5.0),
                                 msg="Vocal detected: %s" % (info,))
                else:
                    # if enough time since last vocal, close mouth to neutral/min
                    if (now - self.last_vocal_ts) * 1000.0 > self.min_open_ms:
                        self.mouth.set_target_angle(self.mouth.min_angle, duration_s=0.08)

                # Idle handling: smooth eye close when idle, keep open otherwise
                if (now - self.last_vocal_ts) > self.idle_timeout:
                    # request close over configured duration
                    eye_close_duration = self.config.get("servos",{}).get("eye_close_duration_s", 2.5)
                    self.eyes.set_target_angle(self.eyes.max_angle, duration_s=eye_close_duration)
                    # if eyes sufficiently closed (within 3 degrees) and idle for idle_timeout, consider SLEEP
                    if abs(self.eyes.angle - self.eyes.max_angle) <= 3:
                        if self.state != "SLEEP":
                            self.log.info("Entering SLEEP state")
                        self.state = "SLEEP"
                else:
                    # keep eyes at neutral (open)
                    self.eyes.set_target_angle(self.eyes.min_angle, duration_s=0.2)
                    if self.state == "SLEEP":
                        self.log.info("Waking from SLEEP")
                    self.state = "RUNNING"

                # telemetry writes at interval
                if now - self._last_status_write_ts >= self._status_write_interval:
                    self._write_status()
                    self._last_status_write_ts = now

                time.sleep(self.tick_s)
        finally:
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_subsystems()
        self.log.info("Teddy stopped")

    def get_status(self):
        return {
            "state": self.state,
            "bt_connected": self.bt.is_connected(),
            "last_vocal_ts": self.last_vocal_ts,
            "speech_confidence": self._last_vocalness
        }
