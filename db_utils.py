# db_utils.py
import sqlite3
import pandas as pd
import streamlit as st
import os
import io
import zipfile
from datetime import datetime
import json
import hashlib
try:
    import bcrypt  # Optional; fallback to SHA-256 if unavailable
except Exception:  # pragma: no cover
    bcrypt = None

# Use relative path for deployment
DB_NAME = 'brent_j_marketing.db'

from contextlib import contextmanager

def get_db_connection():
    """Get database connection (Legacy - prefer using get_db_connection_ctx)"""
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except Exception as e:
        print(f"Failed to connect to the database: {e}")
        return None

@contextmanager
def get_db_connection_ctx():
    """Context manager for database connections"""
    conn = None
    try:
        conn = get_db_connection()
        if conn:
            yield conn
        else:
            raise ConnectionError("Failed to acquire database connection")
    finally:
        if conn:
            conn.close()

def create_tables():
    """Create database tables if they don't exist"""
    try:
        with get_db_connection_ctx() as conn:
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_login TEXT,
                    is_active INTEGER DEFAULT 1
                )
            ''')
            
            # Create clients table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    phone TEXT PRIMARY KEY,
                    client_name TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    last_updated_by TEXT
                )
            ''')
            
            # Create vins table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vins (
                    vin_number TEXT PRIMARY KEY,
                    client_phone TEXT,
                    model TEXT,
                    prod_yr TEXT,
                    body TEXT,
                    engine TEXT,
                    code TEXT,
                    transmission TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    last_updated_by TEXT,
                    FOREIGN KEY(client_phone) REFERENCES clients(phone) ON DELETE CASCADE
                )
            ''')
            
            # Create parts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS parts (
                    id INTEGER PRIMARY KEY,
                    vin_number TEXT,
                    client_phone TEXT,
                    part_name TEXT,
                    part_number TEXT,
                    quantity INTEGER,
                    notes TEXT,
                    date_added TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    last_updated_by TEXT,
                    FOREIGN KEY(vin_number) REFERENCES vins(vin_number) ON DELETE CASCADE,
                    FOREIGN KEY(client_phone) REFERENCES clients(phone) ON DELETE CASCADE
                )
            ''')
            
            # Create part_suppliers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS part_suppliers (
                    id INTEGER PRIMARY KEY,
                    part_id INTEGER,
                    supplier_name TEXT,
                    buying_price REAL,
                    selling_price REAL,
                    delivery_time TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    last_updated_by TEXT,
                    FOREIGN KEY(part_id) REFERENCES parts(id) ON DELETE CASCADE
                )
            ''')
            
            # Create activity_log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT,
                    username TEXT,
                    action TEXT,
                    details TEXT,
                    table_name TEXT,
                    record_id TEXT,
                    old_values TEXT,
                    new_values TEXT
                )
            ''')
            
            # Create default admin user
            if bcrypt:
                admin_password_hash = bcrypt.hashpw("admin".encode(), bcrypt.gensalt()).decode()
            else:
                admin_password_hash = hashlib.sha256("admin".encode()).hexdigest()
            cursor.execute('''
                INSERT OR IGNORE INTO users (username, password_hash, role) 
                VALUES (?, ?, ?)
            ''', ('admin', admin_password_hash, 'admin'))
            
            conn.commit()
    except sqlite3.Error as e:
        print(f"Error creating tables: {e}")

def migrate_schema():
    """Migrate database schema if needed"""
    try:
        with get_db_connection_ctx() as conn:
            cursor = conn.cursor()
            
            # Check if old columns exist and remove them
            cursor.execute("PRAGMA table_info(parts)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'deposit' in columns:
                cursor.execute("ALTER TABLE parts DROP COLUMN deposit")
            if 'balance' in columns:
                cursor.execute("ALTER TABLE parts DROP COLUMN balance")
                
            # Ensure users.is_active exists
            cursor.execute("PRAGMA table_info(users)")
            user_cols = [col[1] for col in cursor.fetchall()]
            if 'is_active' not in user_cols:
                cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")

            conn.commit()
    except sqlite3.Error as e:
        print(f"Migration error: {e}")

@st.cache_data(ttl=300)
def load_data():
    """Load all data from database"""
    try:
        with get_db_connection_ctx() as conn:
            df_clients = pd.read_sql_query("SELECT * FROM clients", conn)
            df_vins = pd.read_sql_query("SELECT * FROM vins", conn)
            df_parts = pd.read_sql_query("SELECT * FROM parts", conn)
            df_part_suppliers = pd.read_sql_query("SELECT * FROM part_suppliers", conn)
            return df_clients, df_vins, df_parts, df_part_suppliers
    except Exception as e:
        print(f"Error loading data: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def get_activity_logs(username=None, limit=100):
    """Get activity logs"""
    try:
        with get_db_connection_ctx() as conn:
            query = "SELECT * FROM activity_log"
            params = []
            if username:
                query += " WHERE username = ?"
                params.append(username)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        print(f"Error getting activity logs: {e}")
        return pd.DataFrame()

def database_maintenance():
    """Perform database maintenance"""
    try:
        with get_db_connection_ctx() as conn:
            conn.execute("VACUUM")
            conn.execute("ANALYZE")
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result[0] == "ok"
    except Exception as e:
        print(f"Database maintenance error: {e}")
        return False

def log_activity(username, action, details, table_name=None, record_id=None, old_values=None, new_values=None):
    """Log user activity to the database"""
    try:
        with get_db_connection_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO activity_log (timestamp, username, action, details, table_name, record_id, old_values, new_values)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    username,
                    action,
                    details,
                    table_name,
                    record_id,
                    json.dumps(old_values) if old_values else None,
                    json.dumps(new_values) if new_values else None
                )
            )
            conn.commit()
    except sqlite3.Error as e:
        print(f"Error logging activity: {e}")

