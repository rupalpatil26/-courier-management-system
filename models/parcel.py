import random
import logging
from datetime import datetime
from db import query_db, execute_db
from services.invoice_service import get_or_create_invoice
from services.otp_service import create_delivery_otp
from services.email_service import (
    notify_parcel_created,
    notify_out_for_delivery,
    notify_parcel_delivered,
    notify_delivery_failed
)

logger = logging.getLogger(__name__)

STATUS_LIST = [
    "Item Accepted by Courier",       # 0
    "Collected",                      # 1
    "Shipped",                        # 2
    "In-Transit",                     # 3
    "Arrived At Destination",         # 4
    "Out for Delivery",               # 5
    "Ready to Pickup",                # 6
    "Delivered",                      # 7
    "Picked-up",                      # 8
    "Unsuccessfull Delivery Attempt"  # 9
]

def format_datetime(dt_val):
    if not dt_val:
        return ""
    if isinstance(dt_val, str):
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                dt_val = datetime.strptime(dt_val.strip(), fmt)
                break
            except ValueError:
                pass
    if isinstance(dt_val, datetime):
        return dt_val.strftime("%b %d, %Y %I:%M %p")
    return str(dt_val)

def generate_reference_number():
    while True:
        ref = f"{random.randint(0, 999999999999):012d}"
        chk = query_db("SELECT COUNT(*) as cnt FROM parcels WHERE reference_number = ?", (ref,), one=True)
        if chk['cnt'] == 0:
            return ref

def get_parcels(status=None, user_type=1, branch_id=None):
    where_clauses = []
    params = []

    if status is not None and str(status).strip() != '' and str(status) != 'all':
        where_clauses.append("status = ?")
        params.append(int(status))

    if user_type != 1 and branch_id is not None and str(branch_id) != '0':
        where_clauses.append("(from_branch_id = ? OR to_branch_id = ?)")
        params.extend([str(branch_id), str(branch_id)])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query = f"SELECT * FROM parcels {where_sql} ORDER BY unix_timestamp(date_created) DESC"
    return query_db(query, tuple(params))

def get_parcel_by_id(parcel_id):
    parcel = query_db("SELECT * FROM parcels WHERE id = ?", (parcel_id,), one=True)
    if not parcel:
        return None
    parcel = dict(parcel)

    to_id = parcel.get('to_branch_id', '-1') or '-1'
    from_id = parcel.get('from_branch_id', '-1') or '-1'
    branches = query_db(
        "SELECT id, concat(street, ', ', city, ', ', state, ', ', zip_code, ', ', country) as address "
        "FROM branches WHERE id IN (?, ?)",
        (to_id, from_id)
    )
    branch_map = {str(b['id']): b['address'] for b in branches}
    parcel['from_branch_address'] = branch_map.get(str(from_id), '')
    parcel['to_branch_address'] = branch_map.get(str(to_id), '')

    # Fetch assigned staff name if present
    if parcel.get('assigned_staff_id'):
        staff = query_db(
            "SELECT concat(firstname, ' ', lastname) as name, phone FROM users WHERE id = ?",
            (parcel['assigned_staff_id'],),
            one=True
        )
        if staff:
            parcel['assigned_staff_name'] = staff['name']
            parcel['assigned_staff_phone'] = staff.get('phone', '')

    # Fetch customer feedback if present
    feedback = query_db("SELECT * FROM parcel_feedback WHERE parcel_id = ?", (parcel_id,), one=True)
    parcel['feedback'] = dict(feedback) if feedback else None

    return parcel

def get_parcel_by_reference(ref):
    if not ref:
        return None
    parcel = query_db("SELECT * FROM parcels WHERE reference_number = ?", (str(ref).strip(),), one=True)
    if parcel:
        return get_parcel_by_id(parcel['id'])
    return None

def get_parcels_for_customer(customer_id, status=None):
    where_clauses = ["customer_id = ?"]
    params = [customer_id]

    if status is not None and str(status).strip() != '' and str(status) != 'all':
        where_clauses.append("status = ?")
        params.append(int(status))

    sql = f"SELECT * FROM parcels WHERE {' AND '.join(where_clauses)} ORDER BY unix_timestamp(date_created) DESC"
    return query_db(sql, tuple(params))

