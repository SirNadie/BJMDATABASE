import os
import sqlite3
import streamlit as st
from datetime import datetime

from db_utils import DB_NAME, database_maintenance, export_filtered_data
from auth import logout


def main_navigation():
    st.sidebar.title("Navigation")
    if st.sidebar.button("Main Dashboard"):
        st.session_state.view = 'main'
        st.session_state.need_rerun = True

    if st.sidebar.button("Clients"):
        st.session_state.view = 'client_list'
        st.session_state.need_rerun = True
    if st.sidebar.button("Parts Inventory"):
        st.session_state.view = 'view_parts_inventory'
        st.session_state.need_rerun = True
    if st.sidebar.button("Generate Quote"):
        st.session_state.view = 'generate_pdf_flow'
        st.session_state.document_type = 'quote'
        st.session_state.need_rerun = True
    if st.sidebar.button("Generate Invoice"):
        st.session_state.view = 'generate_pdf_flow'
        st.session_state.document_type = 'invoice'
        st.session_state.need_rerun = True
    if st.sidebar.button("Text Quote"):
        st.session_state.view = 'generate_text_quote_flow'
        st.session_state.need_rerun = True

    # Admin-only tools
    if st.session_state.get('user_role') == 'admin':
        st.sidebar.markdown("---")
        if st.sidebar.button("View Activity Logs"):
            st.session_state.view = 'activity_logs'
            st.session_state.need_rerun = True
        if st.sidebar.button("User Management"):
            st.session_state.view = 'user_management'
            st.session_state.need_rerun = True

    st.sidebar.markdown("---")
    user = st.session_state.get('username') or 'User'
    role = st.session_state.get('user_role') or 'user'
    st.sidebar.info(f"Logged in as: {user} ({role})")
    st.sidebar.button("Logout", on_click=logout)


def global_search(df_clients, df_vins, df_parts):
    st.sidebar.markdown("---")
    st.sidebar.subheader("Global Search")
    search_term = st.sidebar.text_input("Search across all data")

    if search_term:
        client_results = df_clients[
            df_clients['client_name'].str.contains(search_term, case=False)
            | df_clients['phone'].str.contains(search_term, case=False)
        ]

        vin_results = df_vins[
            df_vins['vin_number'].str.contains(search_term, case=False)
            | df_vins['model'].str.contains(search_term, case=False)
        ]

        part_results = df_parts[
            df_parts['part_name'].str.contains(search_term, case=False)
            | df_parts['part_number'].str.contains(search_term, case=False)
        ]

        if not client_results.empty or not vin_results.empty or not part_results.empty:
            st.sidebar.success(
                f"Found {len(client_results)} clients, {len(vin_results)} VINs, {len(part_results)} parts"
            )

            if st.sidebar.button("View Search Results"):
                st.session_state.view = 'search_results'
                st.session_state.search_results = {
                    'clients': client_results,
                    'vins': vin_results,
                    'parts': part_results,
                }
                st.session_state.need_rerun = True


def export_data():
    st.sidebar.markdown("---")
    st.sidebar.subheader("Data Export")

    export_type = st.sidebar.selectbox("Export Format", ["CSV (ZIP)", "Excel"])

    with st.sidebar.expander("Export Filters"):
        st.write("Filter data to export:")
        include_tables = st.multiselect(
            "Include Tables",
            ["clients", "vins", "parts", "part_suppliers"],
            default=["clients", "vins", "parts", "part_suppliers"],
        )

        client_filter = st.text_input("Filter by Client Phone")
        vin_filter = st.text_input("Filter by VIN Number")

        filters = {}
        if client_filter:
            filters['client_phone'] = client_filter
        if vin_filter:
            filters['vin_number'] = vin_filter
        if include_tables:
            filters['include'] = include_tables

    if st.sidebar.button("Export Data"):
        with st.spinner("Preparing export..."):
            try:
                format_type = 'excel' if export_type == "Excel" else 'csv'
                data, mime_type = export_filtered_data(filters, format_type)

                file_ext = "xlsx" if export_type == "Excel" else "zip"
                file_name = f"brent_j_marketing_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_ext}"

                st.sidebar.download_button(
                    label=f"Download {export_type}",
                    data=data,
                    file_name=file_name,
                    mime=mime_type,
                )
                from auth import log_activity

                log_activity("User", "export_data", f"Exported {export_type} with filters: {filters}")
            except Exception as e:
                st.sidebar.error(f"Export failed: {str(e)}")


def backup_database():
    import shutil
    import datetime as _dt

    st.sidebar.markdown("---")
    st.sidebar.subheader("Backup Management")

    if st.sidebar.button("Backup Database Now"):
        backup_name = f"backup_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2('brent_j_marketing.db', backup_name)
        st.sidebar.success(f"Backup created: {backup_name}")
        from auth import log_activity

        log_activity("User", "backup", f"Created backup: {backup_name}")

    backups = [f for f in os.listdir('.') if f.startswith('backup_') and f.endswith('.db')]
    if backups:
        st.sidebar.write("**Existing Backups:**")
        for backup in sorted(backups, reverse=True)[:5]:
            st.sidebar.write(f"- {backup}")


def confirm_action_interface():
    if st.session_state.confirm_action:
        st.sidebar.warning(st.session_state.confirm_action['message'])
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("Confirm"):
                st.session_state.confirm_action['action']()
                st.session_state.confirm_action = None
                st.session_state.need_rerun = True
        with col2:
            if st.button("Cancel"):
                st.session_state.confirm_action = None
                st.session_state.need_rerun = True


def database_maintenance_interface():
    st.sidebar.markdown("---")
    st.sidebar.subheader("Database Maintenance")

    if st.sidebar.button("Optimize Database"):
        if database_maintenance():
            st.sidebar.success("Database optimized!")
            from auth import log_activity

            log_activity("User", "maintenance", "Database optimization")
        else:
            st.sidebar.error("Database optimization failed")

    if st.sidebar.button("Check Database Integrity"):
        with sqlite3.connect(DB_NAME) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] == "ok":
            st.sidebar.success("Database integrity: OK")
        else:
            st.sidebar.error(f"Database issues: {result[0]}")
        from auth import log_activity

        log_activity("User", "maintenance", "Database integrity check")
