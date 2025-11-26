# logic.py
import sqlite3
from datetime import datetime
import pandas as pd
from security import validate_phone, validate_vin, sanitize_input, validate_numeric
from db_utils import log_activity, get_db_connection

def _execute_query(query, params=(), fetch=None):
    """A helper function to execute database queries with a cached connection."""
    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")
    
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        if not query.strip().upper().startswith('SELECT'):
            conn.commit()
            
        if fetch == 'one':
            return cursor.fetchone()
        elif fetch == 'all':
            return cursor.fetchall()
        elif query.strip().upper().startswith('INSERT'):
            return cursor.lastrowid
        else:
            return None
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def add_new_client(phone, client_name, username):
    """Add a new client to the database with validation"""
    if not phone:
        raise ValueError("Phone number is required")
    
    if not validate_phone(phone):
        raise ValueError("Invalid phone number format")
    
    phone = sanitize_input(phone)
    client_name = sanitize_input(client_name)
    
    existing_client = _execute_query(
        "SELECT phone FROM clients WHERE phone = ?", 
        (phone,), 
        fetch='one'
    )
    
    if existing_client:
        raise ValueError(f"Client with phone {phone} already exists")
    
    result = _execute_query(
        "INSERT INTO clients (phone, client_name, created_by, last_updated_by) VALUES (?, ?, ?, ?)", 
        (phone, client_name, username, username)
    )
    
    log_activity(username, "add_client", f"Added client: {phone} - {client_name}", 
                "clients", phone, None, {"phone": phone, "client_name": client_name})
    return result

def add_vin_to_client(client_phone, vin_no, model, prod_yr, body, engine, code, transmission, username):
    """Add a VIN to a client with validation"""
    if not client_phone:
        raise ValueError("Client phone is required")
    
    if not validate_phone(client_phone):
        raise ValueError("Invalid client phone format")
    
    if vin_no:
        clean_vin = ''.join(vin_no.split()).upper()
        if not validate_vin(clean_vin):
            raise ValueError("Invalid VIN format. Must be 7, 13, or 17 alphanumeric characters, or empty.")
    else:
        clean_vin = None
    
    client_phone = sanitize_input(client_phone)
    clean_vin = sanitize_input(clean_vin) if clean_vin else None
    model = sanitize_input(model)
    prod_yr = sanitize_input(prod_yr)
    body = sanitize_input(body)
    engine = sanitize_input(engine)
    code = sanitize_input(code)
    transmission = sanitize_input(transmission)
    
    client_exists = _execute_query(
        "SELECT phone FROM clients WHERE phone = ?", 
        (client_phone,), 
        fetch='one'
    )
    
    if not client_exists:
        raise ValueError(f"Client with phone {client_phone} does not exist")
    
    result = _execute_query(
        "INSERT OR IGNORE INTO vins (vin_number, client_phone, model, prod_yr, body, engine, code, transmission, created_by, last_updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (clean_vin, client_phone, model, prod_yr, body, engine, code, transmission, username, username)
    )
    
    log_activity(username, "add_vin", f"Added VIN: {clean_vin} for client: {client_phone}", 
                "vins", clean_vin, None, {"vin_number": clean_vin, "client_phone": client_phone})
    return result

def add_supplier_to_part(part_id, supplier_name, buying_price, selling_price, delivery_time, username):
    """Add a supplier to a part with validation"""
    if not part_id:
        raise ValueError("Part ID is required")
    
    if not validate_numeric(part_id, min_val=1):
        raise ValueError("Invalid Part ID")
    
    if not supplier_name:
        raise ValueError("Supplier name is required")
    
    supplier_name = sanitize_input(supplier_name)
    delivery_time = sanitize_input(delivery_time)
    
    if not validate_numeric(buying_price, min_val=0):
        raise ValueError("Invalid buying price")
    
    if not validate_numeric(selling_price, min_val=0):
        raise ValueError("Invalid selling price")
    
    result = _execute_query(
        "INSERT INTO part_suppliers (part_id, supplier_name, buying_price, selling_price, delivery_time, created_by, last_updated_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (part_id, supplier_name, buying_price, selling_price, delivery_time, username, username)
    )
    
    log_activity(username, "add_supplier", f"Added supplier: {supplier_name} for part: {part_id}", 
                "part_suppliers", part_id, None, {"part_id": part_id, "supplier_name": supplier_name})
    return result

