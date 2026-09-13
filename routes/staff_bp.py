from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from db import query_db
from models import user, parcel
from services.otp_service import create_delivery_otp, verify_delivery_otp
from services.email_service import notify_out_for_delivery
from services.code_service import generate_qr_code_base64, generate_barcode_base64

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'login_id' not in session:
            flash('Please log in to access the delivery staff portal.', 'warning')
            return redirect(url_for('pages.login_page'))
        if session.get('login_type') not in (1, 2):
            flash('Access restricted to authorized delivery personnel.', 'danger')
            return redirect(url_for('pages.dashboard_page'))
        return f(*args, **kwargs)
    return decorated_function

@staff_bp.route('/dashboard')
@staff_required
def dashboard():
    staff_id = session.get('login_id')
    all_assigned = parcel.get_parcels_for_staff(staff_id, view_filter='all')
    today_assigned = parcel.get_parcels_for_staff(staff_id, view_filter='today')
    pending_assigned = parcel.get_parcels_for_staff(staff_id, view_filter='pending')
    completed_assigned = parcel.get_parcels_for_staff(staff_id, view_filter='completed')
    failed_assigned = parcel.get_parcels_for_staff(staff_id, view_filter='failed')

    metrics = {
        'total': len(all_assigned),
        'today': len(today_assigned),
        'pending': len(pending_assigned),
        'completed': len(completed_assigned),
        'failed': len(failed_assigned)
    }

    # Attach QR/barcode to pending items for quick scan preview
    for p in pending_assigned[:10]:
        p['status_text'] = parcel.STATUS_LIST[p['status']] if 0 <= p['status'] < len(parcel.STATUS_LIST) else str(p['status'])
        p['qr_code'] = generate_qr_code_base64(f"REF:{p['reference_number']}")
        p['barcode'] = generate_barcode_base64(p['reference_number'])

    return render_template(
        'staff/dashboard.html',
        metrics=metrics,
        pending_parcels=pending_assigned[:10]
    )

@staff_bp.route('/deliveries')
@staff_required
def deliveries():
    staff_id = session.get('login_id')
    tab = request.args.get('tab', 'all')
    deliveries_list = parcel.get_parcels_for_staff(staff_id, view_filter=tab)

    for p in deliveries_list:
        p['status_text'] = parcel.STATUS_LIST[p['status']] if 0 <= p['status'] < len(parcel.STATUS_LIST) else str(p['status'])
        p['qr_code'] = generate_qr_code_base64(f"REF:{p['reference_number']}")
        p['barcode'] = generate_barcode_base64(p['reference_number'])

    return render_template('staff/deliveries.html', deliveries=deliveries_list, current_tab=tab)

@staff_bp.route('/scan')
@staff_required
def scan_page():
    return render_template('staff/scan.html')

@staff_bp.route('/request_otp', methods=['POST'])
@staff_required
def request_otp():
    parcel_id = request.form.get('parcel_id')
    if not parcel_id:
        return jsonify({'success': False, 'message': 'Parcel ID is required.'}), 400

    p_data = parcel.get_parcel_by_id(parcel_id)
    if not p_data:
        return jsonify({'success': False, 'message': 'Parcel not found.'}), 404

    otp_res = create_delivery_otp(int(parcel_id))
    if not otp_res.get('success'):
        return jsonify(otp_res)

    tracking_url = f"/track?ref_no={p_data['reference_number']}"
    staff_name = session.get('login_name', 'Courier Agent')
    notify_out_for_delivery(p_data, otp_res['otp'], tracking_url, staff_name)

    return jsonify({
        'success': True,
        'message': f"OTP sent to {p_data.get('recipient_email') or 'recipient'}.",
        'expires_at': otp_res.get('expires_at')
    })

@staff_bp.route('/verify_otp', methods=['POST'])
@staff_required
def verify_otp():
    parcel_id = request.form.get('parcel_id')
    entered_otp = request.form.get('otp', '').strip()
    notes = request.form.get('delivery_notes', '').strip()

    if not parcel_id or not entered_otp:
        return jsonify({'success': False, 'message': 'Parcel ID and OTP are required.'}), 400

    res = verify_delivery_otp(int(parcel_id), entered_otp)
    if not res.get('success'):
        return jsonify(res)

    # Success: mark status 7 (Delivered)
    staff_id = session.get('login_id', 0)
    del_res = parcel.update_parcel_status(
        int(parcel_id),
        7,
        staff_id=staff_id,
        notes=notes or 'Delivered to recipient (OTP Verified)',
        bypass_otp=True  # Already verified right here!
    )

    if del_res == 1:
        return jsonify({'success': True, 'message': 'OTP verified! Delivery recorded successfully.'})
    else:
        return jsonify({'success': False, 'message': 'Failed to record delivery status.'})

@staff_bp.route('/update_status', methods=['POST'])
@staff_required
def update_delivery_status():
    parcel_id = request.form.get('parcel_id')
    status = request.form.get('status')
    notes = request.form.get('delivery_notes', '').strip()
    staff_id = session.get('login_id', 0)

    if not parcel_id or status is None or str(status).strip() == '':
        flash('Missing parcel ID or status.', 'danger')
        return redirect(request.referrer or url_for('staff.deliveries'))

    try:
        pid = int(parcel_id)
        status_val = int(status)
        if status_val < 0 or status_val >= len(parcel.STATUS_LIST):
            flash('Invalid parcel status value.', 'danger')
            return redirect(request.referrer or url_for('staff.deliveries'))
    except (ValueError, TypeError):
        flash('Invalid parcel ID or status format.', 'danger')
        return redirect(request.referrer or url_for('staff.deliveries'))

    # Check if attempting to mark Delivered without OTP
    if status_val == 7:
        p_data = parcel.get_parcel_by_id(pid)
        if not p_data or not p_data.get('otp_verified'):
            flash('Cannot mark parcel as Delivered without OTP verification. Please enter the recipient OTP.', 'warning')
            return redirect(url_for('staff.deliveries'))

    res = parcel.update_parcel_status(pid, status_val, staff_id=staff_id, notes=notes)
    if res == -1:
        flash('Delivery verification required: Recipient OTP must be verified first.', 'warning')
    elif res == 1:
        flash('Parcel status updated successfully.', 'success')
    else:
        flash('Failed to update parcel status.', 'danger')

    return redirect(request.referrer or url_for('staff.deliveries'))
