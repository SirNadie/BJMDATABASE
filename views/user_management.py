import streamlit as st
from auth import require_admin
from db_utils import (
    list_users,
    create_user,
    update_user_password,
    set_user_active,
)


def render_user_management_view():
    require_admin()
    st.header("User Management")

    if st.button("Back to Main"):
        st.session_state.view = 'main'
        st.session_state.need_rerun = True
        return

    st.info("Only one admin account is allowed. New users are created with role 'user'.")

    st.subheader("Create New User")
    with st.form("create_user_form", clear_on_submit=True):
        new_username = st.text_input("Username", key="um_new_username")
        new_password = st.text_input("Password", type="password", key="um_new_password")
        submitted = st.form_submit_button("Create User")
    if submitted:
        if not new_username or not new_password:
            st.warning("Username and password are required")
        else:
            ok, msg = create_user(new_username.strip(), new_password, 'user', st.session_state.username)
            if ok:
                st.success("User created")
                st.session_state.need_rerun = True
                st.rerun()
            else:
                st.error(msg)

    st.divider()

    st.subheader("Existing Users")
    users_df = list_users()
    if users_df.empty:
        st.info("No users found.")
        return

    # Display table
    st.dataframe(users_df, width='stretch')

    st.markdown("---")
    st.subheader("Manage Accounts")
    # Simple controls for password reset and activation per user
    for _, row in users_df.iterrows():
        username = row['username']
        role = row['role']
        is_active = bool(row.get('is_active', 1))

        with st.expander(f"{username} ({role})"):
            # Password reset
            new_pw = st.text_input(f"New password for {username}", type="password", key=f"pw_{username}")
            if st.button(f"Update Password for {username}", key=f"btn_pw_{username}"):
                if not new_pw:
                    st.warning("Password required")
                else:
                    ok, msg = update_user_password(username, new_pw, st.session_state.username)
                    if ok:
                        st.success("Password updated")
                    else:
                        st.error(msg)

            # Activation toggle (not allowed to deactivate last admin; backend enforces)
            desired_active = st.checkbox("Active", value=is_active, key=f"active_{username}")
            if desired_active != is_active:
                ok, msg = set_user_active(username, desired_active, st.session_state.username)
                if ok:
                    st.success("Status updated")
                    st.session_state.need_rerun = True
                    st.rerun()
                else:
                    st.error(msg)