def add_part_to_vin(vin_number, client_phone, part_name, part_number, quantity, notes, suppliers, username):
    """Add a part to a VIN with transaction handling using a cached connection."""
    if not part_name and not part_number:
        raise ValueError("Part name or part number is required")
    
    date_added = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")
        
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO parts (vin_number, client_phone, part_name, part_number, quantity, notes, date_added, created_by, last_updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (vin_number, client_phone, part_name, part_number, quantity, notes, date_added, username, username)
        )
        part_id = cursor.lastrowid
        
        for supplier in suppliers:
            cursor.execute(
                "INSERT INTO part_suppliers (part_id, supplier_name, buying_price, selling_price, delivery_time, created_by, last_updated_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (part_id, supplier['name'], supplier['buying_price'], supplier['selling_price'], supplier['delivery_time'], username, username)
            )
        conn.commit()
        
        log_activity(username, "add_part", f"Added part: {part_name} ({part_number}) to VIN: {vin_number}", 
                    "parts", part_id, None, {"part_name": part_name, "part_number": part_number})
        return part_id
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during part/supplier addition: {e}")
        raise
    finally:
        conn.close()

def safe_add_part_to_vin(vin_number, client_phone, part_data, suppliers, username):
    """
    Safely add a part to a VIN with comprehensive error handling
    
    Args:
        vin_number: VIN to add part to
        client_phone: Client phone number
        part_data: Dictionary with part details
        suppliers: List of supplier dictionaries
        username: Username of the user adding the part
    
    Returns:
        part_id if successful, None otherwise
    """
    try:
        if not part_data.get('name') and not part_data.get('number'):
            raise ValueError("Part name or number is required")
        
        if not validate_numeric(part_data.get('quantity', 0), min_val=1):
            raise ValueError("Quantity must be at least 1")
        
        return add_part_to_vin(
            vin_number,
            client_phone,
            part_data['name'],
            part_data['number'],
            part_data['quantity'],
            part_data.get('notes', ''),
            suppliers,
            username  # Pass the username parameter
        )
    except Exception as e:
        print(f"Error adding part to VIN: {e}")
        raise

def add_part_without_vin(part_name, part_number, quantity, notes, client_phone, suppliers, username):
    """Add a part without a VIN with transaction handling using a cached connection."""
    if not part_name and not part_number:
        raise ValueError("Part name or part number is required")
    
    date_added = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")
        
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO parts (part_name, part_number, quantity, notes, date_added, client_phone, created_by, last_updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (part_name, part_number, quantity, notes, date_added, client_phone, username, username)
        )
        part_id = cursor.lastrowid
        
        for supplier in suppliers:
            cursor.execute(
                "INSERT INTO part_suppliers (part_id, supplier_name, buying_price, selling_price, delivery_time, created_by, last_updated_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (part_id, supplier['name'], supplier['buying_price'], supplier['selling_price'], supplier['delivery_time'], username, username)
            )
        conn.commit()
        
        log_activity(username, "add_part", f"Added part without VIN: {part_name} ({part_number}) for client: {client_phone}", 
                    "parts", part_id, None, {"part_name": part_name, "part_number": part_number})
        return part_id
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during part/supplier addition: {e}")
        raise
    finally:
        conn.close()

def delete_client(phone, username):
    """Delete a client and all associated data"""
    if not phone:
        raise ValueError("Phone number is required")
    
    client_name = _execute_query(
        "SELECT client_name FROM clients WHERE phone = ?", 
        (phone,), 
        fetch='one'
    )
    
    result = _execute_query("DELETE FROM clients WHERE phone = ?", (phone,))
    
    if client_name:
        log_activity(username, "delete_client", f"Deleted client: {phone} - {client_name[0]}", 
                    "clients", phone, {"phone": phone, "client_name": client_name[0]}, None)
    else:
        log_activity(username, "delete_client", f"Deleted client: {phone}", "clients", phone, None, None)
    
    return result

