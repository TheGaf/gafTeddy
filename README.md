# Teddy Bear Project — Round 2 (Pigpio, Goertzel, Smooth Eye Close)

This release provides a simple, testable project layout for a Raspberry Pi-based "teddy" that:
- Captures audio (via ALSA / BlueALSA loopback routing)
- Classifies frames as "vocal" vs "non-vocal" using RMS/ZCR + lightweight Goertzel features
- Drives servos for mouth/eyes (pigpio if present, otherwise simulated)
- Smooth eye closing with configurable duration
- Small state machine that opens mouth on speech and closes eyes on idle

Quick start (on Pi):
1. Ensure loopback and BlueALSA are configured (see etc/asound.conf).
2. Enable pigpio: `sudo systemctl enable --now pigpiod`
3. Install Python deps:
   sudo apt update
   sudo apt install -y bluez bluealsa alsa-utils pigpio python3-pip libasound2-dev
   sudo pip3 install pyalsaaudio pigpio
4. Edit config.json to set `"bt_device_mac"` if you plan to connect a phone.
5. Run:
   python3 teddy_bear_project.py start

This repository is intentionally lightweight so you can test algorithms and hardware wiring incrementally.