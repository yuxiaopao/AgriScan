"""Prepare CUDA environment then start the verified training workflow unattended."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from prepare_data import ROOT, DATA, download_archive, write_json

TRAINING = ROOT / "training"
PYTHON = TRAINING / ".venv/Scripts/python.exe"
STATUS = TRAINING / "bootstrap-status.json"
TORCH_WHEEL = "torch-2.9.1+cu128-cp312-cp312-win_amd64.whl"
TORCH_URL = "https://download.pytorch.org/whl/cu128/torch-2.9.1%2Bcu128-cp312-cp312-win_amd64.whl"
TORCH_SHA = "3a01f0b64c10a82d444d9fd06b3e8c567b1158b76b2764b8f51bfd8f535064b0"
TORCH_BYTES = 2862033275


def status(stage, **details):
    write_json(STATUS, {"stage": stage, "pid": os.getpid(), "updated_at": time.time(), **details})


def execute(arguments):
    subprocess.run([str(PYTHON), *arguments], cwd=TRAINING, check=True)


def main():
    os.environ["PYTHONUTF8"] = "1"
    os.environ["YOLO_CONFIG_DIR"] = str(TRAINING / ".ultralytics")
    os.environ["YOLO_AUTOINSTALL"] = "false"
    wheel = TRAINING / "downloads" / TORCH_WHEEL
    status("downloading_torch")
    download_archive(wheel, TORCH_URL, TORCH_BYTES, TORCH_SHA, TRAINING / "torch-download-status.json")
    status("installing_environment")
    execute(["-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", str(wheel),
             "https://download.pytorch.org/whl/cu128/torchvision-0.24.1%2Bcu128-cp312-cp312-win_amd64.whl",
             "-r", str(TRAINING / "requirements.txt")])
    status("testing_workflow")
    execute(["-m", "pytest", "test_workflow.py", "-q", "--basetemp", str(ROOT / ".runtime/pytest-training-bootstrap")])
    execute(["workflow.py", "--smoke"])
    status("waiting_dataset")
    deadline = time.monotonic() + 24 * 3600
    while not (DATA / "dataset-report.json").is_file():
        progress = DATA / "download-status.json"
        if progress.exists():
            data = json.loads(progress.read_text(encoding="utf-8"))
            if data.get("stage") == "failed":
                raise RuntimeError(f"Dataset preparation failed: {data.get('error')}")
        if time.monotonic() >= deadline:
            raise TimeoutError("Dataset preparation did not finish within 24 hours")
        time.sleep(30)
    status("training")
    execute(["-u", "workflow.py"])
    status("finished")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        status("failed", error=str(error), traceback=traceback.format_exc())
        raise