def delete_vin(vin_number, username, client_phone: str | None = None):
    """Delete a VIN and all associated parts.

    Handles special cases where VIN may be stored as NULL/blank by scoping to client_phone when provided.
    Returns number of rows deleted.
    """
    if vin_number is None or str(vin_number).strip() == "":
        vin = None
    else:
        vin = str(vin_number).strip()

    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()

        deleted = 0
        if vin is None or vin.lower() in {"none", "no vin provided"}:
            # Delete the placeholder/NULL VIN for this specific client only
            if client_phone:
                cur.execute(
                    "DELETE FROM vins WHERE client_phone = ? AND (vin_number IS NULL OR TRIM(vin_number) IN ('', 'None', 'none', 'No VIN provided'))",
                    (str(client_phone),),
                )
            else:
                # As a safeguard, do not mass-delete all NULL vins without scope
                return 0
            deleted = cur.rowcount
        else:
            # Exact match first (optionally scoped by client)
            if client_phone:
                cur.execute(
                    "DELETE FROM vins WHERE client_phone = ? AND vin_number = ?",
                    (str(client_phone), vin),
                )
            else:
                cur.execute("DELETE FROM vins WHERE vin_number = ?", (vin,))
            deleted = cur.rowcount

            # Fallback: trim/case-insensitive match
            if deleted == 0:
                if client_phone:
                    cur.execute(
                        "DELETE FROM vins WHERE client_phone = ? AND LOWER(TRIM(vin_number)) = LOWER(TRIM(?))",
                        (str(client_phone), vin),
                    )
                else:
                    cur.execute(
                        "DELETE FROM vins WHERE LOWER(TRIM(vin_number)) = LOWER(TRIM(?))",
                        (vin,),
                    )
                deleted = cur.rowcount

        conn.commit()

        action_detail = f"Deleted VIN: {vin if vin is not None else '[NULL/blank]'}"
        if deleted:
            log_activity(username, "delete_vin", action_detail, "vins", vin or "", None, None)
        else:
            log_activity(username, "delete_vin", f"Delete VIN attempted (no row matched): {vin}", "vins", vin or "", None, None)
        return deleted
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()

def delete_part(part_id, username):
    """Delete a part and all associated suppliers"""
    if not part_id:
        raise ValueError("Part ID is required")
    
    part_info = _execute_query(
        "SELECT part_name, part_number FROM parts WHERE id = ?", 
        (part_id,), 
        fetch='one'
    )
    
    result = _execute_query("DELETE FROM parts WHERE id = ?", (part_id,))
    
    if part_info:
        log_activity(username, "delete_part", f"Deleted part: {part_info[0]} ({part_info[1]}) - ID: {part_id}", 
                    "parts", part_id, {"part_name": part_info[0], "part_number": part_info[1]}, None)
    else:
        log_activity(username, "delete_part", f"Deleted part ID: {part_id}", "parts", part_id, None, None)
    
    return result

def update_client_and_vins(old_phone, new_phone, new_name, username):
    """Update client information and all associated references using a cached connection."""
    if not old_phone:
        raise ValueError("Old phone number is required")
    
    if not new_phone:
        raise ValueError("New phone number is required")
    
    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")
        
    try:
        # Get old values for logging
        old_client = _execute_query("SELECT * FROM clients WHERE phone = ?", (old_phone,), fetch='one')
        
        cursor = conn.cursor()
        cursor.execute("UPDATE clients SET phone = ?, client_name = ?, last_updated_by = ? WHERE phone = ?", 
                      (new_phone, new_name, username, old_phone))
        cursor.execute("UPDATE vins SET client_phone = ?, last_updated_by = ? WHERE client_phone = ?", 
                      (new_phone, username, old_phone))
        cursor.execute("UPDATE parts SET client_phone = ?, last_updated_by = ? WHERE client_phone = ?", 
                      (new_phone, username, old_phone))
        conn.commit()
        
        log_activity(username, "update_client", f"Updated client: {old_phone} -> {new_phone}, name: {new_name}", 
                    "clients", new_phone, {"phone": old_phone}, {"phone": new_phone, "client_name": new_name})
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during client update: {e}")
        raise
    finally:
        conn.close()

