import os
import time
from flask import session, current_app
from werkzeug.utils import secure_filename
from db import query_db, execute_db
from models.auth import hash_password

def get_all_users():
    return query_db(
        "SELECT *, concat(firstname, ' ', lastname) as name "
        "FROM users ORDER BY concat(firstname, ' ', lastname) ASC"
    )

def get_staff_users():
    return query_db(
        "SELECT u.*, concat(u.firstname, ' ', u.lastname) as name, "
        "concat(b.street, ', ', b.city, ', ', b.state, ', ', b.zip_code, ', ', b.country) as baddress "
        "FROM users u LEFT JOIN branches b ON b.id = u.branch_id "
        "WHERE u.type = 2 ORDER BY concat(u.firstname, ' ', u.lastname) ASC"
    )

def get_customers():
    return query_db(
        "SELECT *, concat(firstname, ' ', lastname) as name "
        "FROM users WHERE type = 3 ORDER BY concat(firstname, ' ', lastname) ASC"
    )

def get_user_by_id(user_id):
    user = query_db(
        "SELECT u.*, concat(u.firstname, ' ', u.lastname) as name, "
        "concat(b.street, ', ', b.city, ', ', b.state, ', ', b.zip_code, ', ', b.country) as baddress "
        "FROM users u LEFT JOIN branches b ON b.id = u.branch_id "
        "WHERE u.id = ?",
        (user_id,),
        one=True
    )
    return dict(user) if user else None

def register_customer(firstname, lastname, email, password, phone='', address=''):
    """Register a new customer (type = 3). Returns (status_code, user_id or error_msg)."""
    from services.validator import validate_email, validate_phone, check_duplicate_email

    firstname = str(firstname or '').strip()
    lastname = str(lastname or '').strip()
    email = str(email or '').strip().lower()
    password = str(password or '').strip()
    phone = str(phone or '').strip()
    address = str(address or '').strip()

    if not firstname or not lastname:
        return (0, "First name and last name are required.")
    if not email:
        return (0, "Email address is required.")
    if not password:
        return (0, "Password is required.")
    if len(password) < 6:
        return (0, "Password must be at least 6 characters long.")

    # Email format validation
    is_em_valid, em_err = validate_email(email)
    if not is_em_valid:
        return (0, em_err)

    # Phone validation (optional for customer registration)
    if phone:
        is_ph_valid, ph_err, clean_phone = validate_phone(phone, field_name="Phone number", required=False)
        if not is_ph_valid:
            return (0, ph_err)
        phone = clean_phone

    # Duplicate email check
    is_unique, dup_err = check_duplicate_email(email)
    if not is_unique:
        return (2, "Email already exists.")

    try:
        hashed = hash_password(password)
        user_id = execute_db(
            """
            INSERT INTO users (firstname, lastname, email, password, type, branch_id, phone, address)
            VALUES (?, ?, ?, ?, 3, 0, ?, ?)
            """,
            (firstname, lastname, email, hashed, phone, address)
        )
        return (1, user_id)
    except Exception as e:
        return (0, f"Registration failed due to a server error: {str(e)}")

