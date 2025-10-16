from datetime import datetime
from fpdf import FPDF

# --- YOUR COMPANY INFO ---
COMPANY_INFO = {
    "name": "Brent J. Marketing",
    "distributor_line": "Distributors of European mechanical & body parts",
    "address_line1": "#46 Eastern Main Road, Silver Mill",
    "address_line2": "Trinidad and Tobago, San Juan",
    "specialties": [
        "3M reflective, aluminum shapes, sheets, safety equipment",
        "Traffic and road marking signage",
        "GLOUDS water pumps & parts"
    ],
    "phone1": "868-675-7294",
    "phone2": "868-713-2990",
    "phone3": "868-743-9004",
    "email": "brentjmarketingcompany@yahoo.com",
    "website": "bmwpartstt.com"
}


def generate_pdf(
    client_info,
    parts_data,
    total_quote_amount,
    manual_deposit,
    bill_to_info=None,
    ship_to_info=None,
    delivery_time=None,
    document_number=None,
    document_type: str = 'quote'
):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=16)

    # --- COMPANY INFO HEADER ---
    pdf.set_font("Arial", style="B", size=14)
    pdf.cell(200, 8, txt=COMPANY_INFO["name"], ln=True, align="C")

    # Distributors line
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 4, txt=COMPANY_INFO["distributor_line"], ln=True, align="C")

    # Address and Contact Info
    pdf.set_font("Arial", size=8)
    pdf.cell(200, 4, txt=COMPANY_INFO["address_line1"], ln=True, align="C")
    pdf.cell(200, 4, txt=COMPANY_INFO["address_line2"], ln=True, align="C")

    # Specialties line
    for specialty in COMPANY_INFO["specialties"]:
        pdf.cell(200, 4, txt=specialty, ln=True, align="C")

    pdf.cell(200, 4, txt=f"Phones: {COMPANY_INFO['phone1']} / {COMPANY_INFO['phone2']} / {COMPANY_INFO['phone3']}", ln=True, align="C")
    pdf.cell(200, 4, txt=f"Email: {COMPANY_INFO['email']}", ln=True, align="C")
    pdf.cell(200, 4, txt=f"Website: {COMPANY_INFO['website']}", ln=True, align="C")
    pdf.ln(5)  # Add a line break for spacing

    # Quote Title, Number, and Date
    pdf.set_font("Arial", size=16)
    title_text = "QUOTATION" if document_type == 'quote' else "INVOICE"
    number_text = (
        f"Quotation Number: {document_number}"
        if document_type == 'quote'
        else f"Invoice Number: {document_number}"
    )

    pdf.cell(200, 10, txt=title_text, ln=True, align="C")
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=number_text, ln=True, align="R")
    pdf.cell(200, 10, txt=f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True, align="R")
    pdf.ln(5)

    # --- BILL TO / SHIP TO SECTION ---
    current_y = pdf.get_y()

    # Bill To
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(100, 10, txt="Bill to:", ln=False, align="L")

    # Ship To
    pdf.set_x(110)
    pdf.cell(100, 10, txt="Ship to:", ln=True, align="L")

    pdf.set_font("Arial", size=12)
    pdf.set_y(current_y + 10)

    bill_to_name = bill_to_info['name'] if bill_to_info and bill_to_info['name'] else client_info['name']
    bill_to_address = bill_to_info['address'] if bill_to_info and bill_to_info['address'] else f"Phone: {client_info['phone']}"

    pdf.cell(100, 5, txt=f"{bill_to_name}", ln=False, align="L")

    ship_to_name = ship_to_info['name'] if ship_to_info and ship_to_info['name'] else ""
    ship_to_address = ship_to_info['address'] if ship_to_info and ship_to_info['address'] else ""

    pdf.set_x(110)
    pdf.cell(100, 5, txt=f"{ship_to_name}", ln=True, align="L")

    bill_to_address_lines = bill_to_address.split('\n')
    pdf.set_x(10)
    for line in bill_to_address_lines:
        pdf.cell(100, 5, txt=line, ln=True, align="L")

    ship_to_address_lines = ship_to_address.split('\n')
    pdf.set_xy(110, current_y + 15)
    for line in ship_to_address_lines:
        pdf.cell(100, 5, txt=line, ln=True, align="L")

    # Add VIN below the addresses, if applicable
    pdf.ln(5)
    if client_info.get('vin_number') and client_info['vin_number'] != 'Show All Parts':
        pdf.cell(100, 5, txt=f"VIN: {client_info['vin_number']}", ln=True, align="L")
        pdf.ln(5)

    pdf.ln(5)

    # Parts Table Header
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(80, 10, txt="Part Name", border=1, align="C")
    pdf.cell(30, 10, txt="Quantity", border=1, align="C")
    pdf.cell(40, 10, txt="Unit Price ($)", border=1, align="C")
    pdf.cell(40, 10, txt="Total Price ($)", border=1, align="C", ln=True)

    # Parts Table Content
    pdf.set_font("Arial", size=12)
    for part in parts_data:
        total_price = part['quantity'] * part['price']

        pdf.cell(80, 10, txt=str(part['name']), border=1, align="L")
        pdf.cell(30, 10, txt=str(part['quantity']), border=1, align="C")
        pdf.cell(40, 10, txt=f"{part['price']:.2f}", border=1, align="R")
        pdf.cell(40, 10, txt=f"{total_price:.2f}", border=1, align="R", ln=True)

    # Total rows
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(150, 10, txt="TOTAL", border=1, align="R")
    pdf.cell(40, 10, txt=f"{total_quote_amount:.2f}", border=1, align="R", ln=True)

    if manual_deposit > 0:
        pdf.cell(150, 10, txt="DEPOSIT", border=1, align="R")
        pdf.cell(40, 10, txt=f"{manual_deposit:.2f}", border=1, align="R", ln=True)
        pdf.cell(150, 10, txt="BALANCE DUE", border=1, align="R")
        pdf.cell(40, 10, txt=f"{total_quote_amount - manual_deposit:.2f}", border=1, align="R", ln=True)

    # New Terms of Sale and Delivery
    pdf.ln(10)
    pdf.set_font("Arial", size=10)

    # Handle IN STOCK vs delivery time - FIXED
    if delivery_time == "IN STOCK":
        pdf.cell(200, 5, txt="* IN STOCK - Available for immediate pickup/shipment", ln=True)
    else:
        pdf.cell(200, 5, txt=f"* DELIVERY WITHIN {delivery_time} BUSINESS DAYS AFTER ORDER CONFIRMATION", ln=True)

    pdf.cell(200, 5, txt="* An 80% Deposit required upon Order Confirmation", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", style="B", size=10)
    pdf.cell(200, 5, txt="TERMS OF SALE:", ln=True)
    pdf.set_font("Arial", size=8)
    terms_text = (
        "No returns accepted after 7 days from invoice date. "
        "ALL Special Orders must be paid for in advance. "
        "A 20% Restocking Fee and Credit Card Fee applies to returned items. "
        "No return/refund on all special order items Electrical, electronic parts and fuel pumps, warranty is against the manufacture. "
        "Any charges incurred by this company in the recovery of any unpaid invoice balance on account or dishonoured cheque will be at the buyer's expense. "
        "The seller shall retain absolute title ownership and right to possession of the goods until full payment is received. "
        "A 2% finance charge for all account balances over 30 days. "
        "Shipping delays subject to airline, customs or natural disasters are not the responsibility of the seller."
    )
    pdf.multi_cell(0, 4, txt=terms_text)

    return pdf.output(dest='S')

