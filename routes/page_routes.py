from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from models import auth, branch, parcel, user, report
from models.parcel import STATUS_LIST
from models.analytics import get_analytics_dashboard_data
from services.code_service import generate_qr_code_base64, generate_barcode_base64
from services.invoice_service import get_invoice_details, get_or_create_invoice

page_bp = Blueprint('pages', __name__)

@page_bp.before_request
def setup_settings():
    auth.ensure_system_settings()

@page_bp.route('/')
@page_bp.route('/index')
def index():
    return render_template('landing.html', system=session.get('system', {}))

@page_bp.route('/login')
def login_page():
    if session.get('login_id'):
        u_type = session.get('login_type', 2)
        if u_type == 3:
            return redirect(url_for('customer.dashboard'))
        elif u_type == 2:
            return redirect(url_for('staff.dashboard'))
        return redirect(url_for('pages.dashboard', page='home'))
    return render_template('login.html', system=session.get('system', {}))

@page_bp.route('/track', endpoint='track_page')
def track_page():
    ref = request.args.get('ref_no', '') or request.args.get('ref', '')
    if session.get('login_id'):
        if ref:
            return redirect(url_for('pages.dashboard', page='track', ref_no=ref))
        return redirect(url_for('pages.dashboard', page='track'))
    if ref:
        return redirect(f'/?ref_no={ref}#track')
    return redirect('/#track')

@page_bp.route('/dashboard')
def dashboard():
    if not session.get('login_id'):
        return redirect(url_for('pages.login_page'))

    user_type = session.get('login_type', 2)
    # Redirect customer to customer dashboard
    if user_type == 3:
        return redirect(url_for('customer.dashboard'))

    page = request.args.get('page', 'home')
    status_filter = request.args.get('s')
    branch_id = session.get('login_branch_id', 0)

    context = {
        'page': page,
        'status_filter': status_filter,
        'status_list': STATUS_LIST,
        'system': session.get('system', {}),
        'user': session
    }

    if page == 'home':
        context['metrics'] = parcel.get_dashboard_metrics(user_type, branch_id)

    elif page == 'branch_list':
        context['branches'] = branch.get_all_branches()

    elif page in ('new_branch', 'edit_branch'):
        branch_id_arg = request.args.get('id')
        context['branch'] = branch.get_branch_by_id(branch_id_arg) if branch_id_arg else None

    elif page == 'parcel_list':
        context['parcels'] = parcel.get_parcels(status_filter, user_type, branch_id)
        for p in context['parcels']:
            p_track_url = request.host_url.rstrip('/') + f"/track?ref={p['reference_number']}"
            p['qr_code'] = generate_qr_code_base64(p_track_url)
            p['barcode'] = generate_barcode_base64(p['reference_number'])

    elif page in ('new_parcel', 'edit_parcel', 'view_parcel'):
        parcel_id_arg = request.args.get('id')
        p = parcel.get_parcel_by_id(parcel_id_arg) if parcel_id_arg else None
        if p:
            p_track_url = request.host_url.rstrip('/') + f"/track?ref={p['reference_number']}"
            p['qr_code'] = generate_qr_code_base64(p_track_url)
            p['barcode'] = generate_barcode_base64(p['reference_number'])
            p['invoice'] = get_or_create_invoice(int(p['id']), p.get('customer_id', 0))
        context['parcel'] = p
        context['branches'] = branch.get_all_branches()
        context['staff_users'] = user.get_staff_users()

    elif page == 'staff_list':
        context['staff'] = user.get_staff_users()

    elif page in ('new_staff', 'edit_staff'):
        staff_id_arg = request.args.get('id')
        context['staff_member'] = user.get_user_by_id(staff_id_arg) if staff_id_arg else None
        context['branches'] = branch.get_all_branches()

    elif page == 'user_list':
        context['users'] = user.get_all_users()

    elif page in ('new_user', 'edit_user'):
        user_id_arg = request.args.get('id')
        context['user_item'] = user.get_user_by_id(user_id_arg) if user_id_arg else None

    elif page == 'track':
        pass

    elif page == 'reports':
        context['branches'] = branch.get_all_branches()
        context['staff_list'] = user.get_staff_users()
        context['analytics'] = get_analytics_dashboard_data()

    elif page == 'system_settings':
        context['settings'] = auth.get_system_settings()

    else:
        return render_template('404.html'), 404

    return render_template('dashboard.html', **context)

# ---------------------------------------------------------
# Invoice Page Route (Feature 5)
# ---------------------------------------------------------

