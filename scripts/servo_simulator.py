#!/usr/bin/env python3
"""
Simple simulator that creates two ServoController instances and moves them.
Useful if you don't have pigpio or physical servos yet.
"""
import time
from src.servo_controller import ServoController

def main():
    mouth = ServoController(pin=18, min_angle=20, max_angle=120, neutral=20)
    eyes = ServoController(pin=23, min_angle=10, max_angle=90, neutral=10)
    # explicitly start servo threads for the simulator
    mouth.start()
    eyes.start()
    try:
        while True:
            print("Opening mouth")
            mouth.set_target_angle(120, duration_s=0.5)
            time.sleep(1.0)
            print("Closing mouth")
            mouth.set_target_angle(20, duration_s=0.3)
            time.sleep(1.0)
            print("Close eyes")
            eyes.set_target_angle(90, duration_s=1.0)
            time.sleep(2.0)
            print("Open eyes")
            eyes.set_target_angle(10, duration_s=1.0)
            time.sleep(2.0)
    except KeyboardInterrupt:
        mouth.stop()
        eyes.stop()
        print("Simulator exit")

if __name__ == "__main__":
    main()
