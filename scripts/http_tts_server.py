#!/usr/bin/env python3
"""
Small HTTP TTS endpoint for Teddy.

POST /speak  JSON: {"text":"Hello Teddy", "rate":140}
GET  /health

Behavior:
- Uses espeak to synthesize a WAV to /tmp/teddy_speak.wav
- Plays the WAV to the configured USB speaker device (default "usbout")
- Also plays the WAV into the ALSA loopback (default "plughw:Loopback,0,0")
- Returns JSON {"ok":true,"msg":"played"} on success
"""
import os
import tempfile
import subprocess
import logging
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("teddy-http")

# Config override via environment
USB_DEVICE = os.environ.get("TTS_USB_DEVICE", "usbout")
LOOPBACK_DEVICE = os.environ.get("TTS_LOOPBACK_DEVICE", "plughw:Loopback,0,0")
ESPEAK_RATE = int(os.environ.get("TTS_ESPEAK_RATE", "140"))

def synthesize_text(text: str, rate: int = ESPEAK_RATE):
    fd, path = tempfile.mkstemp(prefix="teddy_tts_", suffix=".wav", dir="/tmp")
    os.close(fd)
    # espeak writes to file with -w
    cmd = ["espeak", "-s", str(rate), "-w", path, text]
    log.info("Synthesizing: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return path
    except subprocess.CalledProcessError as e:
        log.exception("espeak failed: %s", e)
        if os.path.exists(path):
            os.remove(path)
        raise

def play_file_to_device(path: str, device: str):
    # use aplay for low-overhead playback
    cmd = ["aplay", "-D", device, path]
    log.info("Playing %s to %s", path, device)
    # start asynchronously and return the Popen so caller can continue
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "usb_device": USB_DEVICE, "loopback_device": LOOPBACK_DEVICE})

@app.route("/speak", methods=["POST"])
def speak():
    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({"ok": False, "error": "missing 'text' field"}), 400
    text = body["text"]
    rate = int(body.get("rate", ESPEAK_RATE))
    try:
        wav = synthesize_text(text, rate=rate)
    except Exception as e:
        return jsonify({"ok": False, "error": "synthesis failed", "detail": str(e)}), 500

    # Play to USB speaker (audible)
    try:
        p_usb = play_file_to_device(wav, USB_DEVICE)
    except Exception as e:
        log.exception("Failed to play to USB device: %s", e)
        p_usb = None

    # Play into loopback so Teddy's VAD sees it and animates mouth/eyes
    try:
        p_lb = play_file_to_device(wav, LOOPBACK_DEVICE)
    except Exception as e:
        log.exception("Failed to play to loopback device: %s", e)
        p_lb = None

    # don't wait for playback to finish — return quickly
    # cleanup wav file after a short delay in background to avoid removing while playing (best-effort)
    try:
        subprocess.Popen(["/bin/sh", "-c", f"sleep 2 && rm -f {wav}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    return jsonify({"ok": True, "msg": "played", "usb_pid": p_usb.pid if p_usb else None, "loopback_pid": p_lb.pid if p_lb else None})

if __name__ == "__main__":
    # bind to all interfaces, port 5001
    app.run(host="0.0.0.0", port=5001, threaded=True)
