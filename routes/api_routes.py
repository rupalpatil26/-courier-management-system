import io
import csv
import json
from flask import Blueprint, request, redirect, url_for, Response, jsonify, send_file, session
from models import auth, branch, parcel, user, report
from models.analytics import get_analytics_dashboard_data
from services.code_service import (
    generate_qr_code_bytes, generate_barcode_bytes,
    generate_qr_code_base64, generate_barcode_base64
)
from services.otp_service import create_delivery_otp, verify_delivery_otp
from services.invoice_service import get_or_create_invoice, get_invoice_details
from services.email_service import notify_out_for_delivery

api_bp = Blueprint('api', __name__)

# ---------------------------------------------------------
# Authentication APIs
# ---------------------------------------------------------

@api_bp.route('/api/auth/login', methods=['POST'])
def api_login():
    """Authenticate user credentials and establish session."""
    data = request.get_json(silent=True) or request.form
    login_user = data.get('email') or data.get('username') or ''
    login_pass = data.get('password', '')
    res = auth.login(login_user, login_pass)
    return str(res)

@api_bp.route('/api/auth/logout', methods=['GET', 'POST'])
def api_logout():
    """Terminate user session and redirect to login page."""
    auth.logout()
    return redirect(url_for('pages.login_page'))

# ---------------------------------------------------------
# Branch Management APIs
# ---------------------------------------------------------

@api_bp.route('/api/branch/save', methods=['POST'])
def api_save_branch():
    """Create or update branch details."""
    data = request.get_json(silent=True) or request.form
    res = branch.save_branch(data)
    if isinstance(res, tuple):
        if res[0]:
            return "1"
        return jsonify({"status": "error", "message": res[1]})
    return str(res)

@api_bp.route('/api/branch/delete', methods=['POST'])
def api_delete_branch():
    """Delete branch by ID."""
    data = request.get_json(silent=True) or request.form
    res = branch.delete_branch(data.get('id'))
    return str(res)

# ---------------------------------------------------------
# Parcel Management APIs
# ---------------------------------------------------------

@api_bp.route('/api/parcel/save', methods=['POST'])
def api_save_parcel():
    """Book or update parcel consignment."""
    res = parcel.save_parcel(request.form)
    if isinstance(res, tuple):
        if res[0]:
            return "1"
        return jsonify({"status": "error", "message": res[1]})
    return str(res)

@api_bp.route('/api/parcel/update_status', methods=['POST'])
def api_update_parcel_status():
    """Update delivery lifecycle status of a parcel."""
    data = request.get_json(silent=True) or request.form
    staff_id = session.get('login_id', 0) if session.get('login_type') == 2 else 0
    res = parcel.update_parcel_status(
        data.get('id'),
        data.get('status'),
        staff_id=staff_id,
        notes=data.get('delivery_notes', '')
    )
    return str(res)

@api_bp.route('/api/parcel/delete', methods=['POST'])
def api_delete_parcel():
    """Delete parcel record by ID."""
    data = request.get_json(silent=True) or request.form
    res = parcel.delete_parcel(data.get('id'))
    return str(res)

@api_bp.route('/api/parcel/history', methods=['GET', 'POST'])
def parcel_history():
    """
    Fetch comprehensive parcel tracking details and milestone history.
    Accepts: 'ref_no' via query parameter, form data, or JSON.
    Returns 404 JSON error if parcel does not exist.
    Returns 200 JSON with parcel info and timeline milestones.
    """
    data = request.get_json(silent=True) or {}
    ref_no = request.args.get('ref_no') or request.form.get('ref_no') or data.get('ref_no', '')
    ref_no = str(ref_no).strip()

    if not ref_no:
        return jsonify({"status": "error", "message": "Reference number is required."}), 400

    from db import query_db
    from models.parcel import STATUS_LIST
    p_row = query_db("SELECT * FROM parcels WHERE reference_number = ?", (ref_no,), one=True)
    if not p_row:
        return jsonify({
            "status": "error",
            "message": f"No parcel found matching reference number '{ref_no}'."
        }), 404

    p_dict = dict(p_row)
    st_idx = p_dict.get('status', 0)
    p_dict['status_text'] = STATUS_LIST[st_idx] if 0 <= st_idx < len(STATUS_LIST) else str(st_idx)

    history_list = parcel.get_parcel_history(ref_no)
    if history_list == 2 or not isinstance(history_list, list):
        history_list = []

    return jsonify({
        "status": "success",
        "reference_number": ref_no,
        "parcel": p_dict,
        "history": history_list
    }), 200

# ---------------------------------------------------------
# User & Staff Management APIs
# ---------------------------------------------------------

