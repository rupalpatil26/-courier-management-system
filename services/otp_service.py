import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from db import query_db, execute_db

logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 60
MAX_OTP_ATTEMPTS = 3

def _hash_otp(otp: str, parcel_id: int) -> str:
    """Secure SHA-256 hash salted with parcel ID."""
    token = f"{parcel_id}:{otp.strip()}:cms_salt_2026"
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def create_delivery_otp(parcel_id: int) -> dict:
    """
    Generate and store a secure 6-digit OTP for parcel delivery.
    Enforces cooldown and invalidates older unexpired tokens.
    """
    now = datetime.now()

    # Check for recent active OTP (cooldown check)
    recent = query_db(
        """
        SELECT * FROM delivery_otps 
        WHERE parcel_id = ? AND is_used = 0 
        ORDER BY id DESC LIMIT 1
        """,
        (parcel_id,),
        one=True
    )

    if recent:
        created_at = recent.get('created_at')
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace('Z', ''))
            except Exception:
                try:
                    created_at = datetime.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S')
                except Exception:
                    created_at = None
        
        if created_at:
            elapsed = (now - created_at).total_seconds()
            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                remaining = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                return {
                    'success': False,
                    'message': f"Please wait {remaining} seconds before requesting a new OTP.",
                    'cooldown': remaining
                }

    # Invalidate previous unused OTPs
    execute_db(
        "UPDATE delivery_otps SET is_used = 2 WHERE parcel_id = ? AND is_used = 0",
        (parcel_id,)
    )

    # Generate 6-digit numeric OTP
    raw_otp = "".join(secrets.choice("0123456789") for _ in range(6))
    otp_hash = _hash_otp(raw_otp, parcel_id)
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    expires_str = expires_at.strftime('%Y-%m-%d %H:%M:%S')

    created_str = now.strftime('%Y-%m-%d %H:%M:%S')

    execute_db(
        """
        INSERT INTO delivery_otps (parcel_id, otp_hash, created_at, expires_at, is_used, attempts)
        VALUES (?, ?, ?, ?, 0, 0)
        """,
        (parcel_id, otp_hash, created_str, expires_str)
    )

    logger.info(f"Generated delivery OTP for parcel ID {parcel_id}, expires at {expires_str}")

    return {
        'success': True,
        'otp': raw_otp,
        'expires_at': expires_str,
        'expiry_minutes': OTP_EXPIRY_MINUTES
    }

def verify_delivery_otp(parcel_id: int, entered_otp: str) -> dict:
    """
    Validate entered OTP against stored hash.
    Checks expiration, attempt counts, and marks OTP as used upon success.
    """
    if not entered_otp or not str(entered_otp).strip():
        return {'success': False, 'message': 'Please enter the 6-digit OTP.'}

    now = datetime.now()
    otp_record = query_db(
        """
        SELECT * FROM delivery_otps 
        WHERE parcel_id = ? AND is_used = 0 
        ORDER BY id DESC LIMIT 1
        """,
        (parcel_id,),
        one=True
    )

    if not otp_record:
        return {'success': False, 'message': 'No active OTP found. Please request a new delivery OTP.'}

    # Check attempt limit
    attempts = int(otp_record.get('attempts', 0))
    if attempts >= MAX_OTP_ATTEMPTS:
        execute_db("UPDATE delivery_otps SET is_used = 3 WHERE id = ?", (otp_record['id'],))
        return {'success': False, 'message': 'Too many failed attempts. Please generate a new OTP.'}

    # Check expiration
    expires_at = otp_record.get('expires_at')
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace('Z', ''))
        except Exception:
            try:
                expires_at = datetime.strptime(expires_at[:19], '%Y-%m-%d %H:%M:%S')
            except Exception:
                expires_at = None

    if expires_at and now > expires_at:
        execute_db("UPDATE delivery_otps SET is_used = 2 WHERE id = ?", (otp_record['id'],))
        return {'success': False, 'message': 'OTP has expired. Please request a new one.'}

    # Verify hash
    entered_hash = _hash_otp(entered_otp, parcel_id)
    if entered_hash == otp_record['otp_hash']:
        # Success: mark used
        execute_db("UPDATE delivery_otps SET is_used = 1 WHERE id = ?", (otp_record['id'],))
        # Update parcel otp_verified flag
        execute_db("UPDATE parcels SET otp_verified = 1 WHERE id = ?", (parcel_id,))
        logger.info(f"OTP verified successfully for parcel ID {parcel_id}")
        return {'success': True, 'message': 'Delivery OTP verified successfully!'}
    else:
        new_attempts = attempts + 1
        execute_db("UPDATE delivery_otps SET attempts = ? WHERE id = ?", (new_attempts, otp_record['id']))
        remaining = MAX_OTP_ATTEMPTS - new_attempts
        if remaining <= 0:
            execute_db("UPDATE delivery_otps SET is_used = 3 WHERE id = ?", (otp_record['id'],))
            return {'success': False, 'message': 'Invalid OTP. Maximum attempts reached. Please generate a new OTP.'}
        return {'success': False, 'message': f'Invalid OTP. {remaining} attempt{"s" if remaining > 1 else ""} remaining.'}