def save_user(form_data, file_storage=None):
    from services.validator import validate_email, validate_phone, check_duplicate_email

    user_id = form_data.get('id')
    firstname = form_data.get('firstname', '').strip()
    lastname = form_data.get('lastname', '').strip()
    email = form_data.get('email', '').strip()
    password = form_data.get('password', '').strip()
    u_type = int(form_data.get('type', 2))
    branch_id = form_data.get('branch_id', 0)
    phone = form_data.get('phone', '').strip()
    address = form_data.get('address', '').strip()

    if not firstname or not lastname:
        return (False, "First name and last name are required.")
    if not email:
        return (False, "Email address is required.")
    if not user_id and not password:
        return (False, "Password is required for new accounts.")

    # Email format validation
    is_em_valid, em_err = validate_email(email)
    if not is_em_valid:
        return (False, em_err)

    # Duplicate email check
    is_unique, dup_err = check_duplicate_email(email, exclude_user_id=user_id)
    if not is_unique:
        return (False, "Email already exists.", 2)

    # Phone validation
    if phone:
        is_ph_valid, ph_err, clean_phone = validate_phone(phone, field_name="Phone number", required=False)
        if not is_ph_valid:
            return (False, ph_err)
        phone = clean_phone

    # For staff users (type 2), branch is required
    if u_type == 2:
        try:
            b_id = int(branch_id or 0)
            if b_id <= 0:
                return (False, "Please select a branch for staff.")
            branch_id = b_id
        except (ValueError, TypeError):
            return (False, "Invalid branch selected.")

    avatar_filename = None
    if file_storage and file_storage.filename != '':
        sec_name = secure_filename(file_storage.filename)
        avatar_filename = f"{int(time.time())}_{sec_name}"
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'assets/uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_storage.save(os.path.join(upload_folder, avatar_filename))

    try:
        if not user_id:
            hashed = hash_password(password) if password else ''
            execute_db(
                "INSERT INTO users (firstname, lastname, email, password, type, branch_id, phone, address) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (firstname, lastname, email, hashed, u_type, branch_id, phone, address)
            )
        else:
            if password:
                hashed = hash_password(password)
                execute_db(
                    "UPDATE users SET firstname = ?, lastname = ?, email = ?, password = ?, type = ?, branch_id = ?, phone = ?, address = ? "
                    "WHERE id = ?",
                    (firstname, lastname, email, hashed, u_type, branch_id, phone, address, user_id)
                )
            else:
                execute_db(
                    "UPDATE users SET firstname = ?, lastname = ?, email = ?, type = ?, branch_id = ?, phone = ?, address = ? "
                    "WHERE id = ?",
                    (firstname, lastname, email, u_type, branch_id, phone, address, user_id)
                )
        return (True, 1)
    except Exception as e:
        return (False, f"Failed to save user: {str(e)}")

def update_user_profile(form_data, file_storage=None):
    from services.validator import validate_email, validate_phone, check_duplicate_email

    user_id = form_data.get('id') or session.get('login_id')
    firstname = form_data.get('firstname', '').strip()
    lastname = form_data.get('lastname', '').strip()
    email = form_data.get('email', '').strip()
    password = form_data.get('password', '').strip()
    phone = form_data.get('phone', '').strip()
    address = form_data.get('address', '').strip()

    if not firstname or not lastname:
        return (False, "First name and last name are required.")
    if not email:
        return (False, "Email address is required.")

    is_em_valid, em_err = validate_email(email)
    if not is_em_valid:
        return (False, em_err)

    is_unique, dup_err = check_duplicate_email(email, exclude_user_id=user_id)
    if not is_unique:
        return (False, "Email already exists.", 2)

    if phone:
        is_ph_valid, ph_err, clean_phone = validate_phone(phone, field_name="Phone number", required=False)
        if not is_ph_valid:
            return (False, ph_err)
        phone = clean_phone

    try:
        if password:
            hashed = hash_password(password)
            execute_db(
                "UPDATE users SET firstname = ?, lastname = ?, email = ?, password = ?, phone = ?, address = ? WHERE id = ?",
                (firstname, lastname, email, hashed, phone, address, user_id)
            )
        else:
            execute_db(
                "UPDATE users SET firstname = ?, lastname = ?, email = ?, phone = ?, address = ? WHERE id = ?",
                (firstname, lastname, email, phone, address, user_id)
            )

        # Update session
        session['login_firstname'] = firstname
        session['login_lastname'] = lastname
        session['login_email'] = email
        session['login_name'] = f"{firstname} {lastname}".strip()
        session['login_phone'] = phone
        session['login_address'] = address
        return (True, 1)
    except Exception as e:
        return (False, f"Failed to update profile: {str(e)}")

def delete_user(user_id):
    try:
        execute_db("DELETE FROM users WHERE id = ?", (user_id,))
        return 1
    except Exception as e:
        return 0
