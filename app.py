# app.py
import time
import sqlite3
import streamlit as st
import pandas as pd
from datetime import datetime
from db_utils import DB_NAME, load_data, create_tables, migrate_schema, database_maintenance, get_db_connection, get_activity_logs
from logic import (
    add_new_client, add_vin_to_client, add_part_to_vin,
    add_part_without_vin, delete_client, delete_vin,
    delete_part, update_client_and_vins, update_part,
    add_supplier_to_part, safe_add_part_to_vin, get_suppliers_for_part, update_vin, move_part_to_vin,
    update_supplier, delete_supplier
)
from security import validate_phone, validate_vin, validate_numeric
from services.pdf import generate_pdf
from ui.navigation import (
    main_navigation,
    global_search,
    export_data,
    backup_database,
    confirm_action_interface,
    database_maintenance_interface,
)
from views.activity_logs import render_activity_logs_view
from views.user_management import render_user_management_view
import random
import base64
import io
import zipfile
import json
import os
from auth import init_session_state, login_form, logout, require_login, require_admin

# Initialize session state
init_session_state()

# --- SESSION STATE INITIALIZATION ---
if 'view' not in st.session_state:
    st.session_state.view = 'main'
if 'show_client_form' not in st.session_state:
    st.session_state.show_client_form = False
if 'client_added' not in st.session_state:
    st.session_state.client_added = False
if 'vin_added' not in st.session_state:
    st.session_state.vin_added = False
if 'current_client_phone' not in st.session_state:
    st.session_state.current_client_phone = None
if 'current_client_name' not in st.session_state:
    st.session_state.current_client_name = None
if 'current_vin_no' not in st.session_state:
    st.session_state.current_vin_no = None
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False
if 'current_vin_no_view' not in st.session_state:
    st.session_state.current_vin_no_view = None
if 'add_part_mode' not in st.session_state:
    st.session_state.add_part_mode = False
if 'selected_vin_to_add_part' not in st.session_state:
    st.session_state.selected_vin_to_add_part = None
if 'part_count' not in st.session_state:
    st.session_state.part_count = 1
if 'supplier_count' not in st.session_state:
    st.session_state.supplier_count = 1
if 'supplier_count_edit' not in st.session_state:
    st.session_state.supplier_count_edit = 1
if 'current_part_id_to_add_supplier' not in st.session_state:
    st.session_state.current_part_id_to_add_supplier = None
if 'last_part_ids' not in st.session_state:
    st.session_state.last_part_ids = []
if 'generated_quote_msg' not in st.session_state:
    st.session_state.generated_quote_msg = ""
if 'quote_selected_vin' not in st.session_state:
    st.session_state.quote_selected_vin = None
if 'quote_selected_part_ids' not in st.session_state:
    st.session_state.quote_selected_part_ids = []
if 'quote_selected_phone' not in st.session_state:
    st.session_state.quote_selected_phone = None
if 'generated_text_quote' not in st.session_state:
    st.session_state.generated_text_quote = ""
if 'document_type' not in st.session_state:
    st.session_state.document_type = 'quote'
if 'generated_pdf_data' not in st.session_state:
    st.session_state.generated_pdf_data = None
if 'generated_pdf_filename' not in st.session_state:
    st.session_state.generated_pdf_filename = ""
if 'show_pdf_preview' not in st.session_state:
    st.session_state.show_pdf_preview = False
if 'part_conditions' not in st.session_state:
    st.session_state.part_conditions = {}
if 'clients_page' not in st.session_state:
    st.session_state.clients_page = 0
if 'parts_page' not in st.session_state:
    st.session_state.parts_page = 0
if 'action_history' not in st.session_state:
    st.session_state.action_history = []
if 'confirm_action' not in st.session_state:
    st.session_state.confirm_action = None
if 'export_filters' not in st.session_state:
    st.session_state.export_filters = {}
if 'current_filters' not in st.session_state:
    st.session_state.current_filters = {}
if 'selected_parts_suppliers' not in st.session_state:
    st.session_state.selected_parts_suppliers = {}
if 'current_part_management' not in st.session_state:
    st.session_state.current_part_management = {
        'current_part_index': 0,
        'parts_data': [],
        'saved_part_ids': []
    }
if 'maintenance_run' not in st.session_state:
    st.session_state.maintenance_run = None
if 'last_activity' not in st.session_state:
    st.session_state.last_activity = datetime.now()
if 'backup_created' not in st.session_state:
    st.session_state.backup_created = False

# Company info moved to services/pdf.py

# --- Ensure tables are created when the app first runs ---
create_tables()
migrate_schema()

# Check if user is authenticated
if not st.session_state.authenticated:
    login_form()
    st.stop()

# --- SESSION TIMEOUT FUNCTIONALITY ---
# Initialize last activity time if not set
if 'last_activity' not in st.session_state:
    st.session_state.last_activity = datetime.now()

# Check for timeout (1 hour = 3600 seconds)
time_since_activity = (datetime.now() - st.session_state.last_activity).seconds

# Warn user 5 minutes before timeout
if time_since_activity > 3300:  # 55 minutes (5 minutes before timeout)
    time_remaining = 3600 - time_since_activity
    minutes_remaining = time_remaining // 60
    seconds_remaining = time_remaining % 60
    st.warning(f"Session will timeout in {minutes_remaining}m {seconds_remaining}s due to inactivity. Interact with the page to continue.")

# Full timeout after 1 hour
if time_since_activity > 3600:
    st.warning("Session timed out due to inactivity. Please log in again.")
    logout()
    st.rerun()

# Update last activity time on every interaction
st.session_state.last_activity = datetime.now()
# --- END SESSION TIMEOUT CODE ---

# Main application content
st.title("Brent J. Marketing, car parts database")
df_clients, df_vins, df_parts, df_part_suppliers = load_data()

# --- DATABASE MAINTENANCE (Admin only, runs on Mondays) ---
if st.session_state.authenticated and st.session_state.user_role == 'admin':
    # Run maintenance weekly on Mondays
    if datetime.now().weekday() == 0:  # Monday (0 = Monday, 6 = Sunday)
        # Use a session state flag to only run once per day
        if 'maintenance_run' not in st.session_state or st.session_state.maintenance_run != datetime.now().date():
            if database_maintenance():
                st.success("Weekly database maintenance completed!")
                from auth import log_activity
                log_activity(st.session_state.username, "maintenance", "Weekly database maintenance performed")
            else:
                st.error("Database maintenance failed")
            st.session_state.maintenance_run = datetime.now().date()
