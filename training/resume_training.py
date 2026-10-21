"""Resume an interrupted run, refusing to launch over an existing workflow."""
import json
import subprocess
import sys

import psutil

from prepare_data import CONFIG, ROOT


def main():
    training = ROOT / "training"
    status_file = training / "status.json"
    if status_file.exists():
        state = json.loads(status_file.read_text(encoding="utf-8"))
        try:
            process = psutil.Process(state["pid"])
            if abs(process.create_time() - state["started_at"]) <= 60 and process.is_running():
                raise RuntimeError(f"Workflow is already running as PID {process.pid}; no duplicate job started")
        except psutil.NoSuchProcess:
            pass
    run = ROOT / "runs/classify" / CONFIG["training"]["name"]
    if not (run / "weights/last.pt").is_file():
        raise FileNotFoundError("No last.pt checkpoint exists; inspect the training failure before a new run")
    subprocess.run([sys.executable, "-u", str(training / "workflow.py"), "--resume"],
                   cwd=training, check=True)


if __name__ == "__main__":
    main()
