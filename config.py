import os
import shutil
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Detect serverless environment (e.g. Vercel, AWS Lambda)
IS_SERVERLESS = bool(os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))

# SQLite Database path selection (read-only filesystem handling for Vercel)
DEFAULT_SQLITE_PATH = os.path.join(BASE_DIR, 'database', 'cms_db.sqlite')
if IS_SERVERLESS:
    TMP_SQLITE_PATH = '/tmp/cms_db.sqlite'
    if not os.path.exists(TMP_SQLITE_PATH) and os.path.exists(DEFAULT_SQLITE_PATH):
        try:
            shutil.copy2(DEFAULT_SQLITE_PATH, TMP_SQLITE_PATH)
        except Exception:
            pass
    ACTIVE_DATABASE_PATH = TMP_SQLITE_PATH
    ACTIVE_UPLOAD_FOLDER = '/tmp/uploads'
else:
    ACTIVE_DATABASE_PATH = DEFAULT_SQLITE_PATH
    ACTIVE_UPLOAD_FOLDER = os.path.join(BASE_DIR, 'assets', 'uploads')

try:
    os.makedirs(ACTIVE_UPLOAD_FOLDER, exist_ok=True)
except Exception:
    pass

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get('SECRET_KEY', 'courier-management-system-secret-key-2026')
    
    # MySQL Database Configuration
    DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'cms_db')
    
    # SQLite Database Fallback / Migration Reference
    DATABASE = os.environ.get('DATABASE', ACTIVE_DATABASE_PATH)
    SQL_SCHEMA_PATH = os.path.join(BASE_DIR, 'database', 'cms_db.sql')
    
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', ACTIVE_UPLOAD_FOLDER)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
