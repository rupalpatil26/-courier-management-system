import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template
from db import execute_db

logger = logging.getLogger(__name__)

def create_in_app_notification(user_id: int, title: str, message: str) -> bool:
    """Create an in-app notification record for a registered user."""
    try:
        if user_id and int(user_id) > 0:
            execute_db(
                """
                INSERT INTO notifications (user_id, title, message, is_read, date_created)
                VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP)
                """,
                (int(user_id), title, message)
            )
            return True
    except Exception as e:
        logger.warning(f"Could not create in-app notification for user {user_id}: {e}")
    return False

def send_email(to_email: str, subject: str, html_content: str, text_content: str = None) -> bool:
    """
    Send an email via SMTP or gracefully fallback to offline logging.
    Guarantees no unhandled exceptions crash the request.
    """
    if not to_email or not str(to_email).strip():
        logger.info(f"Skipping email dispatch: No destination email specified for '{subject}'")
        return False

    to_email = str(to_email).strip()

    # Get configuration from Flask or environment
    mail_server = os.environ.get('MAIL_SERVER') or ''
    mail_port = int(os.environ.get('MAIL_PORT', 587))
    mail_use_tls = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')
    mail_username = os.environ.get('MAIL_USERNAME', '')
    mail_password = os.environ.get('MAIL_PASSWORD', '')
    mail_sender = os.environ.get('MAIL_DEFAULT_SENDER', 'notifications@courier.local')

    # If no SMTP server configured, record to log file gracefully
    if not mail_server or mail_server.lower() in ('none', 'off', 'false', ''):
        logger.info(
            f" [OFFLINE EMAIL DISPATCH] To: {to_email} | Subject: '{subject}' | (SMTP disabled/unconfigured)"
        )
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = mail_sender
        msg['To'] = to_email

        plain = text_content if text_content else f"{subject}\n\nPlease view this message in an HTML-compatible client."
        msg.attach(MIMEText(plain, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        server = smtplib.SMTP(mail_server, mail_port, timeout=5)
        if mail_use_tls:
            server.starttls()
        if mail_username and mail_password:
            server.login(mail_username, mail_password)
        server.send_message(msg)
        server.quit()

        logger.info(f" Successfully dispatched email to {to_email}: '{subject}'")
        return True
    except Exception as err:
        logger.warning(
            f" [SMTP DISPATCH FAILED - FALLBACK] Could not reach {mail_server}:{mail_port} ({err}). "
            f"Recorded offline notification for {to_email}: '{subject}'"
        )
        return False

def notify_parcel_created(parcel: dict, tracking_url: str):
    """Notify sender and recipient when a new parcel is created."""
    subject = f"Shipment Confirmed: #{parcel.get('reference_number')}"
    recipients = []
    if parcel.get('sender_email'):
        recipients.append(parcel['sender_email'])
    if parcel.get('recipient_email') and parcel['recipient_email'] not in recipients:
        recipients.append(parcel['recipient_email'])

    try:
        html = render_template('emails/parcel_created.html', **parcel, tracking_url=tracking_url)
    except Exception:
        html = f"<h2>Shipment Confirmed</h2><p>Parcel #{parcel.get('reference_number')} has been registered.</p>"

    for email in recipients:
        send_email(email, subject, html)

    # In-app notification if customer_id is linked
    if parcel.get('customer_id'):
        create_in_app_notification(
            parcel['customer_id'],
            "New Parcel Booked",
            f"Your parcel #{parcel.get('reference_number')} to {parcel.get('recipient_name')} is confirmed."
        )

def notify_out_for_delivery(parcel: dict, otp: str, tracking_url: str, staff_name: str = None):
    """Notify recipient with delivery OTP when parcel is out for delivery."""
    recipient_email = parcel.get('recipient_email')
    subject = f"Out for Delivery & OTP Code: #{parcel.get('reference_number')}"

    context = dict(parcel)
    context.update({
        'otp': otp,
        'tracking_url': tracking_url,
        'staff_name': staff_name or 'Courier Agent'
    })

    try:
        html = render_template('emails/delivery_otp.html', **context)
    except Exception:
        html = f"<h2>Out for Delivery</h2><p>Parcel #{parcel.get('reference_number')} is out for delivery. Your OTP is: <strong>{otp}</strong></p>"

    if recipient_email:
        send_email(recipient_email, subject, html)

    if parcel.get('customer_id'):
        create_in_app_notification(
            parcel['customer_id'],
            "Package Out For Delivery",
            f"Parcel #{parcel.get('reference_number')} is out for delivery. Delivery OTP: {otp}"
        )

def notify_parcel_delivered(parcel: dict, tracking_url: str, feedback_url: str = None):
    """Notify sender and recipient that the parcel was successfully delivered."""
    subject = f"Delivered: Parcel #{parcel.get('reference_number')}"
    context = dict(parcel)
    context.update({
        'tracking_url': tracking_url,
        'feedback_url': feedback_url or tracking_url
    })

    try:
        html = render_template('emails/parcel_delivered.html', **context)
    except Exception:
        html = f"<h2>Delivered</h2><p>Parcel #{parcel.get('reference_number')} was successfully delivered.</p>"

    for email in [parcel.get('recipient_email'), parcel.get('sender_email')]:
        if email:
            send_email(email, subject, html)

    if parcel.get('customer_id'):
        create_in_app_notification(
            parcel['customer_id'],
            "Parcel Delivered",
            f"Your parcel #{parcel.get('reference_number')} has been successfully delivered!"
        )

def notify_delivery_failed(parcel: dict, tracking_url: str, reason: str = None):
    """Notify customer when a delivery attempt fails."""
    subject = f"Delivery Attempt Unsuccessful: Parcel #{parcel.get('reference_number')}"
    context = dict(parcel)
    context.update({
        'tracking_url': tracking_url,
        'delivery_notes': reason or parcel.get('delivery_notes', '')
    })

    try:
        html = render_template('emails/delivery_failed.html', **context)
    except Exception:
        html = f"<h2>Delivery Attempt Unsuccessful</h2><p>Delivery for #{parcel.get('reference_number')} could not be completed.</p>"

    for email in [parcel.get('recipient_email'), parcel.get('sender_email')]:
        if email:
            send_email(email, subject, html)

    if parcel.get('customer_id'):
        create_in_app_notification(
            parcel['customer_id'],
            "Delivery Attempt Unsuccessful",
            f"Delivery attempt for #{parcel.get('reference_number')} failed. Reason: {reason or 'Address unavailable'}."
        )
