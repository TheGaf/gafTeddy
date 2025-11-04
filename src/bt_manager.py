"""
Simple bluetoothctl-based reconnect manager (non-blocking).
Assumes device already paired/trusted.
"""
import threading
import time
import subprocess
from src.logger import get_logger

class BTManager:
    def __init__(self, config):
        self.config = config
        self._mac = config.get("bt_device_mac", "").strip()
        self._running = False
        self._thread = None
        self._connected = False
        self._last_attempt = 0.0
        self._last_result = ""
        self.log = get_logger()

    def start(self):
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def is_connected(self):
        return self._connected

    def last_attempt_info(self):
        return {"ts": self._last_attempt, "result": self._last_result}

    def _run_btctl(self, cmd):
        p = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = p.communicate(cmd + "\n")
        return out

    def _check_connected(self):
        if not self._mac:
            return False
        out = self._run_btctl(f"info {self._mac}")
        return "Connected: yes" in out

    def _connect(self):
        if not self._mac:
            return False
        self.log.info("Attempting bluetooth connect to %s", self._mac)
        out = self._run_btctl(f"connect {self._mac}")
        self._last_result = out.strip()
        return "Connection successful" in out or "Successful" in out or "Connected: yes" in out

    def _loop(self):
        backoff = 1.0
        while self._running:
            try:
                connected = self._check_connected()
                if connected:
                    if not self._connected:
                        self.log.info("Bluetooth device connected")
                    self._connected = True
                    self._last_result = "connected"
                    backoff = 1.0
                else:
                    if self._connected:
                        self.log.warning("Bluetooth device disconnected")
                    self._connected = False
                    ok = self._connect()
                    self._last_attempt = time.time()
                    if ok:
                        self._connected = True
                        backoff = 1.0
                    else:
                        backoff = min(backoff * 2.0, 60.0)
                        self.log.debug("Connect failed, backing off %s", backoff)
                time.sleep(backoff)
            except Exception as e:
                self.log.exception("BT manager loop exception: %s", e)
                time.sleep(5.0)