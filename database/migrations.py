import logging
from db import query_db, execute_db, get_db_type

logger = logging.getLogger(__name__)

def run_migrations():
    """Safely apply non-destructive schema migrations for SQLite and MySQL."""
    db_type = get_db_type()
    logger.info(f"Running database migrations for {db_type}...")

    # 1. Helper to check existing columns
    def get_existing_columns(table_name):
        try:
            if db_type == 'mysql':
                rows = query_db(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    (table_name,)
                )
                return [r['column_name'].lower() for r in rows] if rows else []
            else:
                rows = query_db(f"PRAGMA table_info({table_name});")
                return [r['name'].lower() for r in rows] if rows else []
        except Exception as e:
            logger.warning(f"Could not read columns for {table_name}: {e}")
            return []

    # 2. Add columns to `users`
    user_cols = get_existing_columns('users')
    if user_cols:
        if 'phone' not in user_cols:
            execute_db("ALTER TABLE users ADD COLUMN phone VARCHAR(50) DEFAULT ''")
        if 'address' not in user_cols:
            execute_db("ALTER TABLE users ADD COLUMN address TEXT DEFAULT ''")

    # 3. Add columns to `parcels`
    parcel_cols = get_existing_columns('parcels')
    if parcel_cols:
        if 'customer_id' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN customer_id INT DEFAULT 0")
        if 'sender_email' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN sender_email VARCHAR(200) DEFAULT ''")
        if 'recipient_email' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN recipient_email VARCHAR(200) DEFAULT ''")
        if 'assigned_staff_id' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN assigned_staff_id INT DEFAULT 0")
        if 'payment_method' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN payment_method VARCHAR(50) DEFAULT 'Cash on Delivery'")
        if 'payment_status' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN payment_status VARCHAR(50) DEFAULT 'Unpaid'")
        if 'delivery_notes' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN delivery_notes TEXT DEFAULT ''")
        if 'delivery_time' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN delivery_time DATETIME DEFAULT NULL")
        if 'otp_verified' not in parcel_cols:
            execute_db("ALTER TABLE parcels ADD COLUMN otp_verified INT DEFAULT 0")

    # 4. Add columns to `parcel_tracks`
    track_cols = get_existing_columns('parcel_tracks')
    if track_cols:
        if 'staff_id' not in track_cols:
            execute_db("ALTER TABLE parcel_tracks ADD COLUMN staff_id INT DEFAULT 0")
        if 'notes' not in track_cols:
            execute_db("ALTER TABLE parcel_tracks ADD COLUMN notes TEXT DEFAULT ''")

    # 5. Create new tables if not exist
    auto_inc = "AUTO_INCREMENT" if db_type == "mysql" else "AUTOINCREMENT"

    # delivery_otps table
    execute_db(f"""
        CREATE TABLE IF NOT EXISTS delivery_otps (
            id INTEGER PRIMARY KEY {auto_inc},
            parcel_id INT NOT NULL,
            otp_hash VARCHAR(255) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            is_used INT DEFAULT 0,
            attempts INT DEFAULT 0
        )
    """)

    # invoices table
    execute_db(f"""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY {auto_inc},
            invoice_number VARCHAR(50) UNIQUE NOT NULL,
            parcel_id INT NOT NULL,
            customer_id INT DEFAULT 0,
            subtotal REAL DEFAULT 0.0,
            tax_amount REAL DEFAULT 0.0,
            discount_amount REAL DEFAULT 0.0,
            total_amount REAL DEFAULT 0.0,
            payment_status VARCHAR(50) DEFAULT 'Unpaid',
            payment_method VARCHAR(50) DEFAULT 'Cash',
            date_created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # parcel_feedback table
    execute_db(f"""
        CREATE TABLE IF NOT EXISTS parcel_feedback (
            id INTEGER PRIMARY KEY {auto_inc},
            parcel_id INT NOT NULL,
            customer_id INT NOT NULL,
            rating INT NOT NULL,
            comments TEXT DEFAULT '',
            date_created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # notifications table
    execute_db(f"""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY {auto_inc},
            user_id INT NOT NULL,
            title VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            is_read INT DEFAULT 0,
            date_created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    logger.info("Database migrations applied successfully.")
