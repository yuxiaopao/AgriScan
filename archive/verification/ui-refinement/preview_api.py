import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.config import Settings
from app.main import create_app
import uvicorn
root = Path(__file__).resolve().parent
settings = Settings(database_url=f"sqlite:///{(root / 'preview.db').as_posix()}", redis_url='', upload_dir=root / 'uploads', demo_mode=True, admin_username='ui-preview', admin_password='REDACTED_SECRET', jwt_secret='REDACTED_SECRET', model_manifest='', llm_enabled=False, email_verification_enabled=False, registration_enabled=True)
uvicorn.run(create_app(settings), host='127.0.0.1', port=18000)
