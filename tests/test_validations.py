import unittest
import json
from app import create_app
from db import query_db, execute_db
from services.validator import (
    validate_email,
    validate_phone,
    validate_positive_number,
    check_duplicate_email,
    check_duplicate_branch_code,
    check_duplicate_reference
)

class CMSValidationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Clean up any leftover test data
        execute_db("DELETE FROM users WHERE email LIKE '%@testvalidation.com'")
        execute_db("DELETE FROM branches WHERE street LIKE 'TestValStreet%'")
        execute_db("DELETE FROM parcels WHERE reference_number LIKE 'TESTREF%'")

    def tearDown(self):
        execute_db("DELETE FROM users WHERE email LIKE '%@testvalidation.com'")
        execute_db("DELETE FROM branches WHERE street LIKE 'TestValStreet%'")
        execute_db("DELETE FROM parcels WHERE reference_number LIKE 'TESTREF%'")
        self.ctx.pop()

    def login_admin(self):
        return self.client.post('/api/auth/login', data={
            'email': 'admin',
            'password': 'admin123'
        })

    # =========================================================================
    # 1. LOGIN VALIDATION TESTS
    # =========================================================================
    def test_login_empty_credentials(self):
        """Empty username or password should return 'empty' with no sensitive leak."""
        res_both_empty = self.client.post('/api/auth/login', data={'username': '', 'password': ''})
        self.assertEqual(res_both_empty.data.decode('utf-8').strip(), 'empty')

        res_user_empty = self.client.post('/api/auth/login', data={'username': '', 'password': 'somepassword'})
        self.assertEqual(res_user_empty.data.decode('utf-8').strip(), 'empty')

        res_pass_empty = self.client.post('/api/auth/login', data={'username': 'admin', 'password': ''})
        self.assertEqual(res_pass_empty.data.decode('utf-8').strip(), 'empty')

    def test_login_wrong_credentials(self):
        """Wrong username/password should return '2' (mapped to 'Invalid username or password.')."""
        res_wrong = self.client.post('/api/auth/login', data={
            'username': 'wrong_user_not_exist',
            'password': 'wrong_password_123'
        })
        self.assertEqual(res_wrong.data.decode('utf-8').strip(), '2')

        # Wrong password for existing user
        res_wrong_pass = self.client.post('/api/auth/login', data={
            'username': 'admin',
            'password': 'IncorrectPassword!'
        })
        self.assertEqual(res_wrong_pass.data.decode('utf-8').strip(), '2')

    # =========================================================================
    # 2. EMAIL FORMAT VALIDATION TESTS
    # =========================================================================
    def test_email_validator_rules(self):
        """Test exact acceptance and rejection rules for email addresses."""
        # Valid email
        ok, msg = validate_email('prasad123@gmail.com')
        self.assertTrue(ok)
        self.assertEqual(msg, '')

        # Invalid emails specified in requirement
        bad_emails = [
            'prasad @1234gmail.com',  # Space before @
            'prasad@',                # Missing domain
            '@gmail.com',             # Missing username
            'prasad@gmail',           # Missing TLD
            'prasad..test@gmail.com', # Consecutive dots
            'prasad @gmail.com',      # Spaces
            'plainaddress',           # No @
            '',                       # Empty
            '   '                     # Whitespace
        ]
        for bad in bad_emails:
            ok, msg = validate_email(bad)
            self.assertFalse(ok, f"Expected '{bad}' to be rejected as an invalid email")
            self.assertTrue(len(msg) > 0)

    # =========================================================================
    # 3. INDIAN PHONE NUMBER VALIDATION TESTS
    # =========================================================================
    def test_indian_phone_validator_rules(self):
        """Test Indian 10-digit mobile number rules (^[6-9]\\d{9}$)."""
        # Valid Indian phone formats (all normalize to 10 digits starting with 6-9)
        valid_phones = [
            '9876543210',
            '+91 9876543210',
            '+91-98765-43210',
            '09876543210',
            '919876543210',
            '8123456789',
            '7000000001',
            '6999999999'
        ]
        for phone in valid_phones:
            ok, msg, clean = validate_phone(phone, "Contact")
            self.assertTrue(ok, f"Expected '{phone}' to be accepted as a valid Indian number: {msg}")
            self.assertEqual(len(clean), 10)
            self.assertIn(clean[0], ['6', '7', '8', '9'])

        # Invalid phone formats
        invalid_phones = [
            'abc1234567',   # Contains letters
            '   ',          # Spaces only
            '12345',        # Too short
            '1234567890',   # Starts with 1 (not 6-9)
            '5551234567',   # Starts with 5
            '987654321012', # Too long
            '98765-abcde',  # Mixed alphanumeric
        ]
        for phone in invalid_phones:
            ok, msg, clean = validate_phone(phone, "Contact")
            self.assertFalse(ok, f"Expected '{phone}' to be rejected as invalid phone")

    # =========================================================================
    # 4. DUPLICATE DATA PREVENTION TESTS
    # =========================================================================
    def test_duplicate_email_detection(self):
        """Prevent duplicate user email addresses and verify 'Email already exists.' message."""
        with self.client:
            self.login_admin()
            email = 'dup_user_test@testvalidation.com'

            # 1. Create first user
            res1 = self.client.post('/api/user/save', data={
                'firstname': 'UserOne',
                'lastname': 'Test',
                'email': email,
                'password': 'password123',
                'type': '2',
                'branch_id': '1'
            })
            self.assertEqual(res1.data.decode('utf-8').strip(), '1')

            # 2. Try creating second user with duplicate email
            res2 = self.client.post('/api/user/save', data={
                'firstname': 'UserTwo',
                'lastname': 'Test',
                'email': email,
                'password': 'password123',
                'type': '2',
                'branch_id': '1'
            })
            self.assertEqual(res2.data.decode('utf-8').strip(), '2')

            # Test check_duplicate_email helper directly
            ok, msg = check_duplicate_email(email)
            self.assertFalse(ok)
            self.assertEqual(msg, "Email already exists.")

    def test_duplicate_branch_code_detection(self):
        """Prevent duplicate branch codes with 'Branch code already exists.'."""
        with self.client:
            self.login_admin()
            bcode = 'BR_TEST_DUP_99'

            # 1. Save branch with custom code
            res1 = self.client.post('/api/branch/save', data={
                'branch_code': bcode,
                'street': 'TestValStreet 1',
                'city': 'Pune',
                'state': 'Maharashtra',
                'zip_code': '411001',
                'country': 'India',
                'contact': '9876543210'
            })
            self.assertEqual(res1.data.decode('utf-8').strip(), '1')

            # 2. Try saving another branch with identical branch code
            res2 = self.client.post('/api/branch/save', data={
                'branch_code': bcode,
                'street': 'TestValStreet 2',
                'city': 'Mumbai',
                'state': 'Maharashtra',
                'zip_code': '400001',
                'country': 'India',
                'contact': '9876543211'
            })
            resp_data = json.loads(res2.data.decode('utf-8'))
            self.assertEqual(resp_data.get('status'), 'error')
            self.assertIn("Branch code already exists.", resp_data.get('message', ''))

    def test_duplicate_parcel_reference_detection(self):
        """Prevent duplicate parcel reference numbers with 'Parcel reference already exists.'."""
        with self.client:
            self.login_admin()
            custom_ref = 'TESTREF123456'

            # 1. Book first parcel with custom reference
            res1 = self.client.post('/api/parcel/save', data={
                'reference_number': custom_ref,
                'sender_name': 'Sender Test',
                'sender_address': 'Address 1',
                'sender_contact': '9876543210',
                'sender_email': 'sender@testvalidation.com',
                'recipient_name': 'Recipient Test',
                'recipient_address': 'Address 2',
                'recipient_contact': '9876543211',
                'recipient_email': 'recipient@testvalidation.com',
                'type': '1',
                'from_branch_id': '1',
                'to_branch_id': '1',
                'weight[]': ['1.5'],
                'height[]': ['10'],
                'width[]': ['10'],
                'length[]': ['10'],
                'price[]': ['100']
            })
            self.assertEqual(res1.data.decode('utf-8').strip(), '1')

            # 2. Attempt duplicate reference
            res2 = self.client.post('/api/parcel/save', data={
                'reference_number': custom_ref,
                'sender_name': 'Sender Test 2',
                'sender_address': 'Address 3',
                'sender_contact': '9876543212',
                'recipient_name': 'Recipient Test 2',
                'recipient_address': 'Address 4',
                'recipient_contact': '9876543213',
                'type': '1',
                'from_branch_id': '1',
                'to_branch_id': '1',
                'weight[]': ['2.0'],
                'height[]': ['12'],
                'width[]': ['12'],
                'length[]': ['12'],
                'price[]': ['150']
            })
            resp_data = json.loads(res2.data.decode('utf-8'))
            self.assertEqual(resp_data.get('status'), 'error')
            self.assertIn("Parcel reference already exists.", resp_data.get('message', ''))

    # =========================================================================
    # 5. PARCEL METRICS VALIDATION TESTS (> 0)
    # =========================================================================
    def test_parcel_metrics_positive_validation(self):
        """Parcel weight, height, width, length, and price must be strictly > 0."""
        # Positive numbers helper check
        ok, msg, val = validate_positive_number('2.5', 'Weight')
        self.assertTrue(ok)
        self.assertEqual(val, 2.5)

        # Zero rejected
        ok, msg, _ = validate_positive_number('0', 'Weight')
        self.assertFalse(ok)
        self.assertIn('greater than zero', msg)

        # Negative rejected
        ok, msg, _ = validate_positive_number('-10', 'Height')
        self.assertFalse(ok)
        self.assertIn('greater than zero', msg)

        # Non-numeric rejected
        ok, msg, _ = validate_positive_number('abc', 'Price')
        self.assertFalse(ok)
        self.assertIn('valid number', msg)

        # Form submission testing:
        with self.client:
            self.login_admin()

            # Test zero weight
            res_zero_w = self.client.post('/api/parcel/save', data={
                'sender_name': 'Sender A',
                'sender_address': 'Address A',
                'sender_contact': '9876543210',
                'recipient_name': 'Recipient B',
                'recipient_address': 'Address B',
                'recipient_contact': '9876543211',
                'type': '1',
                'from_branch_id': '1',
                'to_branch_id': '1',
                'weight[]': ['0'],
                'height[]': ['10'],
                'width[]': ['10'],
                'length[]': ['10'],
                'price[]': ['100']
            })
            data = json.loads(res_zero_w.data.decode('utf-8'))
            self.assertEqual(data.get('status'), 'error')
            self.assertIn('greater than zero', data.get('message', ''))

            # Test negative price
            res_neg_p = self.client.post('/api/parcel/save', data={
                'sender_name': 'Sender A',
                'sender_address': 'Address A',
                'sender_contact': '9876543210',
                'recipient_name': 'Recipient B',
                'recipient_address': 'Address B',
                'recipient_contact': '9876543211',
                'type': '1',
                'from_branch_id': '1',
                'to_branch_id': '1',
                'weight[]': ['2.0'],
                'height[]': ['10'],
                'width[]': ['10'],
                'length[]': ['10'],
                'price[]': ['-50']
            })
            data = json.loads(res_neg_p.data.decode('utf-8'))
            self.assertEqual(data.get('status'), 'error')
            self.assertIn('greater than zero', data.get('message', ''))

    # =========================================================================
    # 6. REQUIRED FIELDS VALIDATION TESTS
    # =========================================================================
    def test_branch_required_fields(self):
        """Branch creation must validate street, city, state, zip_code, country, contact."""
        with self.client:
            self.login_admin()
            # Missing city and zip_code
            res = self.client.post('/api/branch/save', data={
                'street': '123 Main St',
                'city': '',
                'state': 'MH',
                'zip_code': '',
                'country': 'India',
                'contact': '9876543210'
            })
            data = json.loads(res.data.decode('utf-8'))
            self.assertEqual(data.get('status'), 'error')
            self.assertIn('City is required', data.get('message', ''))

    def test_parcel_required_fields(self):
        """Parcel creation must validate sender, recipient, contacts, branch."""
        with self.client:
            self.login_admin()
            # Missing sender_name
            res = self.client.post('/api/parcel/save', data={
                'sender_name': '',
                'sender_address': 'Some Address',
                'sender_contact': '9876543210',
                'recipient_name': 'Recipient B',
                'recipient_address': 'Address B',
                'recipient_contact': '9876543211',
                'type': '1',
                'from_branch_id': '1',
                'weight[]': ['1'],
                'height[]': ['1'],
                'width[]': ['1'],
                'length[]': ['1'],
                'price[]': ['100']
            })
            data = json.loads(res.data.decode('utf-8'))
            self.assertEqual(data.get('status'), 'error')
            self.assertIn('Sender name is required', data.get('message', ''))

    # =========================================================================
    # 7. CUSTOMER REGISTRATION VALIDATION TESTS
    # =========================================================================
    def test_customer_registration_validations(self):
        """Test customer registration password rules, email format, and phone format."""
        # 1. Password mismatch
        res_mismatch = self.client.post('/customer/register', data={
            'firstname': 'Customer',
            'lastname': 'User',
            'email': 'valid_cust@testvalidation.com',
            'contact': '9876543210',
            'address': 'Pune, India',
            'password': 'Password123',
            'confirm_password': 'DifferentPassword456'
        })
        self.assertIn(b'Passwords do not match', res_mismatch.data)

        # 2. Short password (< 6 chars)
        res_short = self.client.post('/customer/register', data={
            'firstname': 'Customer',
            'lastname': 'User',
            'email': 'valid_cust@testvalidation.com',
            'contact': '9876543210',
            'address': 'Pune, India',
            'password': '123',
            'confirm_password': '123'
        })
        self.assertIn(b'at least 6 characters', res_short.data)

        # 3. Invalid phone number
        res_bad_phone = self.client.post('/customer/register', data={
            'firstname': 'Customer',
            'lastname': 'User',
            'email': 'valid_cust@testvalidation.com',
            'contact': '12345',
            'address': 'Pune, India',
            'password': 'Password123',
            'confirm_password': 'Password123'
        })
        self.assertIn(b'10-digit mobile number', res_bad_phone.data)

        # 4. Invalid email format
        res_bad_email = self.client.post('/customer/register', data={
            'firstname': 'Customer',
            'lastname': 'User',
            'email': 'prasad @1234gmail.com',
            'contact': '9876543210',
            'address': 'Pune, India',
            'password': 'Password123',
            'confirm_password': 'Password123'
        })
        self.assertIn(b'valid email address', res_bad_email.data)

        # 5. Successful registration
        res_success = self.client.post('/customer/register', data={
            'firstname': 'Customer',
            'lastname': 'User',
            'email': 'valid_cust@testvalidation.com',
            'contact': '9876543210',
            'address': 'Pune, India',
            'password': 'Password123',
            'confirm_password': 'Password123'
        }, follow_redirects=True)
        self.assertEqual(res_success.status_code, 200)
        self.assertIn(b'Registration successful', res_success.data)

    # =========================================================================
    # 8. PARCEL STATUS VALIDATION TESTS
    # =========================================================================
    def test_parcel_status_validation(self):
        """Invalid status indices should be rejected."""
        with self.client:
            self.login_admin()
            # Out of bounds status
            res_invalid = self.client.post('/api/parcel/update_status', data={
                'id': '1',
                'status': '99'
            })
            self.assertEqual(res_invalid.data.decode('utf-8').strip(), '0')

            # Non-integer status
            res_nan = self.client.post('/api/parcel/update_status', data={
                'id': '1',
                'status': 'delivered_string'
            })
            self.assertEqual(res_nan.data.decode('utf-8').strip(), '0')

    # =========================================================================
    # 9. FLASK PARCEL TRACKING API TESTS (/api/parcel/history)
    # =========================================================================
    def test_parcel_tracking_api_valid_and_not_found(self):
        """Test /api/parcel/history endpoint for valid lookup and 404 error handling."""
        with self.client:
            self.login_admin()
            ref_no = 'TESTREF998877'

            # 1. Search non-existent parcel -> 404
            res_404 = self.client.get('/api/parcel/history?ref_no=DOES_NOT_EXIST_1234')
            self.assertEqual(res_404.status_code, 404)
            data_404 = json.loads(res_404.data.decode('utf-8'))
            self.assertEqual(data_404.get('status'), 'error')
            self.assertIn("No parcel found", data_404.get('message', ''))

            # 2. Missing ref_no -> 400
            res_400 = self.client.get('/api/parcel/history?ref_no=')
            self.assertEqual(res_400.status_code, 400)

            # 3. Create parcel for testing
            self.client.post('/api/parcel/save', data={
                'reference_number': ref_no,
                'sender_name': 'Tracking Sender',
                'sender_address': 'Sender Addr',
                'sender_contact': '9876543210',
                'recipient_name': 'Tracking Recipient',
                'recipient_address': 'Recipient Addr',
                'recipient_contact': '9876543211',
                'type': '1',
                'from_branch_id': '1',
                'to_branch_id': '1',
                'weight[]': ['3.5'],
                'height[]': ['15'],
                'width[]': ['15'],
                'length[]': ['15'],
                'price[]': ['250.00']
            })

            # 4. Search existing parcel -> 200 OK with parcel & history
            res_ok = self.client.get(f'/api/parcel/history?ref_no={ref_no}')
            self.assertEqual(res_ok.status_code, 200)
            data_ok = json.loads(res_ok.data.decode('utf-8'))
            self.assertEqual(data_ok.get('status'), 'success')
            self.assertEqual(data_ok.get('reference_number'), ref_no)
            self.assertIn('parcel', data_ok)
            self.assertEqual(data_ok['parcel']['reference_number'], ref_no)
            self.assertIn('history', data_ok)
            self.assertTrue(isinstance(data_ok['history'], list))
            self.assertTrue(len(data_ok['history']) >= 1)

    # =========================================================================
    # 10. SYSTEM SETTINGS & PROFILE VALIDATION TESTS
    # =========================================================================
    def test_system_settings_validation(self):
        """System settings update must reject invalid emails and non-Indian phones."""
        from models.auth import save_system_settings
        # Bad email
        bad_email_data = {
            'name': 'CMS Hub',
            'email': 'prasad @1234gmail.com',
            'contact': '9876543210',
            'address': 'Pune, India'
        }
        res = save_system_settings(bad_email_data)
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get('status'), 'error')
        self.assertIn('Email', res.get('message', ''))

        # Bad phone
        bad_phone_data = {
            'name': 'CMS Hub',
            'email': 'prasad123@gmail.com',
            'contact': '12345letters',
            'address': 'Pune, India'
        }
        res2 = save_system_settings(bad_phone_data)
        self.assertIsInstance(res2, dict)
        self.assertEqual(res2.get('status'), 'error')
        self.assertIn('cannot contain letters', res2.get('message', ''))

    def test_staff_creation_validation(self):
        """Staff creation validates required fields and proper email format."""
        with self.client:
            self.login_admin()
            # Missing firstname
            res = self.client.post('/api/user/save', data={
                'firstname': '',
                'lastname': 'Staffer',
                'email': 'staff_val@testvalidation.com',
                'password': 'password123',
                'type': '2',
                'branch_id': '1'
            })
            data = json.loads(res.data.decode('utf-8'))
            self.assertEqual(data.get('status'), 'error')
            self.assertIn('First name and last name are required', data.get('message', ''))

            # Invalid email format
            res_bad_email = self.client.post('/api/user/save', data={
                'firstname': 'Staff',
                'lastname': 'User',
                'email': '@gmail.com',
                'password': 'password123',
                'type': '2',
                'branch_id': '1'
            })
            data2 = json.loads(res_bad_email.data.decode('utf-8'))
            self.assertEqual(data2.get('status'), 'error')
            self.assertIn('valid email address', data2.get('message', ''))

    # =========================================================================
    # 11. ERROR SANITIZATION & SECURITY TESTS
    # =========================================================================
    def test_ajax_error_sanitization_no_stacktrace(self):
        """API error responses must return sanitized JSON and never leak Python/DB stack traces."""
        with self.client:
            self.login_admin()
            # Calling an unknown or malformed action
            res = self.client.post('/api/ajax?action=invalid_action_name_xyz')
            self.assertEqual(res.status_code, 400)
            data = json.loads(res.data.decode('utf-8'))
            self.assertEqual(data.get('status'), 'error')
            # Verify no tracebacks in response
            self.assertNotIn('Traceback', res.data.decode('utf-8'))
            self.assertNotIn('File "', res.data.decode('utf-8'))

if __name__ == '__main__':
    unittest.main()
