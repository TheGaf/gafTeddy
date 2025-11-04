import logging
import logging.handlers
import os
import time

_logger = None
_last_throttle = {}

def setup_logging(config):
    global _logger
    level_name = config.get("logging", {}).get("level", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)
    log_file = config.get("logging", {}).get("file")
    logger = logging.getLogger("teddy")
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    logger.handlers = []
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            fh = logging.handlers.TimedRotatingFileHandler(log_file, when="midnight", backupCount=7)
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            logger.warning("Failed to setup file logging")
    _logger = logger

def get_logger():
    global _logger
    if _logger is None:
        logging.basicConfig(level=logging.INFO)
        _logger = logging.getLogger("teddy")
    return _logger

def log_throttle(key: str, interval_s: float, level="info", msg="", *args, **kwargs):
    global _last_throttle
    now = time.time()
    last = _last_throttle.get(key, 0.0)
    if now - last >= interval_s:
        _last_throttle[key] = now
        logger = get_logger()
        if level == "debug":
            logger.debug(msg, *args, **kwargs)
        elif level == "warning":
            logger.warning(msg, *args, **kwargs)
        elif level == "error":
            logger.error(msg, *args, **kwargs)
        else:
            logger.info(msg, *args, **kwargs)
        return True
    return False