# --- END MAINTENANCE CODE ---

# Add logout button to sidebar
# --- Activity Logs View (Admin Only) ---
# Use modular view renderer
if st.session_state.view == 'activity_logs':
    render_activity_logs_view()
    st.stop()

# Legacy inline implementation removed (disabled)
if False:
    require_admin()
    st.header("Activity Logs")
    
    if st.button("⬅️ Back to Main"):
        st.session_state.view = 'main'
        st.session_state.need_rerun = True
    
    st.divider()
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        filter_username = st.text_input("Filter by username", "")
    with col2:
        log_limit = st.number_input("Number of logs", min_value=10, max_value=1000, value=100)
    
    # Load activity logs
    logs_df = get_activity_logs(filter_username if filter_username else None, log_limit)
    
    if not logs_df.empty:
        st.dataframe(logs_df, width='stretch')
        
        # Export option
        if st.button("Export Logs to CSV"):
            csv = logs_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"activity_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.info("No activity logs found.")

def set_view(view_name):
    st.session_state.view = view_name
    st.session_state.need_rerun = True

# --- Sidebar and Global Tools ---
main_navigation()
global_search(df_clients, df_vins, df_parts)
export_data()
backup_database()
confirm_action_interface()
database_maintenance_interface()

# --- Main Dashboard ---
if st.session_state.view == 'main':
    st.header("Search for Client")
    search_term = st.text_input("Search by exact Phone Number", key="search_clients")

    if search_term:
        with st.spinner("Searching for client..."):
            found_client = df_clients[df_clients['phone'].astype(str) == search_term]
            if not found_client.empty:
                st.session_state.view = 'client_details'
                st.session_state.current_client_phone = found_client['phone'].iloc[0]
                st.session_state.current_client_name = found_client['client_name'].iloc[0]
                st.session_state.need_rerun = True
            else:
                st.warning("No client found with that exact phone number.")
                if st.button("Register New Client"):
                    st.session_state.view = 'add_client'
                    st.session_state.show_client_form = True
                    st.session_state.need_rerun = True

    st.divider()

elif st.session_state.view == 'user_management':
    render_user_management_view()
    st.stop()

