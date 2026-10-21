"""Prevent automatic system sleep only while this exact training process exists."""
import ctypes
import json
import os
import time

import psutil

from prepare_data import ROOT, write_json

STATUS = ROOT / "training/awake-status.json"
CONTINUOUS = 0x80000000
SYSTEM_REQUIRED = 0x00000001


def main():
    state = json.loads((ROOT / "training/status.json").read_text(encoding="utf-8"))
    process = psutil.Process(state["pid"])
    created = process.create_time()
    if abs(created - state["started_at"]) > 60 or not any("workflow.py" in part for part in process.cmdline()):
        raise RuntimeError("Recorded PID no longer identifies the training workflow")
    previous = ctypes.windll.kernel32.SetThreadExecutionState(CONTINUOUS | SYSTEM_REQUIRED)
    if not previous:
        raise ctypes.WinError()
    write_json(STATUS, {"stage": "preventing_automatic_sleep", "pid": os.getpid(),
                        "training_pid": process.pid, "training_process_created": created,
                        "display_may_sleep": True, "started_at": time.time()})
    try:
        while process.is_running() and process.create_time() == created:
            try:
                process.wait(timeout=30)
            except psutil.TimeoutExpired:
                continue
            break
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(CONTINUOUS)
        write_json(STATUS, {"stage": "released", "pid": os.getpid(), "updated_at": time.time()})


if __name__ == "__main__":
    main()
