#!/usr/bin/env python3
"""
Interactive calibrator for servos (simple).
"""
import os
from src.config import load_config, save_config
from src.servo_controller import ServoController
from src.logger import setup_logging, get_logger

def run_calibrator(config_path):
    config = load_config(config_path)
    setup_logging(config)
    log = get_logger()
    servos_cfg = config["servos"]
    mouth_cfg = servos_cfg["mouth"]
    eyes_cfg = servos_cfg["eyes"]

    mouth = ServoController(pin=mouth_cfg["pin"],
                            min_angle=mouth_cfg["min_angle"],
                            max_angle=mouth_cfg["max_angle"],
                            neutral=mouth_cfg["neutral"],
                            pulse_min_ms=servos_cfg.get("pulse_min_ms", 0.5),
                            pulse_max_ms=servos_cfg.get("pulse_max_ms", 2.5),
                            max_speed_deg_per_s=servos_cfg.get("max_speed_deg_per_s", {}).get("mouth", 180))
    eyes = ServoController(pin=eyes_cfg["pin"],
                           min_angle=eyes_cfg["min_angle"],
                           max_angle=eyes_cfg["max_angle"],
                           neutral=eyes_cfg["neutral"],
                           pulse_min_ms=servos_cfg.get("pulse_min_ms", 0.5),
                           pulse_max_ms=servos_cfg.get("pulse_max_ms", 2.5),
                           max_speed_deg_per_s=servos_cfg.get("max_speed_deg_per_s", {}).get("eyes", 90))
    # Start servo threads for calibrator
    mouth.start()
    eyes.start()

    print("Calibration CLI")
    print("Commands: select [mouth|eyes], up, down, setneutral, save, quit")
    selected = "mouth"
    try:
        while True:
            cmd = input(f"[{selected}]> ").strip().lower()
            if cmd in ("quit", "q", "exit"):
                break
            if cmd.startswith("select"):
                parts = cmd.split()
                if len(parts) >= 2 and parts[1] in ("mouth", "eyes"):
                    selected = parts[1]
                else:
                    print("select mouth|eyes")
                continue
            controller = mouth if selected == "mouth" else eyes
            cfg = mouth_cfg if selected == "mouth" else eyes_cfg
            if cmd in ("up", "u"):
                cfg["neutral"] = min(cfg["max_angle"], cfg["neutral"] + 2)
                controller.set_target_angle(cfg["neutral"], duration_s=0.2)
            elif cmd in ("down", "d"):
                cfg["neutral"] = max(cfg["min_angle"], cfg["neutral"] - 2)
                controller.set_target_angle(cfg["neutral"], duration_s=0.2)
            elif cmd == "setneutral":
                try:
                    cfg["neutral"] = int(input("new neutral: "))
                    controller.set_target_angle(cfg["neutral"], duration_s=0.2)
                except Exception:
                    print("Invalid value")
            elif cmd == "save":
                save_config(config_path, config)
                print("Saved", config_path)
            else:
                print("Unknown command.")
    finally:
        mouth.stop()
        eyes.stop()
        print("Exiting calibrator.")

if __name__ == "__main__":
    run_calibrator(os.path.join(os.path.dirname(__file__), "config.json"))