def update_part(part_id, part_name, part_number, quantity, notes, suppliers_data, username):
    """Update part information and suppliers with a cached connection."""
    if not part_id:
        raise ValueError("Part ID is required")
    
    if not part_name and not part_number:
        raise ValueError("Part name or part number is required")
    
    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")
        
    try:
        # Get old values for logging
        old_part = _execute_query("SELECT * FROM parts WHERE id = ?", (part_id,), fetch='one')
        old_suppliers = _execute_query("SELECT * FROM part_suppliers WHERE part_id = ?", (part_id,), fetch='all')
        
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE parts SET part_name = ?, part_number = ?, quantity = ?, notes = ?, last_updated_by = ? WHERE id = ?",
            (part_name, part_number, quantity, notes, username, part_id)
        )
        cursor.execute("DELETE FROM part_suppliers WHERE part_id = ?", (part_id, ))
        for supplier in suppliers_data:
            cursor.execute(
                "INSERT INTO part_suppliers (part_id, supplier_name, buying_price, selling_price, delivery_time, created_by, last_updated_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (part_id, supplier['name'], supplier['buying_price'], supplier['selling_price'], supplier['delivery_time'], username, username)
            )
        conn.commit()
        
        log_activity(username, "update_part", f"Updated part: {part_name} ({part_number}) - ID: {part_id}", 
                    "parts", part_id, 
                    {"part_name": old_part[3], "part_number": old_part[4], "quantity": old_part[5]},
                    {"part_name": part_name, "part_number": part_number, "quantity": quantity})
        return part_id
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during part update: {e}")
        raise
    finally:
        conn.close()

def get_clients_by_page(page, page_size=20):
    """Fetch clients for a specific page, ordered by last update."""
    offset = page * page_size
    query = f"SELECT * FROM clients ORDER BY last_updated DESC LIMIT ? OFFSET ?"
    results = _execute_query(query, (page_size, offset), fetch='all')
    return results

def get_parts_by_page(page, page_size=20):
    """Fetch parts for a specific page, ordered by last update."""
    offset = page * page_size
    query = f"SELECT * FROM parts ORDER BY last_updated DESC LIMIT ? OFFSET ?"
    results = _execute_query(query, (page_size, offset), fetch='all')
    return results

def count_table_rows(table_name):
    """Count total rows in a table."""
    query = f"SELECT COUNT(*) FROM {table_name}"
    count = _execute_query(query, fetch='one')
    return count[0] if count else 0

def get_client_by_phone(phone):
    """Retrieve client details by phone number."""
    return _execute_query("SELECT * FROM clients WHERE phone = ?", (phone,), fetch='one')

def get_vins_for_client(phone):
    """Retrieve all VINs for a given client phone number."""
    return _execute_query("SELECT * FROM vins WHERE client_phone = ?", (phone,), fetch='all')
    
def get_parts_for_vin(vin_number):
    """Retrieve all parts for a given VIN."""
    return _execute_query("SELECT * FROM parts WHERE vin_number = ?", (vin_number,), fetch='all')

def get_parts_for_client_without_vin(client_phone):
    """Retrieve parts added for a client without a VIN."""
    return _execute_query("SELECT * FROM parts WHERE vin_number IS NULL AND client_phone = ?", (client_phone,), fetch='all')

def get_vin_details(vin_number):
    """Retrieve VIN details."""
    return _execute_query("SELECT * FROM vins WHERE vin_number = ?", (vin_number,), fetch='one')

def get_suppliers_for_part(part_id):
    """Retrieve suppliers for a given part."""
    return _execute_query("SELECT * FROM part_suppliers WHERE part_id = ?", (part_id,), fetch='all')

