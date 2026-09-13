import os
import re
import time
import logging
import sqlite3
from datetime import datetime
from flask import g, current_app
from config import Config

logger = logging.getLogger(__name__)

# Try importing pymysql for MySQL connectivity
try:
    import pymysql
    import pymysql.cursors
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

def _sqlite_concat(*args):
    return ''.join(str(a) for a in args if a is not None)

def _sqlite_unix_timestamp(val=None):
    if val is None:
        return int(time.time())
    if isinstance(val, (int, float)):
        return int(val)
    try:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d'):
            try:
                dt = datetime.strptime(str(val).strip(), fmt)
                return int(dt.timestamp())
            except ValueError:
                pass
        return int(datetime.fromisoformat(str(val).strip()).timestamp())
    except Exception:
        return 0

def init_mysql_db(host, port, user, password, db_name, sql_file_path):
    """Ensure MySQL database and tables from cms_db.sql are created."""
    if not HAS_PYMYSQL:
        return False
    try:
        # Connect to MySQL server without database first to ensure db exists
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            cur.execute(f"USE `{db_name}`;")
            cur.execute("SHOW TABLES LIKE 'users';")
            tbl = cur.fetchone()
            if not tbl and os.path.isfile(sql_file_path):
                logger.info(f"Initializing MySQL database `{db_name}` from {sql_file_path}")
                with open(sql_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    sql_content = f.read()
                # Split SQL queries by semicolon
                statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
                for stmt in statements:
                    try:
                        cur.execute(stmt)
                    except Exception as stmt_err:
                        # Ignore comments or harmless syntax differences
                        pass
                conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.warning(f"Failed to auto-initialize MySQL database: {e}")
        return False

def get_db():
    if 'db' not in g:
        # Determine database driver
        db_type = 'sqlite'
        db_conn = None

        if HAS_PYMYSQL:
            host = current_app.config.get('DB_HOST', Config.DB_HOST)
            port = current_app.config.get('DB_PORT', Config.DB_PORT)
            user = current_app.config.get('DB_USER', Config.DB_USER)
            password = current_app.config.get('DB_PASSWORD', Config.DB_PASSWORD)
            db_name = current_app.config.get('DB_NAME', Config.DB_NAME)
            sql_file = current_app.config.get('SQL_SCHEMA_PATH', Config.SQL_SCHEMA_PATH)

            try:
                # Attempt connection to MySQL
                init_mysql_db(host, port, user, password, db_name, sql_file)
                db_conn = pymysql.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=db_name,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False
                )
                db_type = 'mysql'
            except Exception as mysql_err:
                logger.warning(
                    f"Could not connect to MySQL ({user}@{host}:{port}/{db_name}): {mysql_err}. "
                    f"Falling back to local SQLite database."
                )

        if db_conn is None:
            # SQLite fallback
            sqlite_path = current_app.config.get('DATABASE', Config.DATABASE)
            os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
            db_conn = sqlite3.connect(sqlite_path, detect_types=sqlite3.PARSE_DECLTYPES)
            db_conn.row_factory = sqlite3.Row
            db_conn.create_function('concat', -1, _sqlite_concat)
            db_conn.create_function('unix_timestamp', -1, _sqlite_unix_timestamp)
            db_conn.execute("PRAGMA foreign_keys = ON")
            db_type = 'sqlite'

        g.db = db_conn
        g.db_type = db_type

    return g.db

def get_db_type():
    if 'db_type' not in g:
        get_db()
    return g.get('db_type', 'sqlite')

def close_db(e=None):
    db = g.pop('db', None)
    g.pop('db_type', None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass

def _normalize_query(query, db_type):
    """Normalize query parameters across SQLite (?) and MySQL (%s)."""
    if db_type == 'mysql':
        # Replace unquoted '?' with '%s'
        # Simple and safe since CMS queries do not embed literal ? marks in strings
        return query.replace('?', '%s')
    else:
        # SQLite uses ?
        return query.replace('%s', '?')

def query_db(query, args=(), one=False):
    db = get_db()
    db_type = get_db_type()
    norm_query = _normalize_query(query, db_type)

    if db_type == 'mysql':
        with db.cursor() as cur:
            cur.execute(norm_query, args)
            rv = cur.fetchall()
            return (rv[0] if rv else None) if one else rv
    else:
        cur = db.execute(norm_query, args)
        rv = cur.fetchall()
        cur.close()
        return (dict(rv[0]) if rv else None) if one else [dict(r) for r in rv]

def execute_db(query, args=(), commit=True):
    db = get_db()
    db_type = get_db_type()
    norm_query = _normalize_query(query, db_type)

    if db_type == 'mysql':
        with db.cursor() as cur:
            cur.execute(norm_query, args)
            last_id = cur.lastrowid
        if commit:
            db.commit()
        return last_id
    else:
        cur = db.execute(norm_query, args)
        if commit:
            db.commit()
        last_id = cur.lastrowid
        cur.close()
        return last_id