@api_bp.route('/api/user/save', methods=['POST'])
def api_save_user():
    """Create or update user / staff profile."""
    img = request.files.get('img')
    res = user.save_user(request.form, img)
    if isinstance(res, tuple):
        if res[0]:
            return "1"
        if len(res) > 2 and res[2] == 2:
            return "2"
        return jsonify({"status": "error", "message": res[1]})
    return str(res)

@api_bp.route('/api/user/update', methods=['POST'])
def api_update_user():
    """Update current user profile."""
    img = request.files.get('img')
    res = user.update_user_profile(request.form, img)
    if isinstance(res, tuple):
        if res[0]:
            return "1"
        if len(res) > 2 and res[2] == 2:
            return "2"
        return jsonify({"status": "error", "message": res[1]})
    return str(res)

@api_bp.route('/api/user/delete', methods=['POST'])
def api_delete_user():
    """Delete user / staff member by ID."""
    data = request.get_json(silent=True) or request.form
    res = user.delete_user(data.get('id'))
    return str(res)

# ---------------------------------------------------------
# System Settings & Reports APIs
# ---------------------------------------------------------

@api_bp.route('/api/settings/save', methods=['POST'])
def api_save_settings():
    """Save system settings configuration."""
    cover = request.files.get('cover')
    res = auth.save_system_settings(request.form, cover)
    if isinstance(res, dict) and res.get('status') == 'error':
        return jsonify(res)
    return str(res)

@api_bp.route('/api/reports/data', methods=['GET', 'POST'])
def api_reports_data():
    """Fetch report data filtered by date range and delivery status."""
    data = request.get_json(silent=True) or request.form or request.args
    date_from = data.get('date_from', '')
    date_to = data.get('date_to', '')
    status = data.get('status', 'all')
    res = report.get_report_data(date_from, date_to, status)
    return Response(json.dumps(res), mimetype='application/json')

@api_bp.route('/api/ajax', methods=['GET', 'POST'])
def api_ajax_dispatcher():
    """Generic action dispatcher for legacy internal AJAX compatibility."""
    action = request.args.get('action') or request.form.get('action')
    if not action:
        return jsonify({"status": "error", "message": "Action not specified"}), 400

    try:
        if action == 'login':
            return api_login()
        elif action == 'logout':
            return api_logout()
        elif action == 'save_branch':
            return api_save_branch()
        elif action == 'delete_branch':
            return api_delete_branch()
        elif action == 'save_parcel':
            return api_save_parcel()
        elif action == 'update_parcel':
            return api_update_parcel_status()
        elif action == 'delete_parcel':
            return api_delete_parcel()
        elif action in ('get_parcel_history', 'parcel_history'):
            return parcel_history()
        elif action == 'get_report':
            return api_reports_data()
        elif action == 'save_user':
            return api_save_user()
        elif action == 'update_user':
            return api_update_user()
        elif action in ('delete_user', 'delete_staff'):
            return api_delete_user()
        elif action == 'save_system_settings':
            return api_save_settings()
        return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error handling API action '{action}': {e}", exc_info=True)
        return jsonify({"status": "error", "message": "A server error occurred while processing your request."}), 500

# ---------------------------------------------------------
# Feature 1: QR Code & Barcode Endpoints
# ---------------------------------------------------------

@api_bp.route('/api/parcel/<reference_number>/qrcode')
def parcel_qrcode_image(reference_number):
    """Stream PNG image bytes of QR code for a parcel."""
    url = request.host_url.rstrip('/') + url_for('pages.track_page') + f"?ref={reference_number}"
    qr_bytes = generate_qr_code_bytes(url)
    if not qr_bytes:
        return "Failed to generate QR code", 500
    return send_file(io.BytesIO(qr_bytes), mimetype='image/png', download_name=f"qr_{reference_number}.png")

@api_bp.route('/api/parcel/<reference_number>/barcode')
def parcel_barcode_image(reference_number):
    """Stream PNG image bytes of Code128 barcode for a parcel."""
    bc_bytes = generate_barcode_bytes(reference_number)
    if not bc_bytes:
        return "Failed to generate barcode", 500
    return send_file(io.BytesIO(bc_bytes), mimetype='image/png', download_name=f"barcode_{reference_number}.png")

