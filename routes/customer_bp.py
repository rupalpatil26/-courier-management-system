from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from db import query_db
from models import user, parcel
from services.invoice_service import get_invoices_for_customer, get_invoice_details
from services.code_service import generate_qr_code_base64, generate_barcode_base64

customer_bp = Blueprint('customer', __name__, url_prefix='/customer')

def customer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'login_id' not in session:
            flash('Please log in to access the customer portal.', 'warning')
            return redirect(url_for('pages.login_page'))
        if session.get('login_type') != 3 and session.get('login_type') != 1:
            flash('Access restricted to registered customers.', 'danger')
            return redirect(url_for('pages.dashboard_page'))
        return f(*args, **kwargs)
    return decorated_function

@customer_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        if 'login_id' in session:
            if session.get('login_type') == 3:
                return redirect(url_for('customer.dashboard'))
            return redirect(url_for('pages.dashboard_page'))
        return render_template('customer/register.html')

    firstname = request.form.get('firstname', '').strip()
    lastname = request.form.get('lastname', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()
    phone = (request.form.get('phone') or request.form.get('contact') or '').strip()
    address = request.form.get('address', '').strip()

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return render_template('customer/register.html', firstname=firstname, lastname=lastname, email=email, phone=phone, address=address)

    status_code, result = user.register_customer(firstname, lastname, email, password, phone, address)
    if status_code == 1:
        # Automatically log customer in
        new_user = user.get_user_by_id(result)
        session['login_id'] = new_user['id']
        session['login_name'] = f"{new_user['firstname']} {new_user['lastname']}".strip()
        session['login_firstname'] = new_user['firstname']
        session['login_lastname'] = new_user['lastname']
        session['login_email'] = new_user['email']
        session['login_type'] = 3
        session['login_phone'] = new_user.get('phone', '')
        session['login_address'] = new_user.get('address', '')
        flash('Registration successful! Welcome to your customer portal.', 'success')
        return redirect(url_for('customer.dashboard'))
    elif status_code == 2:
        flash(result, 'danger')
        return render_template('customer/register.html', firstname=firstname, lastname=lastname, email=email, phone=phone, address=address)
    else:
        flash(result, 'danger')
        return render_template('customer/register.html', firstname=firstname, lastname=lastname, email=email, phone=phone, address=address)

@customer_bp.route('/dashboard')
@customer_required
def dashboard():
    cust_id = session.get('login_id')
    parcels = parcel.get_parcels_for_customer(cust_id)
    invoices = get_invoices_for_customer(cust_id)
    notifications = query_db(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 5",
        (cust_id,)
    )

    total_parcels = len(parcels)
    active_deliveries = sum(1 for p in parcels if p['status'] not in (7, 9))
    delivered_count = sum(1 for p in parcels if p['status'] == 7)
    unpaid_invoices = sum(1 for inv in invoices if inv['payment_status'] != 'Paid')

    return render_template(
        'customer/dashboard.html',
        parcels=parcels[:6],
        invoices=invoices[:5],
        notifications=notifications,
        metrics={
            'total_parcels': total_parcels,
            'active_deliveries': active_deliveries,
            'delivered_count': delivered_count,
            'unpaid_invoices': unpaid_invoices
        }
    )

@customer_bp.route('/book', methods=['GET', 'POST'])
@customer_required
def book_parcel():
    from werkzeug.datastructures import MultiDict

    cust_id = session.get('login_id')
    cust_user = user.get_user_by_id(cust_id)
    branches = query_db("SELECT * FROM branches ORDER BY city ASC")

    if request.method == 'GET':
        return render_template('customer/book_parcel.html', branches=branches, user=cust_user)

    # Build MultiDict and inject customer defaults
    form_dict = MultiDict()
    for key, values in request.form.lists():
        for v in values:
            form_dict.add(key, v)

    form_dict.setlist('customer_id', [str(cust_id)])
    if not form_dict.get('sender_name'):
        form_dict.setlist('sender_name', [f"{cust_user['firstname']} {cust_user['lastname']}".strip()])
    if not form_dict.get('sender_email'):
        form_dict.setlist('sender_email', [cust_user['email']])
    if not form_dict.get('sender_contact'):
        form_dict.setlist('sender_contact', [cust_user.get('phone', '')])
    if not form_dict.get('sender_address'):
        form_dict.setlist('sender_address', [cust_user.get('address', '')])

    save_res = parcel.save_parcel(form_dict)
    if isinstance(save_res, tuple) and not save_res[0]:
        flash(save_res[1], 'danger')
        return render_template('customer/book_parcel.html', branches=branches, user=cust_user, form_data=request.form)

    flash('Parcel shipment successfully booked!', 'success')
    return redirect(url_for('customer.parcels'))

@customer_bp.route('/parcels')
@customer_required
def parcels():
    cust_id = session.get('login_id')
    status = request.args.get('status', 'all')
    parcels_list = parcel.get_parcels_for_customer(cust_id, status=status)

    # Attach QR code and Barcode base64 to each parcel for instantaneous preview
    for p in parcels_list:
        p['qr_code'] = generate_qr_code_base64(f"REF:{p['reference_number']}")
        p['barcode'] = generate_barcode_base64(p['reference_number'])
        p['status_text'] = parcel.STATUS_LIST[p['status']] if 0 <= p['status'] < len(parcel.STATUS_LIST) else str(p['status'])

    return render_template('customer/parcels.html', parcels=parcels_list, current_status=status)

@customer_bp.route('/invoices')
@customer_required
def invoices():
    cust_id = session.get('login_id')
    inv_list = get_invoices_for_customer(cust_id)
    return render_template('customer/invoices.html', invoices=inv_list)

@customer_bp.route('/notifications')
@customer_required
def notifications():
    cust_id = session.get('login_id')
    notifs = query_db(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC",
        (cust_id,)
    )
    # Mark all as read
    query_db("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (cust_id,))
    return render_template('customer/notifications.html', notifications=notifs)

@customer_bp.route('/profile', methods=['GET', 'POST'])
@customer_required
def profile():
    cust_id = session.get('login_id')
    if request.method == 'POST':
        res = user.update_user_profile(request.form)
        if isinstance(res, tuple):
            if res[0]:
                flash('Profile updated successfully.', 'success')
            else:
                flash(res[1], 'danger')
        elif res == 1:
            flash('Profile updated successfully.', 'success')
        else:
            flash('Email already taken by another account.', 'danger')
        return redirect(url_for('customer.profile'))

    cust_user = user.get_user_by_id(cust_id)
    return render_template('customer/profile.html', user=cust_user)

@customer_bp.route('/feedback/<int:parcel_id>', methods=['POST'])
@customer_required
def submit_feedback(parcel_id):
    cust_id = session.get('login_id')
    rating = request.form.get('rating', 5)
    comments = request.form.get('comments', '')
    parcel.save_parcel_feedback(parcel_id, cust_id, rating, comments)
    flash('Thank you! Your feedback has been recorded.', 'success')
    return redirect(request.referrer or url_for('customer.parcels'))
