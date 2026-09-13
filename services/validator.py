import re
import logging
from db import query_db

logger = logging.getLogger(__name__)

# RFC-compliant email regex ensuring no spaces, valid characters, @, domain, and 2+ char TLD
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$'
)

# Indian 10-digit mobile number regex: starts with 6, 7, 8, or 9 and followed by 9 digits
INDIAN_PHONE_REGEX = re.compile(r'^[6-9]\d{9}$')

def validate_email(email):
    """
    Validate email address format.
    Rejects: 'prasad @1234gmail.com', 'prasad@', '@gmail.com', 'prasad..test@gmail.com', spaces-only, etc.
    Accepts: 'prasad123@gmail.com', 'user.name@domain.co.in'
    Returns: (is_valid: bool, error_message: str)
    """
    if not email:
        return False, "Email address is required."
    
    email_str = str(email).strip()
    if not email_str:
        return False, "Email address cannot be empty."

    # Must not contain whitespace anywhere inside
    if re.search(r'\s', email_str):
        return False, "Email address cannot contain spaces."

    # Reject consecutive dots or leading/trailing dots
    if '..' in email_str or email_str.startswith('.') or email_str.endswith('.'):
        return False, "Please enter a valid email address."

    if '@' not in email_str:
        return False, "Please enter a valid email address."

    local_part, sep, domain_part = email_str.partition('@')
    if not local_part or not domain_part:
        return False, "Please enter a valid email address."
    if local_part.endswith('.') or local_part.startswith('.'):
        return False, "Please enter a valid email address."
    if domain_part.startswith('.') or domain_part.endswith('.'):
        return False, "Please enter a valid email address."

    if not EMAIL_REGEX.match(email_str):
        return False, "Please enter a valid email address."

    return True, ""

def validate_phone(phone, field_name="Contact number", required=True):
    """
    Validate Indian 10-digit mobile number.
    Rejects: letters, spaces-only, invalid lengths, invalid starting digits.
    Accepts: 10-digit mobile starting with 6-9, optionally with +91, 91, or 0 prefix.
    Returns: (is_valid: bool, error_message: str, cleaned_phone: str)
    """
    if not phone:
        if required:
            return False, f"{field_name} is required.", ""
        return True, "", ""

    phone_str = str(phone).strip()
    if not phone_str:
        if required:
            return False, f"{field_name} cannot be empty.", ""
        return True, "", ""

    # Reject if letters are present
    if re.search(r'[a-zA-Z]', phone_str):
        return False, f"{field_name} cannot contain letters.", ""

    # Clean allowed formatting characters: spaces, hyphens, plus, parentheses, dots
    cleaned = re.sub(r'[\s\-\+\(\)\.]', '', phone_str)

    # Reject if any non-digits remain
    if not cleaned.isdigit():
        return False, f"{field_name} contains invalid characters.", ""

    # Normalize optional Indian prefixes
    if len(cleaned) == 12 and cleaned.startswith('91'):
        cleaned = cleaned[2:]
    elif len(cleaned) == 11 and cleaned.startswith('0'):
        cleaned = cleaned[1:]

    # Must now be exactly 10 digits
    if len(cleaned) != 10:
        return False, f"{field_name} must be a valid 10-digit mobile number.", ""

    # Must start with 6, 7, 8, or 9
    if not INDIAN_PHONE_REGEX.match(cleaned):
        return False, f"{field_name} must be a valid Indian mobile number starting with 6, 7, 8, or 9.", ""

    return True, "", cleaned

def validate_positive_number(val, field_name="Value", allow_zero=False):
    """
    Validate that a numeric value is a valid positive number (> 0 by default).
    Handles strings with units (e.g. '2.5 kg', '$150.00').
    Returns: (is_valid: bool, error_message: str, float_val: float)
    """
    if val is None or str(val).strip() == '':
        return False, f"{field_name} is required.", 0.0

    raw_str = str(val).strip()
    # Strip common currency and unit suffixes
    cleaned = re.sub(r'[$€£,\s]|(kg|in|cm|m|lbs?)$', '', raw_str, flags=re.IGNORECASE).strip()
    
    try:
        num_val = float(cleaned)
    except (ValueError, TypeError):
        return False, f"{field_name} must be a valid number.", 0.0

    if not allow_zero and num_val <= 0:
        return False, f"{field_name} must be a positive number greater than zero.", 0.0

    if allow_zero and num_val < 0:
        return False, f"{field_name} cannot be negative.", 0.0

    return True, "", num_val

def validate_required_fields(data, required_fields):
    """
    Validate that all required fields are present and non-empty.
    required_fields: dict mapping field_key to friendly_label
    Returns: (is_valid: bool, error_message: str)
    """
    for field_key, friendly_label in required_fields.items():
        val = data.get(field_key)
        if val is None or str(val).strip() == '':
            return False, f"{friendly_label} is required."
    return True, ""

def check_duplicate_email(email, exclude_user_id=None):
    """
    Check if email already exists in users table.
    Returns: (is_unique: bool, error_message: str)
    """
    email_clean = str(email).strip().lower()
    try:
        if exclude_user_id:
            row = query_db(
                "SELECT COUNT(*) as cnt FROM users WHERE LOWER(email) = ? AND id != ?",
                (email_clean, exclude_user_id),
                one=True
            )
        else:
            row = query_db(
                "SELECT COUNT(*) as cnt FROM users WHERE LOWER(email) = ?",
                (email_clean,),
                one=True
            )
        if row and row['cnt'] > 0:
            return False, "Email already exists."
        return True, ""
    except Exception as e:
        logger.error(f"Error checking duplicate email: {e}")
        return False, "Database error verifying email uniqueness."

def check_duplicate_branch_code(branch_code, exclude_branch_id=None):
    """
    Check if branch_code already exists in branches table.
    Returns: (is_unique: bool, error_message: str)
    """
    code_clean = str(branch_code).strip().upper()
    try:
        if exclude_branch_id:
            row = query_db(
                "SELECT COUNT(*) as cnt FROM branches WHERE UPPER(branch_code) = ? AND id != ?",
                (code_clean, exclude_branch_id),
                one=True
            )
        else:
            row = query_db(
                "SELECT COUNT(*) as cnt FROM branches WHERE UPPER(branch_code) = ?",
                (code_clean,),
                one=True
            )
        if row and row['cnt'] > 0:
            return False, "Branch code already exists."
        return True, ""
    except Exception as e:
        logger.error(f"Error checking duplicate branch code: {e}")
        return False, "Database error verifying branch code uniqueness."

def check_duplicate_reference(reference_number, exclude_parcel_id=None):
    """
    Check if reference_number already exists in parcels table.
    Returns: (is_unique: bool, error_message: str)
    """
    ref_clean = str(reference_number).strip()
    try:
        if exclude_parcel_id:
            row = query_db(
                "SELECT COUNT(*) as cnt FROM parcels WHERE reference_number = ? AND id != ?",
                (ref_clean, exclude_parcel_id),
                one=True
            )
        else:
            row = query_db(
                "SELECT COUNT(*) as cnt FROM parcels WHERE reference_number = ?",
                (ref_clean,),
                one=True
            )
        if row and row['cnt'] > 0:
            return False, "Parcel reference already exists."
        return True, ""
    except Exception as e:
        logger.error(f"Error checking duplicate parcel reference: {e}")
        return False, "Database error verifying parcel reference uniqueness."
