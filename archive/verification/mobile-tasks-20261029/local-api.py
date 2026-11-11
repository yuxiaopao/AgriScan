"""Disposable local browser QA server; no production credentials, model or data."""
import os,sys,time
from pathlib import Path
folder=Path(__file__).resolve().parent
os.environ.update(DATABASE_URL=f"sqlite:///{folder/'qa.sqlite'}",UPLOAD_DIR=str(folder/'uploads'),REDIS_URL='',MODEL_MANIFEST='',CLASSIFICATION_MODEL_MANIFEST='',DEMO_MODE='true',ADMIN_USERNAME='qa_mobile_local',ADMIN_PASSWORD='REDACTED_SECRET',LLM_ENABLED='false',EMAIL_VERIFICATION_ENABLED='false',REGISTRATION_ENABLED='true')
sys.path.insert(0,'E:/AgriScan/backend')
from app.main import app
original=app.state.inference.predict
def delayed(path,crop=None):
    time.sleep(4)
    return original(path,crop)
app.state.inference.predict=delayed
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=18931,log_level='warning')