# --- Clients List View ---
elif st.session_state.view == 'client_list':
    st.header("Clients")
    if "client_list_page" not in st.session_state:
        st.session_state.client_list_page = 0

    if st.button("Back to Main"):
        st.session_state.view = 'main'
        st.session_state.need_rerun = True
        st.session_state.client_list_page = 0

    clients_df = df_clients.copy()

    if clients_df.empty:
        st.info("No clients found.")
    else:
        page_size = 20
        total_clients = len(clients_df)
        total_pages = max((total_clients - 1) // page_size + 1, 1)
        current_page = st.session_state.get('client_list_page', 0)
        current_page = max(0, min(current_page, total_pages - 1))
        st.session_state.client_list_page = current_page
        start_idx = current_page * page_size
        end_idx = start_idx + page_size
        page_clients = clients_df.iloc[start_idx:end_idx]

        st.markdown("---")
        st.subheader("Open Client Details")
        # Option A: quick select
        phones = [''] + clients_df['phone'].astype(str).dropna().unique().tolist()
        selected_phone = st.selectbox("Select phone", options=phones, key="open_client_phone")
        if selected_phone:
            row = clients_df[clients_df['phone'].astype(str) == selected_phone].iloc[0]
            st.session_state.current_client_phone = row['phone']
            st.session_state.current_client_name = row['client_name']
            st.session_state.edit_mode = False
            st.session_state.view = 'client_details'
            st.session_state.need_rerun = True

        st.markdown("---")
        st.subheader("Clients (View Details)")
        for _, row in page_clients.iterrows():
            c1, c2, c3 = st.columns([0.4, 0.4, 0.2])
            with c1:
                st.write(str(row['client_name']))
            with c2:
                st.write(str(row['phone']))
            with c3:
                if st.button("View", key=f"view_client_{row['phone']}"):
                    st.session_state.current_client_phone = row['phone']
                    st.session_state.current_client_name = row['client_name']
                    st.session_state.edit_mode = False
                    st.session_state.view = 'client_details'
                    st.session_state.need_rerun = True

        st.markdown("---")
        nav_cols = st.columns([0.2, 0.6, 0.2])
        with nav_cols[0]:
            if st.button("Previous Page", disabled=current_page == 0):
                st.session_state.client_list_page = max(current_page - 1, 0)
                st.session_state.need_rerun = True
        with nav_cols[1]:
            st.write(f"Page {current_page + 1} of {total_pages}")
        with nav_cols[2]:
            if st.button("Next Page", disabled=current_page >= total_pages - 1):
                st.session_state.client_list_page = min(current_page + 1, total_pages - 1)
                st.session_state.need_rerun = True

# --- Client Details View ---
elif st.session_state.view == 'client_details':
    st.header("Client Details")
    if st.button("Back to Clients"):
        st.session_state.view = 'client_list'
        st.session_state.need_rerun = True

    phone = st.session_state.get('current_client_phone')
    name = st.session_state.get('current_client_name')
    if not phone:
        st.info("Select a client from the Clients view.")
    else:
        st.subheader(f"{name} ({phone})")

        # Undo bar for last deletion (VIN or Part)
        last_del = st.session_state.get('last_delete')
        if last_del:
            colu1, colu2, colu3 = st.columns([0.6, 0.2, 0.2])
            with colu1:
                if last_del.get('type') == 'vin':
                    st.info(f"A VIN was deleted: {last_del.get('vin_data',{}).get('vin_number','')} — You can undo.")
                elif last_del.get('type') == 'part':
                    st.info(f"A Part was deleted: {last_del.get('part',{}).get('part_name','')} — You can undo.")
                else:
                    st.info("An item was deleted — You can undo.")
            with colu2:
                if st.button("Undo", key="undo_last_delete"):
                    try:
                        if last_del.get('type') == 'part':
                            pdata = last_del.get('part', {})
                            suppliers = last_del.get('suppliers', [])
                            vin_num = str(pdata.get('vin_number') or '').strip()
                            if vin_num and vin_num not in ('None', 'No VIN provided'):
                                new_part_id = add_part_to_vin(
                                    vin_num,
                                    str(pdata.get('client_phone') or ''),
                                    pdata.get('part_name'),
                                    pdata.get('part_number'),
                                    int(pdata.get('quantity') or 1),
                                    pdata.get('notes') or '',
                                    [],
                                    st.session_state.username,
                                )
                            else:
                                new_part_id = add_part_without_vin(
                                    pdata.get('part_name'),
                                    pdata.get('part_number'),
                                    int(pdata.get('quantity') or 1),
                                    pdata.get('notes') or '',
                                    str(pdata.get('client_phone') or ''),
                                    [],
                                    st.session_state.username,
                                )
                            # Restore suppliers
                            for s in suppliers:
                                try:
                                    add_supplier_to_part(
                                        int(new_part_id),
                                        s.get('supplier_name'),
                                        float(s.get('buying_price') or 0.0),
                                        float(s.get('selling_price') or 0.0),
                                        s.get('delivery_time') or '',
                                        st.session_state.username,
                                    )
                                except Exception:
                                    pass
                            st.success("Part restored.")
                        elif last_del.get('type') == 'vin':
                            v = last_del.get('vin_data', {})
                            cphone = str(last_del.get('client_phone') or '')
                            add_vin_to_client(
                                cphone,
                                v.get('vin_number'),
                                v.get('model'),
                                v.get('prod_yr'),
                                v.get('body'),
                                v.get('engine'),
                                v.get('code'),
                                v.get('transmission'),
                                st.session_state.username,
                            )
                            # Restore parts for VIN
                            for entry in last_del.get('parts', []):
                                part = entry.get('part') or {}
                                suppliers = entry.get('suppliers') or []
                                new_pid = add_part_to_vin(
                                    v.get('vin_number'),
                                    cphone,
                                    part.get('part_name'),
                                    part.get('part_number'),
                                    int(part.get('quantity') or 1),
                                    part.get('notes') or '',
                                    [],
                                    st.session_state.username,
                                )
                                for s in suppliers:
                                    try:
                                        add_supplier_to_part(
                                            int(new_pid),
                                            s.get('supplier_name'),
                                            float(s.get('buying_price') or 0.0),
                                            float(s.get('selling_price') or 0.0),
                                            s.get('delivery_time') or '',
                                            st.session_state.username,
                                        )
                                    except Exception:
                                        pass
                            st.success("VIN and associated parts restored.")
                        st.session_state.last_delete = None
                        st.cache_data.clear()
                        st.session_state.need_rerun = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Undo failed: {e}")
            with colu3:
                if st.button("Dismiss", key="dismiss_last_delete"):
                    st.session_state.last_delete = None
                    st.session_state.need_rerun = True

        # Edit toggle / form
        if not st.session_state.get('edit_mode', False):
            if st.button("Edit Client"):
                st.session_state.edit_mode = True
                st.session_state.need_rerun = True
        else:
            st.markdown("### Edit Client Information")
            with st.form("edit_client_form", clear_on_submit=False):
                new_name = st.text_input("Client Name", value=str(name))
                new_phone = st.text_input("Phone", value=str(phone))
                save_btn = st.form_submit_button("Save Changes")
                cancel_btn = st.form_submit_button("Cancel")

            if save_btn:
                # Validate phone format if changed
                if not validate_phone(new_phone):
                    st.warning("Invalid phone format.")
                else:
                    try:
                        update_client_and_vins(str(phone), str(new_phone), new_name)
                        st.success("Client updated successfully.")
                        st.session_state.current_client_phone = str(new_phone)
                        st.session_state.current_client_name = new_name
                        st.session_state.edit_mode = False
                        st.cache_data.clear()
                        st.session_state.need_rerun = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error updating client: {str(e)}")
            if not save_btn and cancel_btn:
                st.session_state.edit_mode = False
                st.session_state.need_rerun = True
                st.rerun()

        # Details (VINs and Parts)
        st.markdown("### VINs")
        client_vins = df_vins[df_vins['client_phone'].astype(str) == str(phone)]
        if client_vins.empty:
            st.info("No VINs registered for this client.")
        else:
            for _, vin_row in client_vins.iterrows():
                vin_no = str(vin_row['vin_number'])
                parts_for_vin = df_parts[
                    (df_parts['client_phone'].astype(str) == str(phone))
                    & (df_parts['vin_number'].astype(str) == vin_no)
                ]
                part_count = len(parts_for_vin)
                with st.expander(f"VIN {vin_no} ({part_count} parts)"):
                    top1, top2 = st.columns([0.7, 0.3])
                    with top1:
                        infoL, infoR = st.columns(2)
                        with infoL:
                            st.markdown(f"**Model:** {vin_row.get('model', '')}")
                            st.markdown(f"**Prod. Yr:** {vin_row.get('prod_yr', '')}")
                            st.markdown(f"**Body:** {vin_row.get('body', '')}")
                            st.markdown(f"**Engine:** {vin_row.get('engine', '')}")
                        with infoR:
                            st.markdown(f"**Code:** {vin_row.get('code', '')}")
                            st.markdown(f"**Transmission:** {vin_row.get('transmission', '')}")
                    with top2:
                        btn1, btn2 = st.columns(2)
                        with btn1:
                            if st.button("Edit VIN", key=f"edit_vin_{vin_no}"):
                                st.session_state.edit_vin_number = vin_no
                                st.session_state.view = 'edit_vin'
                                st.session_state.need_rerun = True
                        with btn2:
                            if st.button("Delete VIN", key=f"delete_vin_{vin_no}"):
                                # Backup VIN and associated parts + suppliers before deletion
                                vin_backup = {
                                    'vin_number': vin_no,
                                    'model': vin_row.get('model', ''),
                                    'prod_yr': vin_row.get('prod_yr', ''),
                                    'body': vin_row.get('body', ''),
                                    'engine': vin_row.get('engine', ''),
                                    'code': vin_row.get('code', ''),
                                    'transmission': vin_row.get('transmission', ''),
                                }
                                parts_for_vin = df_parts[(df_parts['vin_number'].astype(str) == vin_no)]
                                parts_backup = []
                                for _, p in parts_for_vin.iterrows():
                                    p_dict = {
                                        'id': int(p['id']),
                                        'vin_number': p.get('vin_number'),
                                        'client_phone': p.get('client_phone'),
                                        'part_name': p.get('part_name'),
                                        'part_number': p.get('part_number'),
                                        'quantity': int(p.get('quantity') or 1),
                                        'notes': p.get('notes') or '',
                                    }
                                    suppliers = df_part_suppliers[df_part_suppliers['part_id'] == p['id']]
                                    parts_backup.append({
                                        'part': p_dict,
                                        'suppliers': suppliers.to_dict(orient='records') if not suppliers.empty else []
                                    })
                                try:
                                    delete_vin(vin_no, st.session_state.username)
                                    st.session_state.last_delete = {
                                        'type': 'vin',
                                        'client_phone': str(phone),
                                        'vin_data': vin_backup,
                                        'parts': parts_backup,
                                    }
                                    st.success("VIN deleted. You can undo this action.")
                                    st.cache_data.clear()
                                    st.session_state.need_rerun = True
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Delete VIN failed: {e}")

                    st.markdown("---")
                    st.subheader("Parts for this VIN")
                    # Quick add part directly to this VIN
                    if st.button("Add Part to this VIN", key=f"add_part_to_vin_btn_{vin_no}"):
                        st.session_state.selected_vin_to_add_part = vin_no
                        st.session_state.view = 'add_part_for_client'
                        st.session_state.need_rerun = True
                    # List parts under this VIN
                    if parts_for_vin.empty:
                        st.info("No parts for this VIN.")
                    else:
                        for _, part_row in parts_for_vin.iterrows():
                            info_col, edit_col, del_col = st.columns([0.7, 0.15, 0.15])
                            with info_col:
                                st.write(f"{part_row['part_name']} ({part_row['part_number']}) - Qty: {part_row['quantity']}")
                            with edit_col:
                                if st.button("Edit", key=f"edit_part_{part_row['id']}"):
                                    st.session_state.part_to_edit_id = int(part_row['id'])
                                    st.session_state.view = 'edit_part'
                                    st.session_state.need_rerun = True
                            with del_col:
                                if st.button("Delete", key=f"delete_part_{part_row['id']}"):
                                    # Backup part and suppliers then delete
                                    suppliers = df_part_suppliers[df_part_suppliers['part_id'] == part_row['id']]
                                    st.session_state.last_delete = {
                                        'type': 'part',
                                        'part': {
                                            'id': int(part_row['id']),
                                            'vin_number': part_row.get('vin_number'),
                                            'client_phone': part_row.get('client_phone'),
                                            'part_name': part_row.get('part_name'),
                                            'part_number': part_row.get('part_number'),
                                            'quantity': int(part_row.get('quantity') or 1),
                                            'notes': part_row.get('notes') or '',
                                        },
                                        'suppliers': suppliers.to_dict(orient='records') if not suppliers.empty else []
                                    }
                                    try:
                                        delete_part(int(part_row['id']), st.session_state.username)
                                        st.success("Part deleted. You can undo this action.")
                                        st.cache_data.clear()
                                        st.session_state.need_rerun = True
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Delete part failed: {e}")

        # Parts are shown within each VIN expander above

        # Show parts without a VIN assignment
        no_vin_mask = (
            (df_parts['client_phone'].astype(str) == str(phone))
            & (
                df_parts['vin_number'].isna()
                | (df_parts['vin_number'].astype(str).str.strip().isin(['', 'None', 'No VIN provided']))
            )
        )
        parts_without_vin = df_parts[no_vin_mask]
        if not parts_without_vin.empty:
            st.subheader("Parts Without VIN")
            for _, part_row in parts_without_vin.iterrows():
                info_col, edit_col, del_col = st.columns([0.7, 0.15, 0.15])
                with info_col:
                    st.write(f"{part_row['part_name']} ({part_row['part_number']}) - Qty: {part_row['quantity']}")
                with edit_col:
                    if st.button("Edit", key=f"edit_part_novin_{part_row['id']}"):
                        st.session_state.part_to_edit_id = int(part_row['id'])
                        st.session_state.view = 'edit_part'
                        st.session_state.need_rerun = True
                with del_col:
                    if st.button("Delete", key=f"delete_part_novin_{part_row['id']}"):
                        suppliers = df_part_suppliers[df_part_suppliers['part_id'] == part_row['id']]
                        st.session_state.last_delete = {
                            'type': 'part',
                            'part': {
                                'id': int(part_row['id']),
                                'vin_number': part_row.get('vin_number'),
                                'client_phone': part_row.get('client_phone'),
                                'part_name': part_row.get('part_name'),
                                'part_number': part_row.get('part_number'),
                                'quantity': int(part_row.get('quantity') or 1),
                                'notes': part_row.get('notes') or '',
                            },
                            'suppliers': suppliers.to_dict(orient='records') if not suppliers.empty else []
                        }
                        try:
                            delete_part(int(part_row['id']), st.session_state.username)
                            st.success("Part deleted. You can undo this action.")
                            st.cache_data.clear()
                            st.session_state.need_rerun = True
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete part failed: {e}")

        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Add VIN"):
                st.session_state.view = 'add_vin_to_existing_client'
                st.session_state.vin_added = False
                st.session_state.need_rerun = True
        with col2:
            if st.button("Add Part (No VIN)"):
                st.session_state.view = 'add_part_without_vin_for_client'
                st.session_state.need_rerun = True
        with col3:
            vins_for_client = df_vins[df_vins['client_phone'].astype(str) == str(phone)]['vin_number'].dropna().astype(str).unique().tolist()
            target_vin = st.selectbox("Select VIN", options=[''] + vins_for_client, key="select_vin_for_new_part")
            if st.button("Add Part to VIN"):
                if not target_vin:
                    st.warning("Please select a VIN to add a part to.")
                else:
                    st.session_state.selected_vin_to_add_part = target_vin
                    st.session_state.view = 'add_part_for_client'
                    st.session_state.need_rerun = True

# --- Edit VIN View ---
elif st.session_state.view == 'edit_vin':
    vin_no = st.session_state.get('edit_vin_number')
    if not vin_no:
        st.warning("No VIN selected.")
        st.session_state.view = 'client_details'
        st.stop()
    st.header(f"Edit VIN: {vin_no}")
    vin_df = df_vins[df_vins['vin_number'] == vin_no]
    if vin_df.empty:
        st.warning("VIN not found.")
        st.session_state.view = 'client_details'
        st.stop()
    row = vin_df.iloc[0]
    with st.form("edit_vin_form", clear_on_submit=False):
        new_vin = st.text_input("VIN Number", value=str(row['vin_number']))
        model = st.text_input("Model", value=str(row['model'] or ''))
        prod_yr = st.text_input("Prod. Yr", value=str(row['prod_yr'] or ''))
        body = st.text_input("Body", value=str(row['body'] or ''))
        engine = st.text_input("Engine", value=str(row['engine'] or ''))
        code = st.text_input("Code", value=str(row['code'] or ''))
        transmission = st.text_input("Transmission", value=str(row['transmission'] or ''))
        colb1, colb2 = st.columns(2)
        with colb1:
            save_vin = st.form_submit_button("Save VIN")
        with colb2:
            cancel_vin = st.form_submit_button("Cancel")

    if save_vin:
        try:
            update_vin(vin_no, new_vin, model, prod_yr, body, engine, code, transmission, st.session_state.username)
            st.success("VIN updated successfully.")
            st.session_state.edit_vin_number = new_vin
            st.cache_data.clear()
            st.session_state.view = 'client_details'
            st.session_state.need_rerun = True
            st.rerun()
        except Exception as e:
            st.error(str(e))
    if not save_vin and cancel_vin:
        st.session_state.view = 'client_details'
        st.session_state.need_rerun = True
        st.rerun()

# --- Edit Part View ---
elif st.session_state.view == 'edit_part':
    part_id = st.session_state.get('part_to_edit_id')
    if not part_id:
        st.warning("No part selected.")
        st.session_state.view = 'client_details'
        st.stop()
    st.header(f"Edit Part ID: {part_id}")
    part_df = df_parts[df_parts['id'] == part_id]
    if part_df.empty:
        st.warning("Part not found.")
        st.session_state.view = 'client_details'
        st.stop()
    prow = part_df.iloc[0]
    with st.form("edit_part_form", clear_on_submit=False):
        p_name = st.text_input("Part Name", value=str(prow['part_name'] or ''))
        p_number = st.text_input("Part Number", value=str(prow['part_number'] or ''))
        p_qty = st.number_input("Quantity", min_value=1, value=int(prow['quantity'] or 1))
        p_notes = st.text_area("Notes", value=str(prow['notes'] or ''))
        colpb1, colpb2 = st.columns(2)
        with colpb1:
            save_part = st.form_submit_button("Save Part")
        with colpb2:
            cancel_part = st.form_submit_button("Cancel")

    if save_part:
        try:
            # Preserve existing suppliers
            existing_suppliers = df_part_suppliers[df_part_suppliers['part_id'] == part_id]
            suppliers_data = []
            for _, s in existing_suppliers.iterrows():
                suppliers_data.append({
                    'name': s['supplier_name'],
                    'buying_price': float(s['buying_price'] or 0),
                    'selling_price': float(s['selling_price'] or 0),
                    'delivery_time': s['delivery_time'] or ''
                })
            update_part(int(part_id), p_name, p_number, int(p_qty), p_notes, suppliers_data, st.session_state.username)
            st.success("Part updated successfully.")
            st.cache_data.clear()
            st.session_state.view = 'client_details'
            st.session_state.need_rerun = True
            st.rerun()
        except Exception as e:
            st.error(str(e))
    if not save_part and cancel_part:
        st.session_state.view = 'client_details'
        st.session_state.need_rerun = True
        st.rerun()

    # Suppliers management
    st.markdown("---")
    st.subheader("Suppliers")
    sup_df = df_part_suppliers[df_part_suppliers['part_id'] == part_id]
    if sup_df.empty:
        st.info("No suppliers for this part.")
    else:
        for _, srow in sup_df.iterrows():
            sid = int(srow['id'])
            with st.form(f"edit_supplier_form_{sid}", clear_on_submit=False):
                c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                with c1:
                    s_name = st.text_input("Name", value=str(srow['supplier_name'] or ''), key=f"s_name_{sid}")
                with c2:
                    s_buy = st.number_input("Buy $", min_value=0.0, value=float(srow['buying_price'] or 0.0), format="%.2f", key=f"s_buy_{sid}")
                with c3:
                    s_sell = st.number_input("Sell $", min_value=0.0, value=float(srow['selling_price'] or 0.0), format="%.2f", key=f"s_sell_{sid}")
                with c4:
                    s_del = st.text_input("Delivery", value=str(srow['delivery_time'] or ''), key=f"s_del_{sid}")
                with c5:
                    save_s = st.form_submit_button("Save")
                    del_s = st.form_submit_button("Delete")
            if save_s:
                try:
                    update_supplier(sid, s_name, s_buy, s_sell, s_del, st.session_state.username)
                    st.success("Supplier updated.")
                    st.cache_data.clear()
                    st.session_state.need_rerun = True
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if del_s:
                try:
                    delete_supplier(sid, st.session_state.username)
                    st.success("Supplier deleted.")
                    st.cache_data.clear()
                    st.session_state.need_rerun = True
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # Add new supplier
    with st.form(f"add_supplier_form_edit_{part_id}", clear_on_submit=True):
        st.markdown("### Add Supplier")
        ns1, ns2, ns3, ns4 = st.columns([2, 1, 1, 1])
        with ns1:
            ns_name = st.text_input("Name", key=f"ns_name_{part_id}")
        with ns2:
            ns_buy = st.number_input("Buy $", min_value=0.0, value=0.0, format="%.2f", key=f"ns_buy_{part_id}")
        with ns3:
            ns_sell = st.number_input("Sell $", min_value=0.0, value=0.0, format="%.2f", key=f"ns_sell_{part_id}")
        with ns4:
            ns_del = st.text_input("Delivery", key=f"ns_del_{part_id}")
        add_s_btn = st.form_submit_button("Add Supplier")
    if add_s_btn:
        if not ns_name:
            st.warning("Supplier name is required")
        else:
            try:
                add_supplier_to_part(int(part_id), ns_name, float(ns_buy or 0.0), float(ns_sell or 0.0), ns_del or '', st.session_state.username)
                st.success("Supplier added.")
                st.cache_data.clear()
                st.session_state.need_rerun = True
                st.rerun()
            except Exception as e:
                st.error(str(e))

    # Move part to a registered VIN
    st.markdown("---")
    st.subheader("Move Part to VIN")
    # Determine client's phone for part
    client_phone_for_part = str(prow['client_phone']) if 'client_phone' in prow else ''
    if not client_phone_for_part:
        # fallback to session client phone
        client_phone_for_part = str(st.session_state.get('current_client_phone') or '')
    vin_options = df_vins[df_vins['client_phone'].astype(str) == client_phone_for_part]['vin_number'].dropna().astype(str).unique().tolist()
    target_vin_move = st.selectbox("Select target VIN", options=[''] + vin_options, key=f"move_part_vin_{part_id}")
    if st.button("Move Part", key=f"btn_move_part_{part_id}"):
        if not target_vin_move:
            st.warning("Please select a VIN to move this part to.")
        else:
            try:
                move_part_to_vin(int(part_id), target_vin_move, st.session_state.username)
                st.success("Part moved successfully.")
                st.cache_data.clear()
                st.session_state.view = 'client_details'
                st.session_state.need_rerun = True
                st.rerun()
            except Exception as e:
                st.error(str(e))

# --- Parts Inventory View ---
elif st.session_state.view == 'view_parts_inventory':
    st.header("Parts Inventory")
    if st.button("Back to Main"):
        st.session_state.view = 'main'
        st.session_state.need_rerun = True

    q = st.text_input("Search part name/number", key="parts_search")
    parts_df = df_parts.copy()
    if q:
        qq = str(q).strip()
        parts_df = parts_df[
            parts_df['part_name'].astype(str).str.contains(qq, case=False, na=False)
            | parts_df['part_number'].astype(str).str.contains(qq, case=False, na=False)
        ]
    if parts_df.empty:
        st.info("No parts found.")
    else:
        st.dataframe(parts_df[['part_name','part_number','quantity','client_phone','vin_number']], width='stretch', hide_index=True)

def reset_part_management():
    """Reset part management state"""
    st.session_state.part_count = 1
    st.session_state.current_part_management = {
        'current_part_index': 0,
        'parts_data': [],
        'saved_part_ids': []
    }
    st.session_state.current_part_id_to_add_supplier = None
    
# --- PDF GENERATION FUNCTION ---
def _generate_pdf_legacy(client_info, parts_data, total_quote_amount, manual_deposit, bill_to_info=None, ship_to_info=None, delivery_time=None, document_number=None, document_type='quote'):
    pass
def reset_view_and_state():
    st.session_state.view = 'main'
    st.session_state.show_client_form = False
    st.session_state.client_added = False
    st.session_state.vin_added = False
    st.session_state.current_client_phone = None
    st.session_state.current_client_name = None
    st.session_state.current_vin_no = None
    st.session_state.edit_mode = False
    st.session_state.current_vin_no_view = None
    st.session_state.add_part_mode = False
    st.session_state.selected_vin_to_add_part = None
    st.session_state.part_count = 1
    st.session_state.supplier_count = 1
    st.session_state.supplier_count_edit = 1
    st.session_state.current_part_id_to_add_supplier = None
    st.session_state.last_part_ids = []
    st.session_state.generated_quote_msg = ""
    st.session_state.quote_selected_vin = None
    st.session_state.quote_selected_part_ids = []
    st.session_state.quote_selected_phone = None
    st.session_state.generated_text_quote = ""
    st.session_state.document_type = 'quote'
    st.session_state.generated_pdf_data = None
    st.session_state.generated_pdf_filename = ""
    st.session_state.show_pdf_preview = False
    st.session_state.part_conditions = {}
    st.session_state.clients_page = 0
    st.session_state.parts_page = 0
    st.session_state.selected_items = {
        'clients': [],
        'vins': [],
        'parts': []
    }
    st.session_state.export_filters = {}
    st.session_state.current_filters = {}
    st.session_state.selected_parts_suppliers = {}
    st.session_state.need_rerun = True

def _main_navigation_legacy():
    pass
def _global_search_legacy():
    pass
def _export_data_legacy():
    pass
def _backup_database_legacy():
    pass
def _confirm_action_interface_legacy():
    pass
def _database_maintenance_interface_legacy():
    pass
def get_supplier_info(part_id, supplier_idx):
    """Get supplier information by index"""
    conn = get_db_connection()
    if conn is None:
        return None
    
    suppliers = pd.read_sql_query(
        "SELECT * FROM part_suppliers WHERE part_id = ? ORDER BY supplier_name",
        conn, params=[part_id]
    )
    
    if not suppliers.empty and supplier_idx < len(suppliers):
        return suppliers.iloc[supplier_idx]
    return None

# --- Add Part Forms Renderer (module-level) ---
def render_part_forms():
    if 'current_part_management' not in st.session_state:
        st.session_state.current_part_management = {
            'current_part_index': 0,
            'parts_data': [],
            'saved_part_ids': []
        }

    current_mgmt = st.session_state.current_part_management

    with st.expander("Add Parts", expanded=len(current_mgmt['saved_part_ids']) == 0):
        st.subheader("Add New Parts")

        with st.form("add_multiple_parts_form", clear_on_submit=False):
            parts_data = []
            for i in range(st.session_state.part_count):
                st.markdown(f"**Part {i+1}**")
                part_name = st.text_input("Part Name*", key=f"part_name_{i}", help="At least name or number is required")
                part_number = st.text_input("Part Number", key=f"part_number_{i}")
                quantity = st.number_input("Quantity*", min_value=1, value=1, key=f"quantity_{i}")
                notes = st.text_area("Notes", key=f"notes_{i}")
                st.markdown("---")

                parts_data.append({
                    "name": part_name,
                    "number": part_number,
                    "quantity": quantity,
                    "notes": notes,
                })

            col1, col2 = st.columns(2)
            with col1:
                save_parts_btn = st.form_submit_button("Save Parts")
            with col2:
                cancel_btn = st.form_submit_button("Cancel")

            if save_parts_btn:
                all_valid = True
                validation_errors = []
                for idx, part in enumerate(parts_data):
                    if not part["name"] and not part["number"]:
                        all_valid = False
                        validation_errors.append(f"Part {idx+1}: Name or Number is required")

                if all_valid:
                    saved_ids = []
                    with st.spinner("Saving parts..."):
                        for part in parts_data:
                            try:
                                if st.session_state.view in ['add_part_to_existing_vin', 'add_part_for_client']:
                                    vin_match = df_vins[df_vins['vin_number'] == st.session_state.selected_vin_to_add_part]
                                    if vin_match.empty:
                                        st.error(f"VIN {st.session_state.selected_vin_to_add_part} not found in database")
                                        continue
                                    client_phone = vin_match['client_phone'].iloc[0]
                                    part_id = safe_add_part_to_vin(
                                        st.session_state.selected_vin_to_add_part,
                                        client_phone,
                                        part,
                                        [],
                                        st.session_state.username
                                    )
                                elif st.session_state.view == 'add_part_without_vin_flow':
                                    part_id = add_part_without_vin(
                                        part["name"],
                                        part["number"],
                                        part["quantity"],
                                        part["notes"],
                                        client_phone=None,
                                        suppliers=[],
                                        username=st.session_state.username
                                    )
                                elif st.session_state.view == 'add_part_without_vin_for_client':
                                    part_id = add_part_without_vin(
                                        part["name"],
                                        part["number"],
                                        part["quantity"],
                                        part["notes"],
                                        client_phone=st.session_state.current_client_phone,
                                        suppliers=[],
                                        username=st.session_state.username
                                    )
                                else:
                                    part_id = None

                                if part_id:
                                    saved_ids.append(part_id)
                            except Exception as e:
                                st.error(f"Error saving part: {str(e)}")

                    if saved_ids:
                        current_mgmt['saved_part_ids'] = saved_ids
                        st.success(f"Saved {len(saved_ids)} part(s). Now you can add suppliers below.")
                        # Clear cached data so new parts appear immediately after rerun
                        try:
                            st.cache_data.clear()
                        except Exception:
                            pass
                        st.session_state.need_rerun = True
                        st.rerun()
                else:
                    st.error("Please fix the following errors:")
                    for err in validation_errors:
                        st.write(f"- {err}")

    if current_mgmt['saved_part_ids']:
        st.subheader("Manage Suppliers for Saved Parts")
        for idx, part_id in enumerate(current_mgmt['saved_part_ids']):
            st.markdown(f"**Saved Part {idx+1} (ID: {part_id})**")
            existing_suppliers = df_part_suppliers[df_part_suppliers['part_id'] == part_id]
            if not existing_suppliers.empty:
                with st.expander("Current Suppliers"):
                    st.dataframe(existing_suppliers[['supplier_name','buying_price','selling_price','delivery_time']], width='stretch', hide_index=True)

            with st.form(f"add_supplier_form_{part_id}", clear_on_submit=True):
                supplier_name = st.text_input("Supplier Name*", help="Required field", key=f"supplier_name_{part_id}")
                buying_price = st.number_input("Buying Price ($)", min_value=0.0, value=0.0, format="%.2f", key=f"buying_price_{part_id}")
                selling_price = st.number_input("Selling Price ($)", min_value=0.0, value=0.0, format="%.2f", key=f"selling_price_{part_id}")
                delivery_time = st.text_input("Delivery Time", key=f"delivery_time_{part_id}")

                col1, col2 = st.columns(2)
                with col1:
                    add_supplier_btn = st.form_submit_button("Add Supplier")
                with col2:
                    cancel_supplier_btn = st.form_submit_button("Cancel")

                if add_supplier_btn:
                    if not supplier_name:
                        st.warning("Supplier name is required")
                    else:
                        try:
                            add_supplier_to_part(part_id, supplier_name, buying_price, selling_price, delivery_time, st.session_state.username)
                            st.success("Supplier added successfully!")
                            st.cache_data.clear()
                            st.session_state.need_rerun = True
                        except Exception as e:
                            st.error(f"Error adding supplier: {str(e)}")
    else:
        st.info("Please add and save parts first to manage suppliers.")

    # --- Call render_part_forms() for the 'add_part' views ---
if st.session_state.view in ['add_part_to_existing_vin', 'add_part_without_vin_flow', 'add_part_without_vin_for_client', 'add_part_for_client']:
    if st.session_state.view == 'add_part_to_existing_vin':
        st.header(f"Add Part to VIN: {st.session_state.selected_vin_to_add_part}")
    elif st.session_state.view == 'add_part_without_vin_flow':
        st.header("Add Part Without VIN")
    elif st.session_state.view == 'add_part_for_client':
        st.header(f"Add Part for Client: {st.session_state.current_client_name}")
        if st.session_state.selected_vin_to_add_part:
            st.write(f"**VIN:** {st.session_state.selected_vin_to_add_part}")
    elif st.session_state.view == 'add_part_without_vin_for_client':
        st.header(f"Add Part for Client: {st.session_state.current_client_name} (No VIN)")

    # Back button
    if st.button("Back"):
        if st.session_state.view in ['add_part_without_vin_flow', 'add_part_to_existing_vin']:
            st.session_state.view = 'main'
        else:
            st.session_state.view = 'client_details'
        st.session_state.need_rerun = True

    st.markdown("---")
    render_part_forms()

# --- ADD VIN TO EXISTING CLIENT FLOW ---
elif st.session_state.view == 'add_vin_to_existing_client':
    st.header("Add VIN for Existing Client")
    st.write(f"Client: **{st.session_state.current_client_name}** (Phone: {st.session_state.current_client_phone})")

    if not st.session_state.vin_added:
        with st.form("add_vin_form", clear_on_submit=True):
            vin_no = st.text_input("VIN Number")
            col1, col2 = st.columns([1, 1])
            with col1:
                submitted_vin = st.form_submit_button("Continue")
            with col2:
                if st.form_submit_button("Cancel"):
                    st.session_state.view = 'client_details'
                    st.session_state.need_rerun = True
            
            if submitted_vin:
                if vin_no and not validate_vin(vin_no):
                    st.error("Please enter a valid VIN (13-17 alphanumeric characters) or leave blank")
                else:
                    st.session_state.vin_added = True
                    st.session_state.current_vin_no = vin_no
                    st.session_state.need_rerun = True

    else:
        st.header("Add VIN Details")
        with st.form("add_vin_details_form", clear_on_submit=True):
            st.write(f"Add details for VIN **{st.session_state.current_vin_no}** for client **{st.session_state.current_client_name}** (Phone: {st.session_state.current_client_phone})")
            
            model = st.text_input("Model")
            prod_yr = st.text_input("Prod. Yr")
            body = st.text_input("Body")
            engine = st.text_input("Engine")
            code = st.text_input("Code")
            transmission = st.text_input("Transmission")

            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                submitted_details = st.form_submit_button("Save VIN Details")
            with col2:
                submitted_and_add_part = st.form_submit_button("Save Details & Add Part")
            with col3:
                if st.form_submit_button("Cancel"):
                    st.session_state.view = 'client_details'
                    st.session_state.vin_added = False
                    st.session_state.need_rerun = True
            
            if submitted_details or submitted_and_add_part:
                vin_to_save = st.session_state.current_vin_no if st.session_state.current_vin_no else None
                
                try:
                    # Clean the VIN if it's not empty
                    if vin_to_save:
                        clean_vin = ''.join(vin_to_save.split()).upper()
                        if not validate_vin(clean_vin):
                            st.error("Invalid VIN format. Must be 7, 13, or 17 alphanumeric characters, or empty.")
                            st.stop()
                    else:
                        clean_vin = None
                    
                    with st.spinner("Saving VIN details..."):
                        add_vin_to_client(str(st.session_state.current_client_phone), clean_vin, model, prod_yr, body, engine, code, transmission, st.session_state.username)
                    st.success(f"✅ VIN details saved for {clean_vin if clean_vin else 'No VIN'}!")
                    
                    if submitted_and_add_part:
                        st.session_state.selected_vin_to_add_part = clean_vin if clean_vin else "No VIN provided"
                        st.session_state.view = 'add_part_for_client'
                    else:
                        st.session_state.view = 'client_details'
                    
                    st.session_state.vin_added = False
                    st.session_state.current_vin_no = None
                    st.cache_data.clear()
                    st.session_state.need_rerun = True
                    
                except ValueError as e:
                    st.error(str(e))

# --- SEQUENTIAL CLIENT AND VIN REGISTRATION FLOW ---
elif st.session_state.view == 'add_client':
    if not st.session_state.client_added:
        st.header("Register New Client")
        with st.form("new_client_form", clear_on_submit=True):
            phone = st.text_input("Phone*", help="Required field (7-15 digits)")
            client_name = st.text_input("Client Name")
            
            col1, col2 = st.columns([1,1])
            with col1:
                submitted = st.form_submit_button("Add Client")
            with col2:
                if st.form_submit_button("Back to Main"):
                    reset_view_and_state()
            
            if submitted:
                if phone:
                    if not validate_phone(phone):
                        st.error("Please enter a valid phone number (7-15 digits)")
                    else:
                        try:
                            with st.spinner("Adding new client..."):
                                add_new_client(str(phone), client_name, st.session_state.username)
                            st.session_state.client_added = True
                            st.session_state.current_client_phone = str(phone)
                            st.session_state.current_client_name = client_name
                            st.cache_data.clear()
                            st.session_state.need_rerun = True
                        except ValueError as e:
                            st.error(str(e))
                else:
                    st.warning("Please enter a valid phone number.")

    elif not st.session_state.vin_added:
        st.header("Add VIN for Client")
        with st.form("add_vin_form", clear_on_submit=True):
            st.write(f"Add VIN for: **{st.session_state.current_client_name}** (Phone: {st.session_state.current_client_phone})")
            vin_no = st.text_input("VIN Number", help="Optional: 13-17 alphanumeric characters or leave blank")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                submitted_vin = st.form_submit_button("Continue")
            with col2:
                if st.form_submit_button("Skip and Go to Client Details"):
                    st.session_state.view = 'client_details'
                    st.session_state.client_added = False
                    st.session_state.need_rerun = True
            
            if submitted_vin:
                if vin_no and not validate_vin(vin_no):
                    st.error("Please enter a valid VIN (13-17 alphanumeric characters) or leave blank")
                else:
                    st.session_state.vin_added = True
                    st.session_state.current_vin_no = vin_no
                    st.session_state.need_rerun = True
    
    else:
        st.header("Add VIN Details")
        with st.form("add_vin_details_form", clear_on_submit=True):
            st.write(f"Add details for VIN **{st.session_state.current_vin_no}** for client **{st.session_state.current_client_name}** (Phone: {st.session_state.current_client_phone})")
            
            model = st.text_input("Model")
            prod_yr = st.text_input("Prod. Yr")
            body = st.text_input("Body")
            engine = st.text_input("Engine")
            code = st.text_input("Code")
            transmission = st.text_input("Transmission")

            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                submitted_details = st.form_submit_button("Save VIN Details")
            with col2:
                submitted_and_add_part = st.form_submit_button("Save Details & Add Part")
            with col3:
                if st.form_submit_button("Cancel"):
                    st.session_state.view = 'client_details'
                    st.session_state.vin_added = False
                    st.session_state.need_rerun = True
            
            if submitted_details or submitted_and_add_part:
                vin_to_save = st.session_state.current_vin_no if st.session_state.current_vin_no else None
                
                try:
                    # Clean the VIN if it's not empty
                    if vin_to_save:
                        clean_vin = ''.join(vin_to_save.split()).upper()
                        if not validate_vin(clean_vin):
                            st.error("Invalid VIN format. Must be 7, 13, or 17 alphanumeric characters, or empty.")
                            st.stop()
                    else:
                        clean_vin = None
                    
                    with st.spinner("Saving VIN details..."):
                        # FIXED: Use st.session_state.current_client_phone instead of undefined 'phone' variable
                        add_vin_to_client(
                            str(st.session_state.current_client_phone),  # FIXED HERE
                            clean_vin,
                            model,
                            prod_yr,
                            body,
                            engine,
                            code,
                            transmission,
                            st.session_state.username
                        )
                    st.success(f"✅ VIN details saved for {clean_vin if clean_vin else 'No VIN'}!")
                    
                    if submitted_and_add_part:
                        st.session_state.selected_vin_to_add_part = clean_vin if clean_vin else "No VIN provided"
                        st.session_state.view = 'add_part_for_client'
                    else:
                        st.session_state.view = 'client_details'
                    
                    st.session_state.vin_added = False
                    st.session_state.current_vin_no = None
                    st.cache_data.clear()
                    st.session_state.need_rerun = True
                    
                except ValueError as e:
                    st.error(str(e))

# --- SEARCH RESULTS VIEW ---
elif st.session_state.view == 'search_results':
    st.header("Search Results")
    if st.button("⬅️ Back to Main"):
        reset_view_and_state()
    
    search_results = st.session_state.get('search_results', {})
    
    if search_results:
        if not search_results['clients'].empty:
            st.subheader("Clients")
            st.dataframe(search_results['clients'][['client_name', 'phone']], width='stretch')
        
        if not search_results['vins'].empty:
            st.subheader("VINs")
            st.dataframe(search_results['vins'][['vin_number', 'model', 'client_phone']], width='stretch')
        
        if not search_results['parts'].empty:
            st.subheader("Parts")
            st.dataframe(search_results['parts'][['part_name', 'part_number', 'quantity', 'client_phone', 'vin_number']], width='stretch')
        
        if search_results['clients'].empty and search_results['vins'].empty and search_results['parts'].empty:
            st.info("No results found for your search.")
    else:
        st.info("No search results to display.")

if __name__ == "__main__":
    if st.session_state.get('need_rerun', False):
        st.session_state.need_rerun = False
        st.rerun()
