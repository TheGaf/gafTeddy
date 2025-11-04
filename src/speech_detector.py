#!/usr/bin/env python3
"""
Lightweight speech/vocal detector using RMS, ZCR and a few Goertzel bands.
Implements the decision rule and off-hold hysteresis described in Round 3.
Returns dicts with vocalness, rms, zcr, centroid for telemetry and decisions.
"""
import math
import time
from src.logger import get_logger

def goertzel(samples, sample_rate, freq):
    # Simple Goertzel implementation returning magnitude
    s_prev = 0.0
    s_prev2 = 0.0
    normalized_freq = float(freq) / sample_rate
    coeff = 2.0 * math.cos(2.0 * math.pi * normalized_freq)
    for s in samples:
        s_val = s
        s = s_val + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s
    mag = math.sqrt(max(0.0, s_prev2*s_prev2 + s_prev*s_prev - coeff*s_prev*s_prev2))
    return mag

class SpeechDetector:
    def __init__(self, config):
        self.config = config
        self.log = get_logger()
        self.sample_rate = int(config["audio"].get("sample_rate", 44100))
        self.goertzel_freqs = config["speech"].get("goertzel_freqs", [300, 500, 1000])
        self.weights = config["speech"].get("vocalness_weights", {"rms":0.6,"centroid":0.3,"zcr":0.1})
        self.rms_threshold = config["speech"].get("rms_threshold", 0.02)
        self.zcr_threshold = config["speech"].get("zcr_threshold", 0.05)
        self.on_th = config["speech"].get("vocalness_threshold_on", 0.45)
        self.off_th = config["speech"].get("vocalness_threshold_off", 0.30)
        self.off_hold_ms = config["speech"].get("off_hold_ms", 200)        # require this ms of continuous below to clear
        self.hysteresis_state = False
        self._last_above_ts = 0.0
        self._last_change_ts = time.time()

    def compute_vocalness(self, raw_bytes):
        """
        Returns a dict: { vocalness, rms, zcr, centroid }
        Safe for empty raw_bytes.
        """
        if not raw_bytes:
            return {"vocalness": 0.0, "rms": 0.0, "zcr": 0.0, "centroid": 0.0}
        import struct
        n = len(raw_bytes)//2
        if n <= 0:
            return {"vocalness": 0.0, "rms": 0.0, "zcr": 0.0, "centroid": 0.0}
        fmt = "<" + "h"*n
        try:
            ints = struct.unpack(fmt, raw_bytes)
        except Exception:
            return {"vocalness": 0.0, "rms": 0.0, "zcr": 0.0, "centroid": 0.0}
        samples = [s/32768.0 for s in ints]
        # RMS
        rms = math.sqrt(sum(s*s for s in samples)/max(1, len(samples)))
        # ZCR (use sign changes)
        signs = [1 if s>0 else 0 for s in samples]
        zcr = sum(abs(signs[i]-signs[i-1]) for i in range(1,len(signs))) / max(1, len(signs)-1)
        # spectral centroid approx using Goertzel magnitudes
        mags = []
        for f in self.goertzel_freqs:
            try:
                mags.append(goertzel(samples, self.sample_rate, f))
            except Exception:
                mags.append(0.0)
        centroid = 0.0
        s_mags = sum(mags)
        if s_mags > 0:
            centroid = sum(freq*m for freq,m in zip(self.goertzel_freqs, mags)) / s_mags
            centroid = centroid / max(self.goertzel_freqs)  # normalize to ~0..1
        # Combine features into vocalness
        w = self.weights
        rms_term = min(1.0, rms / max(1e-6, self.rms_threshold * 4))
        zcr_term = min(1.0, zcr / max(1e-6, self.zcr_threshold * 4))
        vocal = (w.get("rms",0.0) * rms_term +
                 w.get("centroid",0.0) * centroid +
                 w.get("zcr",0.0) * zcr_term)
        vocal = max(0.0, min(1.0, vocal))
        return {"vocalness": vocal, "rms": rms, "zcr": zcr, "centroid": centroid}

    def is_vocal(self, raw_bytes):
        """
        Implements decision:
          rms > threshold_rms AND
          vocalness >= on_th AND
          (centroid > 0.45 OR (1 - zcr_norm) > 0.55)
        plus off-hold hysteresis: only clear after off_hold_ms continuous below.
        Returns: { "vocal": bool, "info": compute_vocalness(...) }
        """
        info = self.compute_vocalness(raw_bytes)
        v = info["vocalness"]
        rms = info["rms"]
        zcr = info["zcr"]
        centroid = info["centroid"]
        now = time.time()

        # normalize zcr to 0..1 for voicedness test
        zcr_norm = min(1.0, zcr / max(1e-6, self.zcr_threshold * 4))
        voicedness = (1.0 - zcr_norm) > 0.55
        centroid_ok = centroid > 0.45
        rms_ok = rms > self.rms_threshold
        vocal_ok = v >= self.on_th

        candidate = rms_ok and vocal_ok and (centroid_ok or voicedness)

        if candidate:
            # mark last above time and set state true
            self._last_above_ts = now
            self.hysteresis_state = True
        else:
            # only clear after off_hold_ms since last above
            if (now - self._last_above_ts) * 1000.0 >= self.off_hold_ms:
                self.hysteresis_state = False

        return {"vocal": self.hysteresis_state, "info": info}