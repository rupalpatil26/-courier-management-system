import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'courier-management-system-secret-key-2026')
    
    # MySQL Database Configuration
    DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'cms_db')
    
    # SQLite Database Fallback / Migration Reference
    DATABASE = os.environ.get('DATABASE', os.path.join(BASE_DIR, 'database', 'cms_db.sqlite'))
    SQL_SCHEMA_PATH = os.path.join(BASE_DIR, 'database', 'cms_db.sql')
    
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'assets', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
