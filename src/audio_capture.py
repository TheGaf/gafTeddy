"""
Audio capture placeholder using alsaaudio if available.
Provides a simple get_frame() and get_levels() API.
"""
import threading
import time
import struct
import math
from collections import deque
from src.logger import get_logger

try:
    import alsaaudio
except Exception:
    alsaaudio = None

class AudioCapture:
    def __init__(self, config):
        self.config = config
        self.device = config["audio"].get("device", "hw:Loopback,1,0")
        self.rate = int(config["audio"].get("sample_rate", 44100))
        self.channels = int(config["audio"].get("channels", 1))
        self.framesize = int(config["audio"].get("frame_size", 2048))
        self._running = False
        self._thread = None
        self._latest = {"rms": 0.0, "zcr": 0.0, "peak": 0.0, "ts": time.time(), "raw": b""}
        self._lock = threading.Lock()
        self.log = get_logger()
        self._pcm = None

    def start(self):
        if self._thread:
            return
        if alsaaudio is None:
            self.log.warning("python-alsaaudio not available — audio capture disabled (simulated)")
            return
        try:
            self._pcm = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, device=self.device)
            self._pcm.setchannels(self.channels)
            self._pcm.setrate(self.rate)
            self._pcm.setformat(alsaaudio.PCM_FORMAT_S16_LE)
            self._pcm.setperiodsize(self.framesize)
        except Exception as e:
            self.log.warning("Failed to open ALSA device: %s", e)
            return
        self._running = True
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _compute_levels(self, raw):
        if not raw:
            return {"rms": 0.0, "zcr": 0.0, "peak": 0.0}
        # 16-bit signed little-endian mono
        fmt = "<" + "h" * (len(raw) // 2)
        samples = struct.unpack(fmt, raw)
        # RMS
        ssum = sum((s/32768.0)**2 for s in samples)
        rms = math.sqrt(ssum / max(1, len(samples)))
        # ZCR
        signs = [1 if s>0 else 0 for s in samples]
        zc = sum(abs(signs[i]-signs[i-1]) for i in range(1, len(signs))) / max(1, len(signs)-1)
        # peak
        peak = max(abs(s)/32768.0 for s in samples)
        return {"rms": rms, "zcr": zc, "peak": peak}

    def _thread_main(self):
        while self._running:
            try:
                l, data = self._pcm.read()
                if l:
                    levels = self._compute_levels(data)
                    with self._lock:
                        self._latest.update(levels)
                        self._latest["ts"] = time.time()
                        self._latest["raw"] = data
                else:
                    time.sleep(0.01)
            except Exception as e:
                self.log.exception("Audio capture error: %s", e)
                time.sleep(0.1)

    def get_levels(self):
        with self._lock:
            return dict(self._latest)