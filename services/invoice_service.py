import logging
from datetime import datetime
from db import query_db, execute_db

logger = logging.getLogger(__name__)

TAX_RATE = 0.05  # 5% standard logistics tax

def get_or_create_invoice(parcel_id: int, customer_id: int = 0) -> dict:
    """
    Retrieve an existing invoice for the parcel or generate a unique, idempotent invoice.
    """
    # Check if invoice already exists
    existing = query_db(
        "SELECT * FROM invoices WHERE parcel_id = ? LIMIT 1",
        (parcel_id,),
        one=True
    )
    if existing:
        return existing

    # Fetch parcel details
    parcel = query_db("SELECT * FROM parcels WHERE id = ?", (parcel_id,), one=True)
    if not parcel:
        logger.error(f"Cannot generate invoice: Parcel ID {parcel_id} not found.")
        return None

    # Calculate financial totals
    subtotal = float(parcel.get('price') or 0.0)
    tax_amount = round(subtotal * TAX_RATE, 2)
    discount_amount = 0.0
    total_amount = round(subtotal + tax_amount - discount_amount, 2)

    # Unique invoice sequence: INV-YYYYMMDD-XXXXX
    today_str = datetime.now().strftime('%Y%m%d')
    invoice_number = f"INV-{today_str}-{int(parcel_id):05d}"

    # Use customer_id from parcel if not provided
    cust_id = customer_id or parcel.get('customer_id') or 0
    payment_status = parcel.get('payment_status') or 'Unpaid'
    payment_method = parcel.get('payment_method') or 'Cash on Delivery'

    # Insert invoice
    execute_db(
        """
        INSERT INTO invoices (
            invoice_number, parcel_id, customer_id, subtotal, 
            tax_amount, discount_amount, total_amount, payment_status, payment_method, date_created
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (invoice_number, parcel_id, cust_id, subtotal, tax_amount, discount_amount, total_amount, payment_status, payment_method)
    )

    logger.info(f"Generated new invoice {invoice_number} for parcel ID {parcel_id}")

    return query_db("SELECT * FROM invoices WHERE invoice_number = ?", (invoice_number,), one=True)

def get_invoice_details(invoice_id_or_number):
    """
    Get full invoice details with joined parcel, sender, recipient, and branch info.
    """
    if str(invoice_id_or_number).isdigit():
        inv = query_db("SELECT * FROM invoices WHERE id = ?", (int(invoice_id_or_number),), one=True)
    else:
        inv = query_db("SELECT * FROM invoices WHERE invoice_number = ?", (str(invoice_id_or_number),), one=True)

    if not inv:
        return None

    parcel = query_db(
        """
        SELECT p.*, 
               fb.branch_code as from_branch_code, fb.street as from_street, fb.city as from_city,
               tb.branch_code as to_branch_code, tb.street as to_street, tb.city as to_city
        FROM parcels p
        LEFT JOIN branches fb ON p.from_branch_id = fb.id
        LEFT JOIN branches tb ON p.to_branch_id = tb.id
        WHERE p.id = ?
        """,
        (inv['parcel_id'],),
        one=True
    )

    inv['parcel'] = parcel
    return inv

def get_invoices_for_customer(customer_id: int):
    """Fetch all invoices associated with a specific customer."""
    return query_db(
        """
        SELECT i.*, p.reference_number, p.recipient_name, p.recipient_address, p.status as parcel_status
        FROM invoices i
        JOIN parcels p ON i.parcel_id = p.id
        WHERE i.customer_id = ? OR p.customer_id = ?
        ORDER BY i.id DESC
        """,
        (customer_id, customer_id)
    )

def update_invoice_payment(invoice_id: int, status: str, payment_method: str = None):
    """Update payment status on invoice and synchronise with parcel record."""
    inv = query_db("SELECT * FROM invoices WHERE id = ?", (invoice_id,), one=True)
    if not inv:
        return False

    if payment_method:
        execute_db(
            "UPDATE invoices SET payment_status = ?, payment_method = ? WHERE id = ?",
            (status, payment_method, invoice_id)
        )
        execute_db(
            "UPDATE parcels SET payment_status = ?, payment_method = ? WHERE id = ?",
            (status, payment_method, inv['parcel_id'])
        )
    else:
        execute_db("UPDATE invoices SET payment_status = ? WHERE id = ?", (status, invoice_id))
        execute_db("UPDATE parcels SET payment_status = ? WHERE id = ?", (status, inv['parcel_id']))
    return True