@page_bp.route('/invoice/<inv_param>')
@page_bp.route('/invoice', endpoint='view_invoice_page_default')
def view_invoice_page(inv_param=None):
    inv_id = inv_param or request.args.get('id') or request.args.get('parcel_id')
    if not inv_id:
        return redirect(url_for('pages.dashboard', page='parcel_list'))

    # If parcel_id was passed, get or create invoice
    if request.args.get('parcel_id'):
        inv = get_or_create_invoice(int(request.args.get('parcel_id')))
        if inv:
            return redirect(url_for('pages.view_invoice_page', inv_param=inv['invoice_number']))

    inv_details = get_invoice_details(inv_id)
    if not inv_details:
        return render_template('404.html'), 404

    parcel_data = inv_details.get('parcel', {})
    ref_num = parcel_data.get('reference_number', '')

    tracking_url = request.host_url.rstrip('/') + url_for('pages.track_page') + f"?ref_no={ref_num}"
    qr_b64 = generate_qr_code_base64(tracking_url)
    barcode_b64 = generate_barcode_base64(ref_num)

    return render_template(
        'invoice.html',
        invoice=inv_details,
        parcel=parcel_data,
        qr_code=qr_b64,
        barcode=barcode_b64,
        system=session.get('system', {})
    )

# ---------------------------------------------------------
# Modal Routes (matching uni_modal)
# ---------------------------------------------------------

@page_bp.route('/modal/view_parcel')
def view_parcel_modal():
    parcel_id = request.args.get('id')
    p = parcel.get_parcel_by_id(parcel_id)
    if p:
        tracking_url = request.host_url.rstrip('/') + url_for('pages.track_page') + f"?ref_no={p['reference_number']}"
        p['qr_code'] = generate_qr_code_base64(tracking_url)
        p['barcode'] = generate_barcode_base64(p['reference_number'])
        p['invoice'] = get_or_create_invoice(int(parcel_id), p.get('customer_id', 0))
    return render_template('modals/view_parcel.html', parcel=p, status_list=STATUS_LIST)

@page_bp.route('/modal/view_invoice')
def view_invoice_modal():
    inv_id = request.args.get('id') or request.args.get('parcel_id')
    if request.args.get('parcel_id'):
        inv = get_or_create_invoice(int(request.args.get('parcel_id')))
        if inv:
            inv_id = inv['id']

    inv_details = get_invoice_details(inv_id)
    parcel_data = inv_details.get('parcel', {}) if inv_details else {}
    ref_num = parcel_data.get('reference_number', '')

    qr_b64 = generate_qr_code_base64(f"REF:{ref_num}")
    barcode_b64 = generate_barcode_base64(ref_num)

    return render_template(
        'modals/view_invoice.html',
        invoice=inv_details,
        parcel=parcel_data,
        qr_code=qr_b64,
        barcode=barcode_b64
    )

@page_bp.route('/modal/manage_parcel_status')
def manage_parcel_status_modal():
    parcel_id = request.args.get('id')
    current_status = request.args.get('cs', 0)
    p = parcel.get_parcel_by_id(parcel_id)
    return render_template(
        'modals/manage_parcel_status.html',
        id=parcel_id,
        current_status=int(current_status),
        status_list=STATUS_LIST,
        parcel=p
    )

@page_bp.route('/modal/feedback')
def feedback_modal():
    parcel_id = request.args.get('id')
    p = parcel.get_parcel_by_id(parcel_id)
    return render_template('modals/feedback_modal.html', parcel=p)

@page_bp.route('/modal/view_user')
@page_bp.route('/modal/view_staff')
def view_user_modal():
    user_id = request.args.get('id')
    u = user.get_user_by_id(user_id)
    return render_template('modals/view_user.html', user=u)

@page_bp.route('/modal/view_branch')
def view_branch_modal():
    branch_id = request.args.get('id')
    b = branch.get_branch_by_id(branch_id)
    return render_template('modals/view_branch.html', branch=b)

@page_bp.route('/modal/manage_user')
def manage_user_modal():
    user_id = request.args.get('id') or session.get('login_id')
    u = user.get_user_by_id(user_id)
    return render_template('modals/manage_user.html', user=u)

@page_bp.route('/print/parcels')
@page_bp.route('/modal/print_pdets')
def print_pdets():
    ids = request.args.get('ids', '')
    if not ids:
        return ""
    id_list = [int(x.strip()) for x in ids.split(',') if x.strip().isdigit()]
    parcels_list = []
    for pid in id_list:
        p = parcel.get_parcel_by_id(pid)
        if p:
            p['qr_code'] = generate_qr_code_base64(f"REF:{p['reference_number']}")
            p['barcode'] = generate_barcode_base64(p['reference_number'])
            parcels_list.append(p)
    return render_template('modals/print_pdets.html', parcels=parcels_list)
