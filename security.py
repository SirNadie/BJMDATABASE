# security.py
import re

def validate_phone(phone):
    """Validate phone number format"""
    if not phone:
        return False
    pattern = r'^[\d\s\-\+\(\)]{7,15}$'
    return re.match(pattern, str(phone)) is not None

def validate_vin(vin):
    """Validate VIN format"""
    if not vin or vin in ["No VIN provided", "", None]:
        return True  # Empty VIN is allowed
    
    clean_vin = ''.join(vin.split()).upper()
    
    if len(clean_vin) not in [0, 7, 13, 17]:
        return False
    
    pattern = r'^[A-HJ-NPR-Z0-9]*$'
    return re.match(pattern, clean_vin) is not None

def sanitize_input(text):
    """Sanitize input text"""
    if text is None:
        return None
    return str(text).strip()

def validate_numeric(value, min_val=None, max_val=None):
    """Validate numeric values"""
    try:
        num = float(value)
        if min_val is not None and num < min_val:
            return False
        if max_val is not None and num > max_val:
            return False
        return True
    except (ValueError, TypeError):
        return False

def validate_email(email):
    """Validate email format"""
    if not email:
        return False
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return re.match(pattern, str(email)) is not None

def normalize_vin(vin):
    """Normalize VIN format"""
    if not vin:
        return ""
    return re.sub(r"\s+", "", vin).upper()