def get_parcels_for_staff(staff_id, view_filter='all', status=None):
    """
    Get deliveries assigned to staff with optional filtering:
    'all', 'today', 'pending', 'completed', 'failed'.
    """
    where_clauses = ["assigned_staff_id = ?"]
    params = [staff_id]

    if view_filter == 'today':
        where_clauses.append("date(date_created) = date('now')")
    elif view_filter == 'pending':
        where_clauses.append("status NOT IN (7, 9)")
    elif view_filter == 'completed':
        where_clauses.append("status = 7")
    elif view_filter == 'failed':
        where_clauses.append("status = 9")

    if status is not None and str(status).strip() != '' and str(status) != 'all':
        where_clauses.append("status = ?")
        params.append(int(status))

    sql = f"SELECT * FROM parcels WHERE {' AND '.join(where_clauses)} ORDER BY unix_timestamp(date_created) DESC"
    return query_db(sql, tuple(params))

def save_parcel(form_data):
    from services.validator import (
        validate_email, validate_phone,
        validate_positive_number, check_duplicate_reference
    )

    parcel_id = form_data.get('id')
    sender_name = str(form_data.get('sender_name') or '').strip()
    sender_address = str(form_data.get('sender_address') or '').strip()
    sender_contact = str(form_data.get('sender_contact') or '').strip()
    sender_email = str(form_data.get('sender_email') or '').strip()
    recipient_name = str(form_data.get('recipient_name') or '').strip()
    recipient_address = str(form_data.get('recipient_address') or '').strip()
    recipient_contact = str(form_data.get('recipient_contact') or '').strip()
    recipient_email = str(form_data.get('recipient_email') or '').strip()
    p_type = str(form_data.get('type') or '2').strip()
    from_branch_id = str(form_data.get('from_branch_id') or '').strip()
    to_branch_id = str(form_data.get('to_branch_id') or '').strip()
    customer_id = int(form_data.get('customer_id', 0) or 0)
    assigned_staff_id = int(form_data.get('assigned_staff_id', 0) or 0)
    payment_method = str(form_data.get('payment_method') or 'Cash on Delivery').strip()
    payment_status = str(form_data.get('payment_status') or 'Unpaid').strip()
    delivery_notes = str(form_data.get('delivery_notes') or '').strip()
    custom_ref = str(form_data.get('reference_number') or '').strip()

    # 1. Validate Required Names & Addresses
    if not sender_name:
        return (False, "Sender name is required.")
    if not sender_address:
        return (False, "Sender address is required.")
    if not recipient_name:
        return (False, "Recipient name is required.")
    if not recipient_address:
        return (False, "Recipient address is required.")

    # 2. Validate Contact Numbers (Indian 10-digit mobile)
    is_s_ph, s_ph_err, clean_s_phone = validate_phone(sender_contact, field_name="Sender contact number", required=True)
    if not is_s_ph:
        return (False, s_ph_err)
    sender_contact = clean_s_phone

    is_r_ph, r_ph_err, clean_r_phone = validate_phone(recipient_contact, field_name="Recipient contact number", required=True)
    if not is_r_ph:
        return (False, r_ph_err)
    recipient_contact = clean_r_phone

    # 3. Validate Emails (if provided)
    if sender_email:
        is_s_em, s_em_err = validate_email(sender_email)
        if not is_s_em:
            return (False, f"Sender email error: {s_em_err}")
    if recipient_email:
        is_r_em, r_em_err = validate_email(recipient_email)
        if not is_r_em:
            return (False, f"Recipient email error: {r_em_err}")

    # 4. Validate Branch Routing
    if not from_branch_id:
        return (False, "Please select an origin / processed branch.")
    if p_type == '2' and not to_branch_id:
        return (False, "Please select a destination pickup branch.")

    # 5. Validate Reference Number Uniqueness (if custom reference is provided)
    if custom_ref:
        is_uniq_ref, ref_err = check_duplicate_reference(custom_ref, exclude_parcel_id=parcel_id)
        if not is_uniq_ref:
            return (False, "Parcel reference already exists.")

    # 6. Validate Package Dimensions, Weights, and Prices (> 0)
    weights = form_data.getlist('weight[]') or form_data.getlist('weight') or [form_data.get('weight', '')]
    heights = form_data.getlist('height[]') or form_data.getlist('height') or [form_data.get('height', '')]
    widths = form_data.getlist('width[]') or form_data.getlist('width') or [form_data.get('width', '')]
    lengths = form_data.getlist('length[]') or form_data.getlist('length') or [form_data.get('length', '')]
    prices = form_data.getlist('price[]') or form_data.getlist('price') or [form_data.get('price', '')]

    if not weights or not any(weights):
        return (False, "Please add at least one parcel item.")

    parsed_weights = []
    parsed_heights = []
    parsed_widths = []
    parsed_lengths = []
    parsed_prices = []

    for idx in range(len(weights)):
        w_raw = weights[idx] if idx < len(weights) else ''
        h_raw = heights[idx] if idx < len(heights) else ''
        wd_raw = widths[idx] if idx < len(widths) else ''
        l_raw = lengths[idx] if idx < len(lengths) else ''
        p_raw = prices[idx] if idx < len(prices) else ''

        # Validate Weight (> 0)
        ok_w, msg_w, val_w = validate_positive_number(w_raw, field_name=f"Item {idx+1} weight")
        if not ok_w:
            return (False, msg_w)
        parsed_weights.append(f"{val_w:g}")

        # Validate Height (> 0)
        ok_h, msg_h, val_h = validate_positive_number(h_raw, field_name=f"Item {idx+1} height")
        if not ok_h:
            return (False, msg_h)
        parsed_heights.append(f"{val_h:g}")

        # Validate Width (> 0)
        ok_wd, msg_wd, val_wd = validate_positive_number(wd_raw, field_name=f"Item {idx+1} width")
        if not ok_wd:
            return (False, msg_wd)
        parsed_widths.append(f"{val_wd:g}")

        # Validate Length (> 0)
        ok_l, msg_l, val_l = validate_positive_number(l_raw, field_name=f"Item {idx+1} length")
        if not ok_l:
            return (False, msg_l)
        parsed_lengths.append(f"{val_l:g}")

        # Validate Price (> 0)
        ok_p, msg_p, val_p = validate_positive_number(p_raw, field_name=f"Item {idx+1} price")
        if not ok_p:
            return (False, msg_p)
        parsed_prices.append(val_p)

    try:
        if parcel_id:
            # Edit existing parcel
            ref_to_save = custom_ref if custom_ref else None
            execute_db(
                """
                UPDATE parcels SET 
                    sender_name = ?, sender_address = ?, sender_contact = ?, sender_email = ?,
                    recipient_name = ?, recipient_address = ?, recipient_contact = ?, recipient_email = ?,
                    type = ?, from_branch_id = ?, to_branch_id = ?, weight = ?, height = ?, width = ?, 
                    length = ?, price = ?, customer_id = ?, assigned_staff_id = ?, 
                    payment_method = ?, payment_status = ?, delivery_notes = ?
                    """ + (", reference_number = ?" if ref_to_save else "") + """
                WHERE id = ?
                """,
                tuple([
                    sender_name, sender_address, sender_contact, sender_email,
                    recipient_name, recipient_address, recipient_contact, recipient_email,
                    p_type, from_branch_id, to_branch_id,
                    parsed_weights[0], parsed_heights[0], parsed_widths[0], parsed_lengths[0],
                    parsed_prices[0], customer_id, assigned_staff_id,
                    payment_method, payment_status, delivery_notes
                ] + ([ref_to_save] if ref_to_save else []) + [parcel_id])
            )
            # Ensure invoice exists
            get_or_create_invoice(int(parcel_id), customer_id)
            return (True, 1)

        # Adding new parcel(s)
        created_ids = []
        for i in range(len(parsed_prices)):
            ref = custom_ref if (custom_ref and len(parsed_prices) == 1) else generate_reference_number()
            w = parsed_weights[i]
            h = parsed_heights[i]
            wd = parsed_widths[i]
            l = parsed_lengths[i]
            price_val = parsed_prices[i]

            new_id = execute_db(
                """
                INSERT INTO parcels (
                    reference_number, sender_name, sender_address, sender_contact, sender_email,
                    recipient_name, recipient_address, recipient_contact, recipient_email,
                    type, from_branch_id, to_branch_id, weight, height, width, length, price,
                    status, customer_id, assigned_staff_id, payment_method, payment_status, delivery_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (ref, sender_name, sender_address, sender_contact, sender_email,
                 recipient_name, recipient_address, recipient_contact, recipient_email,
                 p_type, from_branch_id, to_branch_id, w, h, wd, l, price_val,
                 customer_id, assigned_staff_id, payment_method, payment_status, delivery_notes)
            )

            created_ids.append(new_id)

            # 1. Automatically generate invoice (Feature 5)
            try:
                get_or_create_invoice(new_id, customer_id)
            except Exception as inv_err:
                logger.warning(f"Error auto-generating invoice for parcel {new_id}: {inv_err}")

            # 2. Dispatch parcel created email notification (Feature 6)
            try:
                parcel_data = get_parcel_by_id(new_id)
                tracking_url = f"/track?ref_no={ref}"
                notify_parcel_created(parcel_data, tracking_url)
            except Exception as mail_err:
                logger.warning(f"Error sending creation email for parcel {new_id}: {mail_err}")

        return (True, 1)
    except Exception as e:
        logger.error(f"Error saving parcel: {e}", exc_info=True)
        return (False, f"Failed to save parcel: {str(e)}")

def update_parcel_status(parcel_id, status, staff_id=0, notes='', bypass_otp=None):
    """
    Update parcel status with full lifecycle notifications and OTP enforcement.
    Delivery staff (staff_id > 0) strictly require OTP verification before marking status 7 (Delivered).
    Admin / system updates (staff_id == 0 or explicit bypass) allow status override.
    """
    try:
        status = int(status)
        if status < 0 or status >= len(STATUS_LIST):
            return 0
    except (ValueError, TypeError):
        return 0

    parcel = get_parcel_by_id(parcel_id)
    if not parcel:
        return 0

    if bypass_otp is None:
        bypass_otp = (staff_id == 0)

    tracking_url = f"/track?ref_no={parcel['reference_number']}"

    # OTP Delivery Verification Rule:
    # Status 7 = Delivered. Requires OTP verification for delivery staff!
    if status == 7:
        if not bypass_otp and not parcel.get('otp_verified'):
            return -1  # Denied: OTP not verified!

        execute_db(
            """
            UPDATE parcels SET status = 7, delivery_time = CURRENT_TIMESTAMP, delivery_notes = ? 
            WHERE id = ?
            """,
            (notes or parcel.get('delivery_notes', ''), parcel_id)
        )
        execute_db(
            "INSERT INTO parcel_tracks (parcel_id, status, staff_id, notes) VALUES (?, 7, ?, ?)",
            (parcel_id, staff_id, notes or 'Delivered to recipient (OTP Verified)')
        )

        # Notify parties
        try:
            notify_parcel_delivered(parcel, tracking_url)
        except Exception as e:
            logger.warning(f"Could not dispatch delivered email: {e}")
        return 1

    elif status == 5:
        # Status 5 = Out for Delivery: Generate OTP and email it to recipient
        otp_res = create_delivery_otp(parcel_id)
        execute_db(
            "UPDATE parcels SET status = 5, delivery_notes = ? WHERE id = ?",
            (notes or parcel.get('delivery_notes', ''), parcel_id)
        )
        execute_db(
            "INSERT INTO parcel_tracks (parcel_id, status, staff_id, notes) VALUES (?, 5, ?, ?)",
            (parcel_id, staff_id, notes or 'Package dispatched out for delivery')
        )

        if otp_res.get('success'):
            try:
                staff_name = ''
                if staff_id:
                    st = query_db("SELECT concat(firstname, ' ', lastname) as name FROM users WHERE id = ?", (staff_id,), one=True)
                    staff_name = st['name'] if st else ''
                notify_out_for_delivery(parcel, otp_res['otp'], tracking_url, staff_name)
            except Exception as e:
                logger.warning(f"Could not dispatch OTP email: {e}")
        return 1

    elif status == 9:
        # Status 9 = Unsuccessful Delivery Attempt
        execute_db(
            "UPDATE parcels SET status = 9, delivery_notes = ? WHERE id = ?",
            (notes or 'Delivery attempt unsuccessful', parcel_id)
        )
        execute_db(
            "INSERT INTO parcel_tracks (parcel_id, status, staff_id, notes) VALUES (?, 9, ?, ?)",
            (parcel_id, staff_id, notes or 'Delivery attempt unsuccessful')
        )
        try:
            notify_delivery_failed(parcel, tracking_url, notes)
        except Exception as e:
            logger.warning(f"Could not dispatch failure notice: {e}")
        return 1

    else:
        # Other status transition (0, 1, 2, 3, 4, 6, 8)
        execute_db("UPDATE parcels SET status = ? WHERE id = ?", (status, parcel_id))
        execute_db(
            "INSERT INTO parcel_tracks (parcel_id, status, staff_id, notes) VALUES (?, ?, ?, ?)",
            (parcel_id, status, staff_id, notes)
        )
        return 1

def assign_parcel_staff(parcel_id, staff_id):
    """Assign a delivery staff member to a parcel."""
    execute_db("UPDATE parcels SET assigned_staff_id = ? WHERE id = ?", (staff_id, parcel_id))
    return 1

def delete_parcel(parcel_id):
    execute_db("DELETE FROM parcels WHERE id = ?", (parcel_id,))
    execute_db("DELETE FROM parcel_tracks WHERE parcel_id = ?", (parcel_id,))
    execute_db("DELETE FROM delivery_otps WHERE parcel_id = ?", (parcel_id,))
    execute_db("DELETE FROM invoices WHERE parcel_id = ?", (parcel_id,))
    execute_db("DELETE FROM parcel_feedback WHERE parcel_id = ?", (parcel_id,))
    return 1

def get_parcel_history(reference_number):
    parcel = query_db("SELECT * FROM parcels WHERE reference_number = ?", (reference_number.strip(),), one=True)
    if not parcel:
        return 2

    history = [
        {
            'status': 'Item Accepted by Courier',
            'date_created': format_datetime(parcel['date_created']),
            'notes': 'Package accepted into courier system'
        }
    ]

    tracks = query_db(
        "SELECT * FROM parcel_tracks WHERE parcel_id = ? ORDER BY unix_timestamp(date_created) ASC",
        (parcel['id'],)
    )

    for t in tracks:
        st_idx = t['status']
        st_name = STATUS_LIST[st_idx] if 0 <= st_idx < len(STATUS_LIST) else str(st_idx)
        history.append({
            'status': st_name,
            'date_created': format_datetime(t['date_created']),
            'notes': t.get('notes', '')
        })

    return history

def save_parcel_feedback(parcel_id, customer_id, rating, comments=''):
    """Save customer feedback and star rating for a completed delivery."""
    rating = max(1, min(5, int(rating)))
    existing = query_db(
        "SELECT id FROM parcel_feedback WHERE parcel_id = ? AND customer_id = ?",
        (parcel_id, customer_id),
        one=True
    )
    if existing:
        execute_db(
            "UPDATE parcel_feedback SET rating = ?, comments = ? WHERE id = ?",
            (rating, comments.strip(), existing['id'])
        )
    else:
        execute_db(
            "INSERT INTO parcel_feedback (parcel_id, customer_id, rating, comments) VALUES (?, ?, ?, ?)",
            (parcel_id, customer_id, rating, comments.strip())
        )
    return 1

def get_dashboard_metrics(user_type=1, branch_id=None):
    total_branches = query_db("SELECT COUNT(*) as cnt FROM branches", one=True)['cnt']
    total_parcels = query_db("SELECT COUNT(*) as cnt FROM parcels", one=True)['cnt']
    total_staff = query_db("SELECT COUNT(*) as cnt FROM users WHERE type = 2", one=True)['cnt']
    total_customers = query_db("SELECT COUNT(*) as cnt FROM users WHERE type = 3", one=True)['cnt']

    status_counts = []
    for idx, name in enumerate(STATUS_LIST):
        cnt = query_db("SELECT COUNT(*) as cnt FROM parcels WHERE status = ?", (idx,), one=True)['cnt']
        status_counts.append({'status_id': idx, 'status_name': name, 'count': cnt})

    return {
        'total_branches': total_branches,
        'total_parcels': total_parcels,
        'total_staff': total_staff,
        'total_customers': total_customers,
        'status_counts': status_counts
    }
