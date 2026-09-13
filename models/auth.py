import hashlib
import os
import time
from flask import session, current_app
from werkzeug.utils import secure_filename
from db import query_db, execute_db

def hash_password(password):
    return hashlib.md5(password.encode('utf-8')).hexdigest()

def login(email, password):
    if not email or not str(email).strip() or not password:
        return 'empty'

    hashed = hash_password(password)
    username = str(email).strip()
    try:
        user = query_db(
            "SELECT *, concat(firstname, ' ', lastname) as name FROM users "
            "WHERE (email = ? OR (email = 'admin' AND ? = 'admin@admin.com') OR (email = 'admin@admin.com' AND ? = 'admin')) "
            "AND password = ?",
            (username, username, username, hashed),
            one=True
        )
        if user:
            for key in user.keys():
                if key != 'password':
                    session[f'login_{key}'] = user[key]
            return 1
        return 2
    except Exception as e:
        current_app.logger.error(f"Login database error: {e}", exc_info=True)
        return 2

def logout():
    keys = list(session.keys())
    for key in keys:
        if key.startswith('login_'):
            session.pop(key, None)
    return 1

def get_system_settings():
    try:
        setting = query_db("SELECT * FROM system_settings LIMIT 1", one=True)
        if setting:
            return dict(setting)
    except Exception as e:
        current_app.logger.error(f"Error loading system settings: {e}", exc_info=True)
    return {
        'id': 1,
        'name': 'Courier Management System',
        'email': 'info@sample.comm',
        'contact': '+6948 8542 623',
        'address': '2102 Caldwell Road, Rochester, New York, 14608',
        'cover_img': ''
    }

def ensure_system_settings():
    if 'system' not in session or not session['system']:
        session['system'] = get_system_settings()
    return session['system']

def save_system_settings(form_data, file_storage=None):
    from services.validator import validate_email, validate_phone

    name = form_data.get('name', '').strip()
    contact = form_data.get('contact', '').strip()
    email = form_data.get('email', '').strip()
    address = form_data.get('address', '').strip()

    if not name or not contact or not email:
        return {"status": "error", "message": "System name, contact number, and email are required."}

    is_em_valid, em_msg = validate_email(email)
    if not is_em_valid:
        return {"status": "error", "message": em_msg}

    is_ph_valid, ph_msg, cleaned_phone = validate_phone(contact, field_name="System contact")
    if not is_ph_valid:
        return {"status": "error", "message": ph_msg}

    contact = cleaned_phone

    cover_filename = None
    if file_storage and file_storage.filename != '':
        sec_name = secure_filename(file_storage.filename)
        cover_filename = f"{int(time.time())}_{sec_name}"
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        file_storage.save(os.path.join(upload_folder, cover_filename))

    try:
        chk = query_db("SELECT * FROM system_settings LIMIT 1", one=True)
        if chk:
            if cover_filename:
                execute_db(
                    "UPDATE system_settings SET name = ?, contact = ?, email = ?, address = ?, cover_img = ? WHERE id = ?",
                    (name, contact, email, address, cover_filename, chk['id'])
                )
            else:
                execute_db(
                    "UPDATE system_settings SET name = ?, contact = ?, email = ?, address = ? WHERE id = ?",
                    (name, contact, email, address, chk['id'])
                )
        else:
            execute_db(
                "INSERT INTO system_settings (name, contact, email, address, cover_img) VALUES (?, ?, ?, ?, ?)",
                (name, contact, email, address, cover_filename or '')
            )

        # Refresh session system settings
        session['system'] = get_system_settings()
        return 1
    except Exception as e:
        current_app.logger.error(f"Error saving system settings: {e}", exc_info=True)
        return {"status": "error", "message": "Failed to save system settings due to a server error."}
