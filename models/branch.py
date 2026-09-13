import random
from db import query_db, execute_db

def get_all_branches():
    return query_db(
        "SELECT *, concat(street, ', ', city, ', ', state, ', ', zip_code, ', ', country) as address "
        "FROM branches ORDER BY street ASC, city ASC, state ASC"
    )

def get_branch_by_id(branch_id):
    return query_db("SELECT * FROM branches WHERE id = ?", (branch_id,), one=True)

def generate_branch_code():
    while True:
        code = f"{random.randint(0, 99999999):08d}"
        chk = query_db("SELECT COUNT(*) as cnt FROM branches WHERE branch_code = ?", (code,), one=True)
        if chk['cnt'] == 0:
            return code

def save_branch(data):
    from services.validator import validate_phone, check_duplicate_branch_code

    branch_id = data.get('id')
    street = data.get('street', '').strip()
    city = data.get('city', '').strip()
    state = data.get('state', '').strip()
    zip_code = data.get('zip_code', '').strip()
    country = data.get('country', '').strip()
    contact = data.get('contact', '').strip()
    bcode_input = data.get('branch_code', '').strip()

    # Validate required fields
    if not street:
        return (False, "Street/Building is required.")
    if not city:
        return (False, "City is required.")
    if not state:
        return (False, "State is required.")
    if not zip_code:
        return (False, "Zip Code/Postal Code is required.")
    if not country:
        return (False, "Country is required.")
    if not contact:
        return (False, "Contact number is required.")

    # Validate contact number (Indian 10-digit mobile)
    is_ph, ph_err, clean_phone = validate_phone(contact, field_name="Contact number", required=True)
    if not is_ph:
        return (False, ph_err)
    contact = clean_phone

    # Handle branch code and duplicate detection
    if bcode_input:
        is_unique, dup_err = check_duplicate_branch_code(bcode_input, exclude_branch_id=branch_id)
        if not is_unique:
            return (False, "Branch code already exists.")
        bcode = bcode_input
    elif not branch_id:
        bcode = generate_branch_code()
    else:
        bcode = None

    try:
        if not branch_id:
            execute_db(
                "INSERT INTO branches (branch_code, street, city, state, zip_code, country, contact) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (bcode, street, city, state, zip_code, country, contact)
            )
        else:
            if bcode:
                execute_db(
                    "UPDATE branches SET branch_code = ?, street = ?, city = ?, state = ?, zip_code = ?, country = ?, contact = ? "
                    "WHERE id = ?",
                    (bcode, street, city, state, zip_code, country, contact, branch_id)
                )
            else:
                execute_db(
                    "UPDATE branches SET street = ?, city = ?, state = ?, zip_code = ?, country = ?, contact = ? "
                    "WHERE id = ?",
                    (street, city, state, zip_code, country, contact, branch_id)
                )
        return (True, 1)
    except Exception as e:
        return (False, f"Failed to save branch: {str(e)}")

def delete_branch(branch_id):
    try:
        execute_db("DELETE FROM branches WHERE id = ?", (branch_id,))
        return 1
    except Exception as e:
        return 0