# ===== User management helpers (admin UI) =====
def _hash_password(password: str) -> str:
    if bcrypt:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return hashlib.sha256(password.encode()).hexdigest()

def list_users():
    """Return DataFrame of users without password hashes."""
    try:
        with get_db_connection_ctx() as conn:
            return pd.read_sql_query(
                "SELECT username, role, created_date, last_login, COALESCE(is_active, 1) as is_active FROM users ORDER BY username",
                conn
            )
    except Exception as e:
        print(f"Error listing users: {e}")
        return pd.DataFrame()

def _users_has_is_active(conn) -> bool:
    try:
        cur = conn.execute("PRAGMA table_info(users)")
        return any(row[1] == 'is_active' for row in cur.fetchall())
    except Exception:
        return False

def count_admins() -> int:
    try:
        with get_db_connection_ctx() as conn:
            if _users_has_is_active(conn):
                cur = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND COALESCE(is_active,1)=1")
            else:
                cur = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except Exception as e:
        print(f"Error counting admins: {e}")
        return 0

def create_user(username: str, password: str, role: str, actor: str) -> tuple[bool, str]:
    if not username or not password:
        return False, "Username and password are required"
    if role not in ("user", "admin"):
        return False, "Invalid role"
    try:
        with get_db_connection_ctx() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            if cur.fetchone():
                return False, "Username already exists"
            pwd_hash = _hash_password(password)
            # Try to use is_active column if available
            if _users_has_is_active(conn):
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, created_date, is_active) VALUES (?, ?, ?, ?, 1)",
                    (username, pwd_hash, role, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
            else:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, created_date) VALUES (?, ?, ?, ?)",
                    (username, pwd_hash, role, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
            conn.commit()
            log_activity(actor, "create_user", f"Created user '{username}' with role '{role}'", "users", username)
            # If a new admin was created and a default 'admin' exists, consider deactivating 'admin'
            if role == 'admin' and username != 'admin' and _users_has_is_active(conn):
                try:
                    # Only if there is at least one other active admin (the new one)
                    cur.execute("UPDATE users SET is_active = 0 WHERE username = 'admin' AND COALESCE(is_active,1)=1")
                    conn.commit()
                except Exception:
                    pass
            return True, "User created"
    except sqlite3.Error as e:
        return False, f"DB error: {e}"

def update_user_password(username: str, new_password: str, actor: str) -> tuple[bool, str]:
    if not username or not new_password:
        return False, "Username and new password are required"
    try:
        with get_db_connection_ctx() as conn:
            pwd_hash = _hash_password(new_password)
            cur = conn.cursor()
            cur.execute("UPDATE users SET password_hash = ? WHERE username = ?", (pwd_hash, username))
            if cur.rowcount == 0:
                return False, "User not found"
            conn.commit()
            log_activity(actor, "update_password", f"Updated password for '{username}'", "users", username)
            return True, "Password updated"
    except sqlite3.Error as e:
        return False, f"DB error: {e}"

def update_user_role(username: str, new_role: str, actor: str) -> tuple[bool, str]:
    if new_role not in ("user", "admin"):
        return False, "Invalid role"
    try:
        with get_db_connection_ctx() as conn:
            # Prevent removing the last admin
            if new_role == 'user':
                cur = conn.execute("SELECT role FROM users WHERE username = ?", (username,))
                row = cur.fetchone()
                if not row:
                    return False, "User not found"
                if row[0] == 'admin' and count_admins() <= 1:
                    return False, "Cannot demote the last admin"
            cur = conn.cursor()
            cur.execute("UPDATE users SET role = ? WHERE username = ?", (new_role, username))
            if cur.rowcount == 0:
                return False, "User not found"
            conn.commit()
            log_activity(actor, "update_role", f"Changed role for '{username}' to '{new_role}'", "users", username)
            return True, "Role updated"
    except sqlite3.Error as e:
        return False, f"DB error: {e}"

def set_user_active(username: str, active: bool, actor: str) -> tuple[bool, str]:
    """Activate/Deactivate a user account with safety checks."""
    try:
        with get_db_connection_ctx() as conn:
            if not _users_has_is_active(conn):
                return False, "This operation is not supported on current schema"
            # Prevent deactivating self
            if actor == username:
                return False, "You cannot deactivate your own account"
            # Prevent deactivating last admin
            cur = conn.execute("SELECT role, COALESCE(is_active,1) FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            if not row:
                return False, "User not found"
            role, is_active = row
            if active:
                # Reactivate
                conn.execute("UPDATE users SET is_active = 1 WHERE username = ?", (username,))
                conn.commit()
                log_activity(actor, "activate_user", f"Reactivated user '{username}'", "users", username)
                return True, "User reactivated"
            else:
                if role == 'admin' and count_admins() <= 1:
                    return False, "Cannot deactivate the last admin"
                conn.execute("UPDATE users SET is_active = 0 WHERE username = ?", (username,))
                conn.commit()
                log_activity(actor, "deactivate_user", f"Deactivated user '{username}'", "users", username)
                return True, "User deactivated"
    except sqlite3.Error as e:
        return False, f"DB error: {e}"

def _apply_basic_filters(df: pd.DataFrame, table: str, filters: dict) -> pd.DataFrame:
    """Apply simple filters to a DataFrame based on provided filter dict."""
    if df is None or df.empty:
        return df
    if not filters:
        return df

    df_f = df
    client_phone = filters.get('client_phone')
    vin_number = filters.get('vin_number')

    if table == 'clients':
        if client_phone:
            df_f = df_f[df_f['phone'].astype(str) == str(client_phone)]
    elif table in ('vins', 'parts'):
        if client_phone and 'client_phone' in df_f.columns:
            df_f = df_f[df_f['client_phone'].astype(str) == str(client_phone)]
        if vin_number and 'vin_number' in df_f.columns:
            df_f = df_f[df_f['vin_number'].astype(str) == str(vin_number)]
    return df_f

def export_filtered_data(filters=None, format_type: str = 'csv'):
    """Export selected tables with optional filters.

    Args:
        filters: dict with optional keys: 'include' list of table names, 'client_phone', 'vin_number'
        format_type: 'csv' (zip with CSVs) or 'excel'

    Returns:
        (bytes, mime_type)
    """
    try:
        with get_db_connection_ctx() as conn:
            include = (filters or {}).get('include') or [
                'clients', 'vins', 'parts', 'part_suppliers'
            ]
            include = [t for t in include if t in ['clients', 'vins', 'parts', 'part_suppliers']]

            # Load dataframes
            dfs: dict[str, pd.DataFrame] = {}
            try:
                if 'clients' in include:
                    dfs['clients'] = pd.read_sql_query("SELECT * FROM clients", conn)
                    dfs['clients'] = _apply_basic_filters(dfs['clients'], 'clients', filters or {})
                if 'vins' in include:
                    dfs['vins'] = pd.read_sql_query("SELECT * FROM vins", conn)
                    dfs['vins'] = _apply_basic_filters(dfs['vins'], 'vins', filters or {})
                if 'parts' in include or 'part_suppliers' in include:
                    df_parts = pd.read_sql_query("SELECT * FROM parts", conn)
                    df_parts = _apply_basic_filters(df_parts, 'parts', filters or {})
                    if 'parts' in include:
                        dfs['parts'] = df_parts
                    # part_suppliers depends on part ids
                    if 'part_suppliers' in include:
                        if not df_parts.empty:
                            part_ids = df_parts['id'].dropna().astype(int).tolist()
                            # build parameterized IN clause safely
                            placeholders = ','.join(['?'] * len(part_ids))
                            query = f"SELECT * FROM part_suppliers WHERE part_id IN ({placeholders})"
                            dfs['part_suppliers'] = pd.read_sql_query(query, conn, params=part_ids)
                        else:
                            dfs['part_suppliers'] = pd.DataFrame(columns=[
                                'id', 'part_id', 'supplier_name', 'buying_price', 'selling_price', 'delivery_time',
                                'created_date', 'last_updated', 'created_by', 'last_updated_by'
                            ])
            except Exception as e:  # pragma: no cover
                raise RuntimeError(f"Export query failed: {e}")

            # Prepare output
            if format_type.lower() == 'excel':
                buffer = io.BytesIO()
                try:
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        for name, df in dfs.items():
                            # Ensure sheet names are valid and unique
                            sheet_name = name[:31]
                            df.to_excel(writer, sheet_name=sheet_name, index=False)
                    data = buffer.getvalue()
                finally:
                    buffer.close()
                mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                return data, mime
            else:
                # Default to CSV ZIP
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
                    for name, df in dfs.items():
                        csv_bytes = df.to_csv(index=False).encode('utf-8')
                        zf.writestr(f"{name}.csv", csv_bytes)
                data = buffer.getvalue()
                buffer.close()
                return data, 'application/zip'
    except Exception as e:
        raise RuntimeError(f"Export failed: {e}")
