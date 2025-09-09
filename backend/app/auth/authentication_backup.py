import streamlit as st
from .supabase_client import supabase_client
from ..utils.logging_config import get_logger
from ..config.admin_config import AdminConfig
from ..core.db_usage_tracker import DBUsageTracker

logger = get_logger('csv_analyzer')

def display_auth_form():
    """
    Displays login and registration forms.
    Returns user object on successful login/registration, otherwise None.
    """
    st.markdown("### 🔑 Welcome to CSV Analyzer Pro")
    
    # Check for existing session
    session = supabase_client.auth.get_session()
    if session and session.user:
        st.session_state['user'] = session.user
        return session.user

    col1, col2 = st.columns(2)

    with col1:
        with st.form("login_form"):
            st.markdown("#### 🔐 Login")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            login_button = st.form_submit_button("Login")

            if login_button:
                try:
                    response = supabase_client.auth.sign_in_with_password({
                        "email": email,
                        "password": password
                    })
                    
                    if response.user:
                        st.session_state['user'] = response.user
                        logger.info(f"User logged in: {response.user.email}")
                        
                        # Auto-upgrade admin user if configured
                        if AdminConfig.is_admin_email(email) and AdminConfig.should_auto_upgrade():
                            try:
                                usage_tracker = DBUsageTracker()
                                if usage_tracker.upgrade_user_by_email(email, "admin"):
                                    logger.info(f"Auto-upgraded admin user: {email}")
                            except Exception as e:
                                logger.warning(f"Auto-upgrade failed for {email}: {e}")
                        
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Login failed. Please check your credentials.")
                        
                except Exception as e:
                    st.error(f"Login failed: {e}")

    with col2:
        with st.form("signup_form"):
            st.markdown("#### 🚀 Sign Up")
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            signup_button = st.form_submit_button("Sign Up")

            if signup_button:
                try:
                    user_session = supabase_client.auth.sign_up({
                        "email": email,
                        "password": password
                    })
                    
                    if user_session.user:
                        st.session_state['user'] = user_session.user
                        logger.info(f"New user signed up: {user_session.user.email}")
                        
                        # Auto-upgrade admin user if configured
                        if AdminConfig.is_admin_email(email) and AdminConfig.should_auto_upgrade():
                            try:
                                usage_tracker = DBUsageTracker()
                                if usage_tracker.upgrade_user_by_email(email, "admin"):
                                    logger.info(f"Auto-upgraded new admin user: {email}")
                            except Exception as e:
                                logger.warning(f"Auto-upgrade failed for new user {email}: {e}")
                        
                        st.success("Signup successful! You can now start using the application.")
                        st.rerun()
                    else:
                        st.info("Please check your email to verify your account before logging in.")
                        
                except Exception as e:
                    st.error(f"Signup failed: {e}")
    
    return None

def handle_logout():
    """Handles user logout."""
    if st.sidebar.button("Logout"):
        try:
            supabase_client.auth.sign_out()
            if 'user' in st.session_state:
                del st.session_state['user']
            logger.info("User logged out")
            st.rerun()
        except Exception as e:
            st.error(f"Logout failed: {e}")