def update_supplier(supplier_id: int, supplier_name: str, buying_price: float, selling_price: float, delivery_time: str, username: str):
    """Update a single supplier row for a part."""
    if not supplier_id:
        raise ValueError("Supplier ID is required")
    if not supplier_name:
        raise ValueError("Supplier name is required")
    if not validate_numeric(buying_price, min_val=0):
        raise ValueError("Invalid buying price")
    if not validate_numeric(selling_price, min_val=0):
        raise ValueError("Invalid selling price")

    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")
    try:
        cur = conn.cursor()
        old_row = cur.execute("SELECT part_id, supplier_name, buying_price, selling_price, delivery_time FROM part_suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if not old_row:
            raise ValueError("Supplier not found")
        cur.execute(
            "UPDATE part_suppliers SET supplier_name = ?, buying_price = ?, selling_price = ?, delivery_time = ?, last_updated_by = ? WHERE id = ?",
            (supplier_name, float(buying_price or 0), float(selling_price or 0), delivery_time or '', username, supplier_id)
        )
        conn.commit()
        log_activity(
            username,
            "update_supplier",
            f"Updated supplier {supplier_id} for part {old_row[0]}",
            "part_suppliers",
            str(supplier_id),
            {"supplier_name": old_row[1], "buying_price": old_row[2], "selling_price": old_row[3], "delivery_time": old_row[4]},
            {"supplier_name": supplier_name, "buying_price": float(buying_price or 0), "selling_price": float(selling_price or 0), "delivery_time": delivery_time or ''},
        )
        return True
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during supplier update: {e}")
        raise
    finally:
        conn.close()

def delete_supplier(supplier_id: int, username: str):
    """Delete a supplier from part_suppliers."""
    if not supplier_id:
        raise ValueError("Supplier ID is required")
    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")
    try:
        cur = conn.cursor()
        old_row = cur.execute("SELECT part_id, supplier_name, buying_price, selling_price, delivery_time FROM part_suppliers WHERE id = ?", (supplier_id,)).fetchone()
        cur.execute("DELETE FROM part_suppliers WHERE id = ?", (supplier_id,))
        conn.commit()
        log_activity(
            username,
            "delete_supplier",
            f"Deleted supplier {supplier_id} for part {old_row[0] if old_row else ''}",
            "part_suppliers",
            str(supplier_id),
            {"supplier_name": old_row[1] if old_row else None},
            None,
        )
        return True
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during supplier deletion: {e}")
        raise
    finally:
        conn.close()

def get_part_details(part_id):
    """Retrieve a single part details by its ID."""
    return _execute_query("SELECT * FROM parts WHERE id = ?", (part_id,), fetch='one')

def get_client_info_for_export(phone):
    """Retrieve client and associated VINs and parts for a quote or invoice."""
    client_info = _execute_query("SELECT * FROM clients WHERE phone = ?", (phone,), fetch='one')
    if not client_info:
        return None
    
    vins = _execute_query("SELECT vin_number, model FROM vins WHERE client_phone = ?", (phone,), fetch='all')
    parts = _execute_query("SELECT id, vin_number, part_name, part_number, quantity, notes FROM parts WHERE client_phone = ?", (phone,), fetch='all')
    
    parts_with_suppliers = []
    for part in parts:
        part_id, vin, name, number, qty, notes = part
        suppliers = get_suppliers_for_part(part_id)
        parts_with_suppliers.append({
            'id': part_id,
            'vin_number': vin,
            'part_name': name,
            'part_number': number,
            'quantity': qty,
            'notes': notes,
            'suppliers': suppliers
        })
        
    return {
        'client': client_info,
        'vins': vins,
        'parts': parts_with_suppliers
    }

def get_quote_data(phone, selected_vin, selected_part_ids):
    """Retrieve data for generating a quote."""
    client_info = get_client_by_phone(phone)
    if not client_info:
        return None
    
    vin_info = None
    if selected_vin:
        vin_info = get_vin_details(selected_vin)
        
    parts_data = []
    for part_id in selected_part_ids:
        part_details = get_part_details(part_id)
        if part_details:
            suppliers = get_suppliers_for_part(part_id)
            part_dict = dict(zip(['id', 'vin_number', 'client_phone', 'part_name', 'part_number', 'quantity', 'notes', 'date_added', 'created_date', 'last_updated'], part_details))
            part_dict['suppliers'] = suppliers
            parts_data.append(part_dict)
            
    return {
        'client': client_info,
        'vin': vin_info,
        'parts': parts_data
    }

def move_part_to_vin(part_id: int, new_vin_number: str, username: str):
    """Move an existing part to a registered VIN.

    - Validates target VIN exists and fetches its client_phone.
    - Updates parts.vin_number and keeps client_phone consistent with the VIN's client.
    - Logs the activity.
    """
    if not part_id or not new_vin_number:
        raise ValueError("Part ID and target VIN are required")

    clean_vin = ''.join(str(new_vin_number).split()).upper()
    if not validate_vin(clean_vin):
        raise ValueError("Invalid VIN format. Must be 7, 13, or 17 alphanumeric characters.")

    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")

    try:
        cur = conn.cursor()
        # Get existing part
        part_row = cur.execute("SELECT id, vin_number, client_phone, part_name, part_number FROM parts WHERE id = ?", (part_id,)).fetchone()
        if not part_row:
            raise ValueError("Part not found")
        old_vin = part_row[1]

        # Target VIN must exist
        vin_row = cur.execute("SELECT vin_number, client_phone FROM vins WHERE vin_number = ?", (clean_vin,)).fetchone()
        if not vin_row:
            raise ValueError("Target VIN not found")
        target_phone = vin_row[1]

        # Update part assignment
        cur.execute(
            "UPDATE parts SET vin_number = ?, client_phone = ?, last_updated_by = ? WHERE id = ?",
            (clean_vin, target_phone, username, part_id)
        )
        conn.commit()

        log_activity(
            username,
            "move_part",
            f"Moved part ID {part_id} from VIN {old_vin or 'None'} to {clean_vin}",
            "parts",
            str(part_id),
            {"vin_number": old_vin},
            {"vin_number": clean_vin, "client_phone": target_phone},
        )
        return True
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during moving part: {e}")
        raise
    finally:
        conn.close()

def update_vin(old_vin_number: str, new_vin_number: str, model: str, prod_yr: str, body: str, engine: str, code: str, transmission: str, username: str):
    """Update VIN details. If VIN number changes, update dependent parts as well."""
    if not old_vin_number:
        raise ValueError("Old VIN is required")

    if new_vin_number:
        clean_new_vin = ''.join(new_vin_number.split()).upper()
        if not validate_vin(clean_new_vin):
            raise ValueError("Invalid VIN format. Must be 7, 13, or 17 alphanumeric characters.")
    else:
        raise ValueError("New VIN cannot be empty")

    conn = get_db_connection()
    if conn is None:
        raise ConnectionError("Database connection not available")

    try:
        cur = conn.cursor()
        # Check existence of old VIN
        row = cur.execute("SELECT vin_number, client_phone FROM vins WHERE vin_number = ?", (old_vin_number,)).fetchone()
        if not row:
            raise ValueError("VIN not found")
        client_phone = row[1]

        # If VIN is changing, ensure no conflict
        if clean_new_vin != old_vin_number:
            conflict = cur.execute("SELECT 1 FROM vins WHERE vin_number = ?", (clean_new_vin,)).fetchone()
            if conflict:
                raise ValueError("Another record already uses the new VIN number")

        # Update vins record (including possibly the VIN PK)
        cur.execute(
            "UPDATE vins SET vin_number = ?, model = ?, prod_yr = ?, body = ?, engine = ?, code = ?, transmission = ?, last_updated_by = ? WHERE vin_number = ?",
            (clean_new_vin, model, prod_yr, body, engine, code, transmission, username, old_vin_number)
        )

        # Update dependent parts' vin_number if VIN changed
        if clean_new_vin != old_vin_number:
            cur.execute(
                "UPDATE parts SET vin_number = ?, last_updated_by = ? WHERE vin_number = ?",
                (clean_new_vin, username, old_vin_number)
            )

        conn.commit()
        log_activity(
            username,
            "update_vin",
            f"Updated VIN {old_vin_number} -> {clean_new_vin} for client {client_phone}",
            "vins",
            clean_new_vin,
            {"vin_number": old_vin_number},
            {"vin_number": clean_new_vin, "model": model, "prod_yr": prod_yr, "body": body, "engine": engine, "code": code, "transmission": transmission},
        )
        return clean_new_vin
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error during VIN update: {e}")
        raise
    finally:
        conn.close()

def search_db(query):
    """Perform a comprehensive search across all relevant tables safely."""
    if not query:
        return {'clients': pd.DataFrame(), 'vins': pd.DataFrame(), 'parts': pd.DataFrame()}
    
    conn = get_db_connection()
    if conn is None:
        return {'clients': pd.DataFrame(), 'vins': pd.DataFrame(), 'parts': pd.DataFrame()}

    # Use parameterized queries to prevent SQL injection
    search_pattern = f"%{query}%"
    
    try:
        df_clients = pd.read_sql_query(
            "SELECT * FROM clients WHERE phone LIKE ? OR client_name LIKE ?", 
            conn, params=[search_pattern, search_pattern]
        )
        df_vins = pd.read_sql_query(
            "SELECT * FROM vins WHERE vin_number LIKE ? OR model LIKE ?", 
            conn, params=[search_pattern, search_pattern]
        )
        df_parts = pd.read_sql_query(
            "SELECT * FROM parts WHERE part_name LIKE ? OR part_number LIKE ? OR notes LIKE ?", 
            conn, params=[search_pattern, search_pattern, search_pattern]
        )
    except Exception as e:
        print(f"Error during search: {e}")
        return {'clients': pd.DataFrame(), 'vins': pd.DataFrame(), 'parts': pd.DataFrame()}
    finally:
        conn.close()
    
    return {
        'clients': df_clients,
        'vins': df_vins,
        'parts': df_parts
    }
