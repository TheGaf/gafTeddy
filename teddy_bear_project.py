#!/usr/bin/env python3
"""
Main launcher / CLI for Teddy Bear project.

Usage:
  python3 teddy_bear_project.py start
  python3 teddy_bear_project.py status
  python3 teddy_bear_project.py calibrate
"""
import sys
import os
import json
from src.config import load_config
from src.logger import setup_logging, get_logger
from src.state_machine import TeddyStateMachine

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def main():
    if len(sys.argv) < 2:
        print("Usage: teddy_bear_project.py [start|status|calibrate]")
        return
    cmd = sys.argv[1]
    config = load_config(CONFIG_PATH)
    setup_logging(config)
    log = get_logger()
    if cmd == "start":
        log.info("Starting Teddy state machine")
        sm = TeddyStateMachine(config)
        try:
            sm.run()
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt received, stopping")
            sm.stop()
    elif cmd == "status":
        sm = TeddyStateMachine(config)
        status = sm.get_status()
        print(json.dumps(status, indent=2))
    elif cmd == "calibrate":
        import calibrate_cli
        calibrate_cli.run_calibrator(CONFIG_PATH)
    else:
        print("Unknown command:", cmd)

if __name__ == "__main__":
    main()