@api_bp.route('/api/parcel/<reference_number>/details')
def parcel_api_details(reference_number):
    """Return JSON details of a parcel, including base64 codes, invoice, and tracking."""
    p = parcel.get_parcel_by_reference(reference_number)
    if not p:
        return jsonify({'error': 'Parcel not found'}), 404

    tracking_url = request.host_url.rstrip('/') + url_for('pages.track_page') + f"?ref={reference_number}"
    qr_b64 = generate_qr_code_base64(tracking_url)
    barcode_b64 = generate_barcode_base64(reference_number)
    invoice = get_or_create_invoice(p['id'], p.get('customer_id', 0))
    history = parcel.get_parcel_history(reference_number)

    p['qr_code'] = qr_b64
    p['barcode'] = barcode_b64
    p['invoice'] = invoice
    p['history'] = history if isinstance(history, list) else []
    p['status_text'] = parcel.STATUS_LIST[p['status']] if 0 <= p['status'] < len(parcel.STATUS_LIST) else str(p['status'])

    return jsonify(p)

# ---------------------------------------------------------
# Feature 4: OTP API Endpoints
# ---------------------------------------------------------

@api_bp.route('/api/otp/request', methods=['POST'])
def api_request_otp():
    parcel_id = request.form.get('parcel_id') or (request.json and request.json.get('parcel_id'))
    if not parcel_id:
        return jsonify({'success': False, 'message': 'Parcel ID required'}), 400

    p = parcel.get_parcel_by_id(parcel_id)
    if not p:
        return jsonify({'success': False, 'message': 'Parcel not found'}), 404

    otp_res = create_delivery_otp(int(parcel_id))
    if not otp_res.get('success'):
        return jsonify(otp_res)

    tracking_url = request.host_url.rstrip('/') + url_for('pages.track_page') + f"?ref={p['reference_number']}"
    staff_name = session.get('login_name', 'Delivery Agent')
    notify_out_for_delivery(p, otp_res['otp'], tracking_url, staff_name)

    return jsonify({
        'success': True,
        'message': f"OTP successfully dispatched to {p.get('recipient_email') or 'recipient'}.",
        'expires_at': otp_res.get('expires_at')
    })

@api_bp.route('/api/otp/verify', methods=['POST'])
def api_verify_otp():
    data = request.form if request.form else (request.json or {})
    parcel_id = data.get('parcel_id')
    otp = data.get('otp')
    notes = data.get('delivery_notes', '')

    if not parcel_id or not otp:
        return jsonify({'success': False, 'message': 'Parcel ID and OTP required'}), 400

    res = verify_delivery_otp(int(parcel_id), str(otp))
    if not res.get('success'):
        return jsonify(res)

    staff_id = session.get('login_id', 0)
    del_res = parcel.update_parcel_status(
        int(parcel_id),
        7,
        staff_id=staff_id,
        notes=notes or 'Delivered to recipient (OTP Verified)',
        bypass_otp=True
    )

    if del_res == 1:
        return jsonify({'success': True, 'message': 'OTP verified! Delivery marked complete.'})
    else:
        return jsonify({'success': False, 'message': 'Failed to record delivery status.'})

# ---------------------------------------------------------
# Feature 7: Advanced Reports & Chart Analytics
# ---------------------------------------------------------

@api_bp.route('/api/reports/analytics')
def api_report_analytics():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    branch_id = request.args.get('branch_id')
    staff_id = request.args.get('staff_id')
    status = request.args.get('status')

    analytics = get_analytics_dashboard_data(
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id,
        staff_id=staff_id,
        status=status
    )
    return jsonify(analytics)

@api_bp.route('/api/reports/export_csv')
def export_reports_csv():
    date_from = request.args.get('date_from', '2000-01-01')
    date_to = request.args.get('date_to', '2099-12-31')
    status = request.args.get('status', 'all')

    report_data = report.get_report_data(date_from, date_to, status)

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['#', 'Date Created', 'Tracking Number', 'Sender Name', 'Recipient Name', 'Status', 'Price ($)'])

    for idx, r in enumerate(report_data, 1):
        cw.writerow([
            idx,
            r['date_created'],
            r['reference_number'],
            r['sender_name'],
            r['recipient_name'],
            r['status'],
            r['price']
        ])

    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)

    filename = f"courier_report_{date_from}_to_{date_to}.csv"
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name=filename)

@api_bp.route('/api/feedback/submit', methods=['POST'])
def api_submit_feedback():
    data = request.form if request.form else (request.json or {})
    parcel_id = data.get('parcel_id')
    customer_id = data.get('customer_id') or session.get('login_id', 0)
    rating = data.get('rating', 5)
    comments = data.get('comments', '')

    if not parcel_id or not customer_id:
        return jsonify({'success': False, 'message': 'Missing parcel or customer ID.'}), 400

    res = parcel.save_parcel_feedback(int(parcel_id), int(customer_id), rating, comments)
    return jsonify({'success': bool(res == 1), 'message': 'Feedback submitted successfully!'})
