import unittest
import json
from app import create_app
from db import get_db, query_db, execute_db
from models.auth import hash_password

class CourierManagementSystemTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def login_admin(self, username='admin', password='admin123'):
        return self.client.post('/api/auth/login', data={
            'email': username,
            'password': password
        })

    def test_01_public_landing_page(self):
        """Test public landing page and tracking widget UI rendering"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Track your parcel status', response.data)
        
        # Test /index route
        res_alias = self.client.get('/index')
        self.assertEqual(res_alias.status_code, 200)

    def test_02_login_and_logout(self):
        """Test authentication flow, session variables, and invalid credentials"""
        # Invalid credentials
        res_fail = self.client.post('/api/auth/login', data={
            'email': 'wrong@example.com',
            'password': 'invalidpassword'
        })
        self.assertEqual(res_fail.data.decode('utf-8').strip(), '2')

        # 1. Valid credentials with username 'admin'
        res_admin = self.login_admin(username='admin', password='admin123')
        self.assertEqual(res_admin.data.decode('utf-8').strip(), '1')

        # Check authenticated dashboard access
        res_dash = self.client.get('/dashboard?page=home')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'Total Branches', response_data := res_dash.data)

        # Logout
        res_logout = self.client.get('/api/auth/logout')
        self.assertEqual(res_logout.status_code, 302)

        # 2. Valid credentials with legacy 'admin@admin.com'
        res_legacy = self.login_admin(username='admin@admin.com', password='admin123')
        self.assertEqual(res_legacy.data.decode('utf-8').strip(), '1')

    def test_03_branch_crud(self):
        """Test creating, listing, updating, and deleting branches"""
        with self.client:
            self.login_admin()
            # 1. Create branch
            res_add = self.client.post('/api/branch/save', data={
                'street': '123 Test Blvd',
                'city': 'TestCity',
                'state': 'TestState',
                'zip_code': '99999',
                'country': 'TestCountry',
                'contact': '9876543210'
            })
            self.assertEqual(res_add.data.decode('utf-8').strip(), '1')

            # Verify in DB
            b = query_db("SELECT * FROM branches WHERE street = ? AND city = ?", ('123 Test Blvd', 'TestCity'), one=True)
            self.assertIsNotNone(b)
            self.assertTrue(len(b['branch_code']) > 0)
            branch_id = b['id']

            # 2. Update branch
            res_upd = self.client.post('/api/branch/save', data={
                'id': branch_id,
                'street': '456 Updated Ave',
                'city': 'TestCity',
                'state': 'TestState',
                'zip_code': '99999',
                'country': 'TestCountry',
                'contact': '9876543210'
            })
            self.assertEqual(res_upd.data.decode('utf-8').strip(), '1')
            b_updated = query_db("SELECT * FROM branches WHERE id = ?", (branch_id,), one=True)
            self.assertEqual(b_updated['street'], '456 Updated Ave')

            # 3. Delete branch
            res_del = self.client.post('/api/branch/delete', data={'id': branch_id})
            self.assertEqual(res_del.data.decode('utf-8').strip(), '1')
            b_deleted = query_db("SELECT * FROM branches WHERE id = ?", (branch_id,), one=True)
            self.assertIsNone(b_deleted)

    def test_04_staff_and_user_crud(self):
        """Test staff creation with branch association, duplicate detection, and deletion"""
        with self.client:
            self.login_admin()
            test_email = 'staff_test_auto@example.com'
            # Cleanup if existing
            execute_db("DELETE FROM users WHERE email = ?", (test_email,))

            # 1. Add staff
            res_add = self.client.post('/api/user/save', data={
                'firstname': 'Automated',
                'lastname': 'Staffer',
                'email': test_email,
                'password': 'password123',
                'type': '2',
                'branch_id': '1'
            })
            self.assertEqual(res_add.data.decode('utf-8').strip(), '1')

            u = query_db("SELECT * FROM users WHERE email = ?", (test_email,), one=True)
            self.assertIsNotNone(u)
            self.assertEqual(u['type'], 2)
            staff_id = u['id']

            # 2. Test duplicate email detection
            res_dup = self.client.post('/api/user/save', data={
                'firstname': 'Copy',
                'lastname': 'Cat',
                'email': test_email,
                'password': 'password123',
                'type': '2',
                'branch_id': '1'
            })
            self.assertEqual(res_dup.data.decode('utf-8').strip(), '2')

            # 3. Delete staff
            res_del = self.client.post('/api/user/delete', data={'id': staff_id})
            self.assertEqual(res_del.data.decode('utf-8').strip(), '1')
            self.assertIsNone(query_db("SELECT * FROM users WHERE id = ?", (staff_id,), one=True))

    def test_05_parcel_booking_and_lifecycle(self):
        """Test parcel booking, 12-digit ref generation, tracking history, and status progression"""
        with self.client:
            self.login_admin()
            # 1. Book a new parcel
            res_book = self.client.post('/api/parcel/save', data={
                'sender_name': 'Alice Smith',
                'sender_address': '789 Sender Lane',
                'sender_contact': '9876543211',
                'recipient_name': 'Bob Jones',
                'recipient_address': '321 Recipient Rd',
                'recipient_contact': '9876543212',
                'type': '1',
                'from_branch_id': '1',
                'to_branch_id': '1',
                'weight[]': ['2.5 kg'],
                'height[]': ['10 cm'],
                'width[]': ['20 cm'],
                'length[]': ['30 cm'],
                'price[]': ['150.00']
            })
            self.assertEqual(res_book.data.decode('utf-8').strip(), '1')

            parcel = query_db("SELECT * FROM parcels WHERE sender_name = ? ORDER BY id DESC", ('Alice Smith',), one=True)
            self.assertIsNotNone(parcel)
            ref_no = parcel['reference_number']
            self.assertEqual(len(ref_no), 12)
            parcel_id = parcel['id']

            # 2. Query initial tracking status (public tracking)
            res_track = self.client.get(f'/api/parcel/history?ref_no={ref_no}')
            self.assertEqual(res_track.status_code, 200)
            track_json = json.loads(res_track.data.decode('utf-8'))
            self.assertEqual(track_json['status'], 'success')
            history = track_json['history']
            self.assertIsInstance(history, list)
            self.assertTrue(len(history) >= 1)
            self.assertIn('Accepted', history[0]['status'])

            # 3. Advance lifecycle status to Collected (1), Shipped (2), and Delivered (7)
            for new_status in (1, 2, 7):
                res_upd = self.client.post('/api/parcel/update_status', data={
                    'id': parcel_id,
                    'status': str(new_status)
                })
                self.assertEqual(res_upd.data.decode('utf-8').strip(), '1')

            # 4. Verify updated history contains status progression
            res_track_updated = self.client.get(f'/api/parcel/history?ref_no={ref_no}')
            self.assertEqual(res_track_updated.status_code, 200)
            track_upd_json = json.loads(res_track_updated.data.decode('utf-8'))
            history_updated = track_upd_json['history']
            self.assertEqual(len(history_updated), 4)
            self.assertEqual(history_updated[-1]['status'], 'Delivered')

            # 5. Delete test parcel and clean up tracking records
            res_del = self.client.post('/api/parcel/delete', data={'id': parcel_id})
            self.assertEqual(res_del.data.decode('utf-8').strip(), '1')
            self.assertIsNone(query_db("SELECT * FROM parcels WHERE id = ?", (parcel_id,), one=True))

    def test_06_reports_generation(self):
        """Test transaction report filtering by date range"""
        with self.client:
            self.login_admin()
            res_report = self.client.post('/api/reports/data', data={
                'date_from': '2020-01-01',
                'date_to': '2030-12-31',
                'status': 'all'
            })
            self.assertEqual(res_report.status_code, 200)
            data = json.loads(res_report.data.decode('utf-8'))
            self.assertIsInstance(data, list)

    def test_07_modals_and_legacy_endpoints(self):
        """Test rendering of all modal views matching legacy PHP modal endpoints"""
        with self.client:
            self.login_admin()
            # View parcel modal
            p = query_db("SELECT id FROM parcels LIMIT 1", one=True)
            if p:
                res_vm = self.client.get(f"/modal/view_parcel?id={p['id']}")
                self.assertEqual(res_vm.status_code, 200)
                self.assertIn(b"Sender Information", res_vm.data)

                # Manage status modal
                res_sm = self.client.get(f"/modal/manage_parcel_status?id={p['id']}&cs=0")
                self.assertEqual(res_sm.status_code, 200)
                self.assertIn(b"Update Status", res_sm.data)

                # Print slip
                res_print = self.client.get(f"/print/parcels?ids={p['id']}")
                self.assertEqual(res_print.status_code, 200)
                self.assertIn(b"Print Parcel Details", res_print.data)

            # View user modal
            u = query_db("SELECT id FROM users LIMIT 1", one=True)
            if u:
                res_vu = self.client.get(f"/modal/view_user?id={u['id']}")
                self.assertEqual(res_vu.status_code, 200)

            # System settings page
            res_sys = self.client.get('/dashboard?page=system_settings')
            self.assertEqual(res_sys.status_code, 200)
            self.assertIn(b'System Name', res_sys.data)

    def test_08_qrcode_and_barcode_generation(self):
        """Test QR code and Code128 barcode generation as streaming images and base64 strings"""
        from services.code_service import generate_qr_code_base64, generate_barcode_base64
        parcel = query_db("SELECT reference_number FROM parcels LIMIT 1", one=True)
        self.assertIsNotNone(parcel)
        ref = parcel['reference_number']

        # QR Code image streaming endpoint
        res_qr = self.client.get(f'/api/parcel/{ref}/qrcode')
        self.assertEqual(res_qr.status_code, 200)
        self.assertEqual(res_qr.content_type, 'image/png')
        self.assertTrue(len(res_qr.data) > 100)

        # Barcode image streaming endpoint
        res_bc = self.client.get(f'/api/parcel/{ref}/barcode')
        self.assertEqual(res_bc.status_code, 200)
        self.assertEqual(res_bc.content_type, 'image/png')
        self.assertTrue(len(res_bc.data) > 100)

        # Base64 data URLs
        qr_b64 = generate_qr_code_base64(ref)
        bc_b64 = generate_barcode_base64(ref)
        self.assertTrue(qr_b64.startswith('data:image/png;base64,'))
        self.assertTrue(bc_b64.startswith('data:image/png;base64,'))

    def test_09_customer_registration_and_portal_access(self):
        """Test customer self-registration, session creation, and portal dashboard access"""
        from models.user import register_customer
        # 1. Register customer via helper
        code, cust_id = register_customer('Emma', 'Watson', 'emma@testcust.com', 'clientPass123', '9876543213', '123 Baker St')
        self.assertEqual(code, 1)
        self.assertTrue(cust_id > 0)

        # 2. Duplicate registration check
        code_dup, _ = register_customer('Emma', 'Watson', 'emma@testcust.com', 'clientPass123')
        self.assertEqual(code_dup, 2)

        # 3. Test customer portal login and dashboard
        with self.client:
            res_login = self.client.post('/api/auth/login', data={
                'email': 'emma@testcust.com',
                'password': 'clientPass123'
            })
            self.assertEqual(res_login.data.decode('utf-8').strip(), '1')

            # Customer dashboard
            res_dash = self.client.get('/customer/dashboard')
            self.assertEqual(res_dash.status_code, 200)
            self.assertIn(b'Emma', res_dash.data)

            # Customer profile
            res_prof = self.client.get('/customer/profile')
            self.assertEqual(res_prof.status_code, 200)

            # Clean up test customer
            execute_db("DELETE FROM users WHERE id = ?", (cust_id,))

    def test_10_customer_booking_and_invoices(self):
        """Test customer parcel booking flow, automatic invoice creation, and invoices list"""
        from models.user import register_customer
        from models.parcel import save_parcel
        from services.invoice_service import get_invoices_for_customer

        _, cust_id = register_customer('David', 'Beckham', 'david@testcust.com', 'david123')
        with self.client:
            self.client.post('/api/auth/login', data={'email': 'david@testcust.com', 'password': 'david123'})

            # Book parcel
            from werkzeug.datastructures import MultiDict
            book_data = MultiDict([
                ('customer_id', str(cust_id)),
                ('sender_name', 'David Beckham'),
                ('sender_address', '77 Legend Blvd'),
                ('sender_contact', '9876543214'),
                ('sender_email', 'david@testcust.com'),
                ('recipient_name', 'Victoria Beckham'),
                ('recipient_address', '88 Fashion Ave'),
                ('recipient_contact', '9876543215'),
                ('recipient_email', 'victoria@testcust.com'),
                ('from_branch_id', '1'),
                ('to_branch_id', '2'),
                ('type', '1'),
                ('weight[]', '2.5'),
                ('height[]', '15'),
                ('width[]', '20'),
                ('length[]', '25'),
                ('price[]', '65.00'),
                ('payment_method', 'Cash on Delivery')
            ])
            save_parcel(book_data)

            # Verify parcel was created
            p = query_db("SELECT * FROM parcels WHERE customer_id = ? ORDER BY id DESC", (cust_id,), one=True)
            self.assertIsNotNone(p)
            self.assertEqual(p['recipient_name'], 'Victoria Beckham')

            # Verify invoice was automatically generated
            invoices = get_invoices_for_customer(cust_id)
            self.assertTrue(len(invoices) >= 1)
            self.assertTrue(invoices[0]['invoice_number'].startswith('INV-'))

            # Customer view parcels and invoices pages
            res_p = self.client.get('/customer/parcels')
            self.assertEqual(res_p.status_code, 200)
            self.assertIn(b'Victoria Beckham', res_p.data)

            res_inv = self.client.get('/customer/invoices')
            self.assertEqual(res_inv.status_code, 200)

            # Clean up
            execute_db("DELETE FROM parcels WHERE id = ?", (p['id'],))
            execute_db("DELETE FROM invoices WHERE parcel_id = ?", (p['id'],))
            execute_db("DELETE FROM users WHERE id = ?", (cust_id,))

    def test_11_staff_portal_and_delivery_manifest(self):
        """Test delivery personnel hub, assignments view, and camera scanner page"""
        with self.client:
            # Login as staff (user id 2 from seed data: jsmith@sample.com)
            self.client.post('/api/auth/login', data={
                'email': 'jsmith@sample.com',
                'password': 'jsmith123'
            })

            # Hub Dashboard
            res_dash = self.client.get('/staff/dashboard')
            self.assertEqual(res_dash.status_code, 200)
            self.assertIn(b'Delivery Hub', res_dash.data)

            # Deliveries view with tabs
            res_del = self.client.get('/staff/deliveries?tab=all')
            self.assertEqual(res_del.status_code, 200)

            # Barcode / QR Scanner page
            res_scan = self.client.get('/staff/scan')
            self.assertEqual(res_scan.status_code, 200)
            self.assertIn(b'Scanner', res_scan.data)

    def test_12_otp_delivery_verification_lifecycle(self):
        """Test OTP generation, rate limiting, attempt limit, hash verification, and delivery completion"""
        from services.otp_service import create_delivery_otp, verify_delivery_otp
        from models.parcel import update_parcel_status, get_parcel_by_id

        # Pick an active parcel
        p = query_db("SELECT * FROM parcels LIMIT 1", one=True)
        self.assertIsNotNone(p)
        pid = p['id']

        # Reset parcel state for test
        execute_db("UPDATE parcels SET otp_verified = 0, status = 5 WHERE id = ?", (pid,))
        execute_db("DELETE FROM delivery_otps WHERE parcel_id = ?", (pid,))

        # Verify staff cannot mark status 7 (Delivered) without OTP verification
        denied_res = update_parcel_status(pid, 7, staff_id=2, bypass_otp=False)
        self.assertEqual(denied_res, -1)  # Denied!

        # 1. Generate OTP
        otp_res = create_delivery_otp(pid)
        self.assertTrue(otp_res['success'])
        raw_otp = otp_res['otp']
        self.assertEqual(len(raw_otp), 6)

        # 2. Rate limit test: immediate request within 60s cooldown fails
        rate_res = create_delivery_otp(pid)
        self.assertFalse(rate_res['success'])
        self.assertIn('Please wait', rate_res['message'])

        # 3. Invalid OTP submission fails
        fail_res = verify_delivery_otp(pid, '000000' if raw_otp != '000000' else '111111')
        self.assertFalse(fail_res['success'])

        # 4. Valid OTP verification succeeds
        succ_res = verify_delivery_otp(pid, raw_otp)
        self.assertTrue(succ_res['success'])

        # 5. Verify parcel otp_verified is now 1
        updated_p = get_parcel_by_id(pid)
        self.assertEqual(updated_p['otp_verified'], 1)

        # 6. Now delivery status 7 succeeds
        del_res = update_parcel_status(pid, 7, staff_id=2, bypass_otp=False)
        self.assertEqual(del_res, 1)

        # Clean up otp test data
        execute_db("DELETE FROM delivery_otps WHERE parcel_id = ?", (pid,))

    def test_13_invoice_generation_and_calculations(self):
        """Test invoice creation, financial totals, 5% logistics tax calculation, and idempotency"""
        from services.invoice_service import get_or_create_invoice, get_invoice_details
        parcel = query_db("SELECT * FROM parcels LIMIT 1", one=True)
        self.assertIsNotNone(parcel)

        inv1 = get_or_create_invoice(parcel['id'])
        self.assertIsNotNone(inv1)
        self.assertTrue(inv1['invoice_number'].startswith('INV-'))

        # Idempotency: calling twice returns existing invoice without duplicating
        inv2 = get_or_create_invoice(parcel['id'])
        self.assertEqual(inv1['id'], inv2['id'])
        self.assertEqual(inv1['invoice_number'], inv2['invoice_number'])

        # Calculation checks
        subtotal = float(parcel.get('price') or 0.0)
        expected_tax = round(subtotal * 0.05, 2)
        expected_total = round(subtotal + expected_tax, 2)
        self.assertAlmostEqual(float(inv1['subtotal']), subtotal, places=2)
        self.assertAlmostEqual(float(inv1['tax_amount']), expected_tax, places=2)
        self.assertAlmostEqual(float(inv1['total_amount']), expected_total, places=2)

        # Standalone invoice print page rendering
        res_view = self.client.get(f"/invoice/{inv1['invoice_number']}")
        self.assertEqual(res_view.status_code, 200)
        self.assertIn(inv1['invoice_number'].encode(), res_view.data)

    def test_14_email_notification_service_and_offline_fallback(self):
        """Test modular email sender with offline fallback and in-app notifications"""
        from services.email_service import send_email, create_in_app_notification
        
        # Test offline fallback (does not crash or raise when SMTP unconfigured)
        res = send_email('test@example.com', 'Test Notification', '<h1>Hello</h1>')
        self.assertTrue(res)

        # In-app notification creation
        user = query_db("SELECT id FROM users LIMIT 1", one=True)
        if user:
            ok = create_in_app_notification(user['id'], 'Shipment Update', 'Your parcel is on its way!')
            self.assertTrue(ok)
            notif = query_db("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user['id'],), one=True)
            self.assertIsNotNone(notif)
            self.assertEqual(notif['title'], 'Shipment Update')
            execute_db("DELETE FROM notifications WHERE id = ?", (notif['id'],))

    def test_15_reports_analytics_api_and_csv_export(self):
        """Test reports analytics API dataset for 6 Chart.js charts and CSV report download"""
        # Analytics JSON API
        res_ana = self.client.get('/api/reports/analytics')
        self.assertEqual(res_ana.status_code, 200)
        data = json.loads(res_ana.data.decode('utf-8'))
        self.assertIn('summary', data)
        self.assertIn('charts', data)
        self.assertIn('trend', data['charts'])
        self.assertIn('status', data['charts'])
        self.assertIn('branch', data['charts'])
        self.assertIn('outcome', data['charts'])
        self.assertIn('staff', data['charts'])

        # CSV Export endpoint
        res_csv = self.client.get('/api/reports/export_csv?date_from=2020-01-01&date_to=2030-12-31')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.content_type, 'text/csv; charset=utf-8')
        csv_text = res_csv.data.decode('utf-8')
        self.assertIn('Tracking Number', csv_text)
        self.assertIn('Sender Name', csv_text)

    def test_16_customer_feedback_submission(self):
        """Test customer delivery rating (1-5 stars) and comments submission"""
        from models.parcel import save_parcel_feedback
        parcel = query_db("SELECT id FROM parcels LIMIT 1", one=True)
        user = query_db("SELECT id FROM users LIMIT 1", one=True)
        self.assertIsNotNone(parcel)
        self.assertIsNotNone(user)

        res = save_parcel_feedback(parcel['id'], user['id'], 5, 'Super fast and courteous delivery!')
        self.assertEqual(res, 1)

        fb = query_db("SELECT * FROM parcel_feedback WHERE parcel_id = ? AND customer_id = ?", (parcel['id'], user['id']), one=True)
        self.assertIsNotNone(fb)
        self.assertEqual(fb['rating'], 5)
        self.assertIn('Super fast', fb['comments'])

        # API details contains feedback
        p = query_db("SELECT reference_number FROM parcels WHERE id = ?", (parcel['id'],), one=True)
        res_det = self.client.get(f"/api/parcel/{p['reference_number']}/details")
        self.assertEqual(res_det.status_code, 200)
        det = json.loads(res_det.data.decode('utf-8'))
        self.assertIsNotNone(det.get('feedback'))

        # Clean up feedback
        execute_db("DELETE FROM parcel_feedback WHERE id = ?", (fb['id'],))

    def test_17_unique_parcel_qr_code_and_scanning(self):
        """Test unique parcel QR code generation, details page section, download, print, invoice, and tracking resolution"""
        parcel = query_db("SELECT * FROM parcels LIMIT 1", one=True)
        self.assertIsNotNone(parcel)
        ref = parcel['reference_number']
        p_id = parcel['id']

        # 1. QR Code PNG direct endpoint
        res_qr = self.client.get(f"/api/parcel/{ref}/qrcode")
        self.assertEqual(res_qr.status_code, 200)
        self.assertEqual(res_qr.content_type, 'image/png')
        self.assertGreater(len(res_qr.data), 100)

        # 2. Parcel Details Modal (/modal/view_parcel?id=...)
        res_modal = self.client.get(f"/modal/view_parcel?id={p_id}")
        self.assertEqual(res_modal.status_code, 200)
        self.assertIn(b"Official Parcel QR Code & Barcode", res_modal.data)
        self.assertIn(b"Download QR Code", res_modal.data)
        self.assertIn(b"Print QR Code", res_modal.data)
        self.assertIn(f"/api/parcel/{ref}/qrcode".encode(), res_modal.data)

        # 3. Dedicated full page parcel details (dashboard?page=view_parcel&id=...)
        with self.client.session_transaction() as sess:
            sess['login_id'] = 1
            sess['login_type'] = 1
            sess['login_name'] = 'Administrator'
        res_page = self.client.get(f"/dashboard?page=view_parcel&id={p_id}")
        self.assertEqual(res_page.status_code, 200)
        self.assertIn(b"Official Parcel QR Code", res_page.data)
        self.assertIn(b"Download QR Code", res_page.data)
        self.assertIn(b"Print QR Code", res_page.data)

        # 4. Print Parcel Details page (/print/parcels?ids=...)
        res_print = self.client.get(f"/print/parcels?ids={p_id}")
        self.assertEqual(res_print.status_code, 200)
        self.assertIn(b"Print Parcel Details", res_print.data)
        self.assertTrue(b"qrcode" in res_print.data or b"data:image/png;base64" in res_print.data)

        # 5. Parcel Invoice
        from services.invoice_service import get_or_create_invoice
        inv = get_or_create_invoice(p_id)
        res_inv = self.client.get(f"/invoice/{inv['invoice_number']}")
        self.assertEqual(res_inv.status_code, 200)
        self.assertIn(b"Download QR", res_inv.data)
        self.assertTrue(b"qrcode" in res_inv.data or b"data:image/png;base64" in res_inv.data)

        # 6. Staff scanner API details lookup
        res_api = self.client.get(f"/api/parcel/{ref}/details")
        self.assertEqual(res_api.status_code, 200)
        api_data = json.loads(res_api.data.decode('utf-8'))
        self.assertEqual(api_data['reference_number'], ref)
        self.assertIn('qr_code', api_data)
        self.assertIn('barcode', api_data)

        # 7. Live tracking URL from QR code
        res_track = self.client.get(f"/track?ref={ref}", follow_redirects=True)
        self.assertEqual(res_track.status_code, 200)
        self.assertIn(ref.encode(), res_track.data)

if __name__ == '__main__':
    unittest.main()
