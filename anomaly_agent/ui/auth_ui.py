"""Login screen and account box. The rules themselves live in anomaly_agent/auth.py."""
import streamlit as st

from anomaly_agent.auth import AuthError, login, register_user
from anomaly_agent.db.database import DatabaseUnavailable, session_scope

USER_KEY = "auth_user"


def current_user():
    return st.session_state.get(USER_KEY)


def require_login(public_demo):
    """Return the logged-in user. Without one, show the login screen and stop the page.

    The public demo has no accounts at all, so it returns None and the page goes on.
    """
    if public_demo:
        return None
    user = current_user()
    if user is None:
        show_login_screen()
        st.stop()
    return user


def _sign_in(user):
    st.session_state[USER_KEY] = user
    st.rerun()


def show_login_screen():
    st.title("Excel Anomaly Agent")
    st.markdown(
        '<div class="page-sub">Log in to analyse your data. Saved analyses belong to your account only.</div>',
        unsafe_allow_html=True,
    )
    login_tab, register_tab = st.tabs(["Log in", "Create account"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", key="login_submit")
        if submitted:
            try:
                with session_scope() as session:
                    user = login(session, email, password)
            except AuthError as error:
                st.error(str(error))
            except DatabaseUnavailable as error:
                st.error(str(error))
            else:
                _sign_in(user)

    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Your name", key="register_name")
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password", type="password", key="register_password",
                                     help="At least 8 characters, with a letter and a number.")
            again = st.text_input("Repeat the password", type="password", key="register_again")
            submitted = st.form_submit_button("Create account", key="register_submit")
        if submitted:
            try:
                if password != again:
                    raise AuthError("The two passwords are not the same.")
                with session_scope() as session:
                    user = register_user(session, name, email, password)
            except AuthError as error:
                st.error(str(error))
            except DatabaseUnavailable as error:
                st.error(str(error))
            else:
                _sign_in(user)


def render_account_box(user):
    """Who is logged in, and the Log out button (top of the sidebar)."""
    if user is None:
        return
    box = st.sidebar.container(border=True)
    box.caption("Signed in as")
    box.markdown(f"**{user['name']}**")
    box.text(user["email"])
    if box.button("Log out", key="logout", width="stretch"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]  # forget the user and every page setting
        st.rerun()
