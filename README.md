# Courier Management System

A comprehensive web-based Courier Management System built with Python and Flask. The platform provides end-to-end parcel booking, tracking, status updates, invoice generation, customer/staff management, and role-based access control.

---

## Features

- **Parcel Management**: Create, update, assign, and track parcels seamlessly across branches.
- **Real-Time Tracking**: Public and authenticated parcel tracking with status timeline and milestones.
- **OTP-Verified Delivery**: Secure delivery verification with one-time password confirmation.
- **Role-Based Portals**:
  - **Admin**: Full system control, branch management, staff assignments, reports, and system settings.
  - **Staff**: Dedicated delivery dashboard, barcode/QR scanning, and status updates.
  - **Customer**: Parcel booking, live notifications, history, and invoice downloads.
- **Invoice & Email Notifications**: Automated PDF/HTML invoices and email status alerts.
- **Flexible Database**: Auto-migrating SQLite fallback with support for MySQL.

---

## Tech Stack

- **Backend**: Python 3, Flask
- **Database**: SQLite (default local) / MySQL
- **Frontend**: HTML5, Jinja2 Templates, Vanilla CSS, Bootstrap, AdminLTE
- **Testing**: Python `unittest` suite (33 unit and integration tests)

---

## Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/rupalpatil26/-courier-management-system.git
cd -courier-management-system
```

### 2. Set Up Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the example environment configuration:
```bash
cp .env.example .env
```

### 4. Run the Application
```bash
python3 app.py
```
Open your browser and navigate to `http://127.0.0.1:8080`.

---

## Running Tests

Run the complete test suite:
```bash
python3 -m unittest discover -s tests
```

---

## Default Admin Credentials
- **Username**: `admin` (or `admin@admin.com`)
- **Password**: `admin123`

---

## License
This project is open source and available under the [MIT License](LICENSE).
