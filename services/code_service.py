import io
import base64
import logging
import qrcode
import barcode
from barcode.writer import ImageWriter

logger = logging.getLogger(__name__)

def generate_qr_code_bytes(data: str) -> bytes:
    """Generate raw PNG bytes for a QR code."""
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error generating QR code for {data}: {e}")
        return b""

def generate_qr_code_base64(data: str) -> str:
    """Generate a base64 Data URL for a QR code."""
    raw_bytes = generate_qr_code_bytes(data)
    if not raw_bytes:
        return ""
    b64 = base64.b64encode(raw_bytes).decode('utf-8')
    return f"data:image/png;base64,{b64}"

def generate_barcode_bytes(code: str) -> bytes:
    """Generate raw PNG bytes for a Code128 barcode."""
    try:
        code_str = str(code).strip()
        code128 = barcode.get('code128', code_str, writer=ImageWriter())
        buffer = io.BytesIO()
        code128.write(buffer, options={
            'module_width': 0.25,
            'module_height': 12.0,
            'font_size': 9,
            'text_distance': 3.5,
            'quiet_zone': 2.0,
            'write_text': True
        })
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error generating barcode for {code}: {e}")
        return b""

def generate_barcode_base64(code: str) -> str:
    """Generate a base64 Data URL for a Code128 barcode."""
    raw_bytes = generate_barcode_bytes(code)
    if not raw_bytes:
        return ""
    b64 = base64.b64encode(raw_bytes).decode('utf-8')
    return f"data:image/png;base64,{b64}"
