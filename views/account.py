import streamlit as st

from anomaly_agent.auth import AuthError, change_password, delete_account
from anomaly_agent.db.analyses import list_analyses
from anomaly_agent.db.database import DatabaseUnavailable, get_engine, session_scope
from anomaly_agent.db.models import User
from anomaly_agent.ui.auth_ui import USER_KEY, current_user
from anomaly_agent.ui.theme import page_header

user = current_user()
page_header("Account", "Your details and your security settings.")

try:
    with session_scope() as session:
        record = session.get(User, user["id"])
        member_since = record.created_at.strftime("%d %b %Y") if record else "n/a"
        last_login = record.last_login.strftime("%d %b %Y %H:%M UTC") if record and record.last_login else "n/a"
    database = get_engine().dialect.name
except DatabaseUnavailable as error:
    st.error(str(error))
    st.stop()

with session_scope() as session:
    saved_count = len(list_analyses(session, user["id"], limit=1000))
c1, c2 = st.columns(2)
c1.metric("Name", user["name"], border=True)
c2.metric("Saved analyses", saved_count, border=True)
c3, c4 = st.columns(2)
c3.metric("Member since", member_since, border=True)
c4.metric("Last login", last_login, border=True)
database_name = {"postgresql": "PostgreSQL", "sqlite": "SQLite"}.get(database, database)
st.caption(f"Data is stored in {database_name}. Passwords are stored only as bcrypt hashes.")

st.subheader("Change password")
with st.form("change_password"):
    current = st.text_input("Current password", type="password", key="cp_current")
    new = st.text_input("New password", type="password", key="cp_new")
    again = st.text_input("Repeat the new password", type="password", key="cp_again")
    go = st.form_submit_button("Change password", key="cp_submit")
if go:
    try:
        if new != again:
            raise AuthError("The two new passwords are not the same.")
        with session_scope() as session:
            change_password(session, user["id"], current, new)
    except AuthError as error:
        st.error(str(error))
    else:
        st.success("Password changed.")

st.subheader("Delete account")
st.caption("This deletes your account and every analysis you saved. It cannot be undone.")
with st.form("delete_account"):
    password = st.text_input("Type your password to confirm", type="password", key="da_password")
    sure = st.checkbox("I understand that my saved analyses will be deleted", key="da_sure")
    go = st.form_submit_button("Delete my account", key="da_submit")
if go:
    try:
        if not sure:
            raise AuthError("Please tick the box to confirm.")
        with session_scope() as session:
            delete_account(session, user["id"], password)
    except AuthError as error:
        st.error(str(error))
    else:
        st.session_state.pop(USER_KEY, None)
        st.rerun()
