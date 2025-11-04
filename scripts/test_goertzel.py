#!/usr/bin/env python3
"""
Quick script to sanity-check the Goertzel implementation in speech_detector.
Generates a pure sine and prints computed vocalness pieces.
"""
import math
import struct
import os
from src.speech_detector import SpeechDetector
from src.config import load_config

# load project-root config regardless of current working dir
cfg = load_config(os.path.join(os.path.dirname(__file__), "..", "config.json"))
sd = SpeechDetector(cfg)

def make_sine(freq, sr=44100, dur=0.1, amp=0.5):
    n = int(sr*dur)
    samples = [amp*math.sin(2*math.pi*freq*i/sr) for i in range(n)]
    # convert to 16-bit PCM bytes
    ints = [int(max(-32767, min(32767, int(s*32767)))) for s in samples]
    raw = struct.pack("<" + "h"*len(ints), *ints)
    return raw

if __name__ == "__main__":
    for f in (300, 500, 1000, 2000):
        raw = make_sine(f)
        info = sd.compute_vocalness(raw)
        print(f"freq={f} -> vocalness={info['vocalness']:.3f} rms={info['rms']:.4f} centroid={info['centroid']:.3f}")
