# auth.py
from datetime import datetime
import streamlit as st
import hashlib
import sqlite3
import os
import json
from db_utils import log_activity
try:
    import bcrypt  # Optional dependency for secure password hashing
except Exception:  # pragma: no cover
    bcrypt = None

# Use relative path for deployment
DB_NAME = 'brent_j_marketing.db'

def get_db_connection():
    """Get database connection"""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except Exception as e:
        print(f"Failed to connect to the database: {e}")
        return None

def _looks_like_bcrypt(hash_str: str) -> bool:
    try:
        return isinstance(hash_str, str) and hash_str.startswith("$2") and len(hash_str) > 50
    except Exception:
        return False

def _looks_like_sha256_hex(hash_str: str) -> bool:
    if not isinstance(hash_str, str) or len(hash_str) != 64:
        return False
    try:
        int(hash_str, 16)
        return True
    except Exception:
        return False

def authenticate_user(username, password):
    """Authenticate user credentials.

    Supports legacy SHA-256 hex hashes and downgrades bcrypt hashes back to
    SHA-256 so credentials continue working on installs without the optional
    bcrypt dependency.
    """
    conn = get_db_connection()
    if conn is None:
        return False, None
    
    try:
        cursor = conn.cursor()
        # Include is_active for access control; fallback handled by migrate_schema at app start
        try:
            cursor.execute("SELECT password_hash, role, COALESCE(is_active,1) FROM users WHERE username = ?", (username,))
        except Exception:
            cursor.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        
        if result:
            if len(result) >= 3 and not result[2]:
                return False, None
            stored_hash, role = result[0], result[1]
            authed = False

            if stored_hash and _looks_like_bcrypt(stored_hash):
                if bcrypt:
                    try:
                        authed = bcrypt.checkpw(password.encode(), stored_hash.encode())
                        if authed:
                            # Replace bcrypt hash with SHA-256 for compatibility
                            sha256_hash = hashlib.sha256(password.encode()).hexdigest()
                            cursor.execute(
                                "UPDATE users SET password_hash = ? WHERE username = ?",
                                (sha256_hash, username)
                            )
                            # Downgraded hash stored via SHA-256
                    except Exception:
                        authed = False
                else:
                    print("bcrypt module not available; unable to validate stored bcrypt hash")
                    authed = False
            else:
                # SHA-256 path
                sha256_hash = hashlib.sha256(password.encode()).hexdigest()
                if stored_hash == sha256_hash:
                    authed = True

            if authed:
                cursor.execute(
                    "UPDATE users SET last_login = ? WHERE username = ?",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username)
                )
                conn.commit()
                return True, role
        return False, None
    except Exception as e:
        print(f"Authentication error: {e}")
        return False, None

def get_user_role(username):
    """Get user role"""
    conn = get_db_connection()
    if conn is None:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"Error getting user role: {e}")
        return None

    

def init_session_state():
    defaults = {
        'authenticated': False,
        'username': None,
        'user_role': None,
        'login_attempted': False,
        'login_loading': False,
        'need_rerun': False,
        'last_activity': datetime.now(),
        'maintenance_run': None,
        'backup_created': False
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def login_form():
    """Display login form"""
    st.title("Brent J. Marketing - Login")
    
    with st.form("login_form", clear_on_submit=True):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Login", type="primary", disabled=st.session_state.get('login_loading', False))
    
    if submitted:
        st.session_state.login_loading = True
        with st.spinner("Signing in..."):
            authenticated, role = authenticate_user(username, password)
        
        if authenticated:
            st.session_state.authenticated = True
            st.session_state.username = username
            st.session_state.user_role = role
            st.session_state.login_attempted = False
            # Ensure landing on main dashboard after login
            st.session_state.view = 'main'
            log_activity(username, "login", "User logged in successfully")
            st.session_state.need_rerun = True
            st.session_state.login_loading = False
            # Force immediate rerun to load the authenticated app state
            st.rerun()
        else:
            st.session_state.login_attempted = True
            st.caption("Invalid username or password")
            log_activity(username, "login_failed", "Failed login attempt")
            st.session_state.login_loading = False

def logout():
    """Logout user"""
    if st.session_state.authenticated:
        log_activity(st.session_state.username, "logout", "User logged out")
    
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.login_attempted = False
    # Ensure landing back to main view after logout
    st.session_state.view = 'main'
    st.session_state.need_rerun = True

def require_login():
    """Require user to be logged in"""
    if not st.session_state.authenticated:
        login_form()
        if not st.session_state.authenticated:
            st.stop()

def require_admin():
    """Require user to be admin"""
    require_login()
    if st.session_state.user_role != 'admin':
        st.error("Administrator access required")
        st.stop()
