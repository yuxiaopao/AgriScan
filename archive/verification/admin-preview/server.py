from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))

from fastapi.staticfiles import StaticFiles
from app.config import Settings
from app.main import create_app
import uvicorn

folder = Path(__file__).resolve().parent
app = create_app(Settings(
    database_url=f"sqlite:///{folder / 'preview.db'}", redis_url="",
    upload_dir=folder / "uploads", demo_mode=True,
    admin_username="admin", admin_password="REDACTED_SECRET",
    registration_enabled=True, email_verification_enabled=False, llm_enabled=False,
    jwt_secret="REDACTED_SECRET",
    model_manifest=str(root / "models/releases/plantvillage-yolo26m-906cf72f6bf0/manifest.json"),
))
app.mount("/", StaticFiles(directory=root / "frontend/dist", html=True), name="preview")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)
