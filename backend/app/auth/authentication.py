import streamlit as st
import os
from .supabase_client import supabase_client
from ..utils.logging_config import get_logger

logger = get_logger('csv_analyzer')

def display_auth_form():
    """
    Simple, clean authentication form that prioritizes fallback mode.
    """
    st.markdown("### Welcome to Universal Insight Engine")

    # First priority: Check for fallback mode (for deployment stability)
    if os.environ.get('FALLBACK_TO_TEST_USER', 'false').lower() == 'true':
        # Create test user without showing warning message
        test_user = type('TestUser', (), {
            'id': 'fallback-test-user',
            'email': 'fallback-test@example.com',
            'user_metadata': {'name': 'Fallback Test User'}
        })()
        st.session_state['user'] = test_user
        return test_user

    # Second priority: If user is already in session, return them
    if 'user' in st.session_state and st.session_state['user']:
        return st.session_state['user']

    # Third priority: Try to get existing session (but don't fail hard)
    try:
        if supabase_client:
            session = supabase_client.auth.get_session()
            if session and session.user:
                st.session_state['user'] = session.user
                return session.user
    except Exception as e:
        # Log the error but don't show it to user - just proceed to login forms
        logger.error(f"Session check failed (will show login forms): {str(e)}")

    # Final priority: Show login/signup forms
    col1, col2 = st.columns(2)

    with col1:
        with st.form("login_form"):
            st.markdown("#### 🔐 Login")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            login_button = st.form_submit_button("Login")

            if login_button:
                if not email or not password:
                    st.error("Please fill in all fields")
                else:
                    try:
                        user_session = supabase_client.auth.sign_in_with_password({
                            "email": email,
                            "password": password
                        })
                        
                        if user_session.user:
                            # Clear any existing UI states
                            for key in list(st.session_state.keys()):
                                if key.startswith('ui_') or key in ['messages', 'processed_content', 'file_type']:
                                    st.session_state.pop(key, None)
                                    
                            st.session_state['user'] = user_session.user
                            st.session_state['authenticated'] = True  # Explicitly mark as authenticated
                            logger.info(f"User logged in: {user_session.user.email}")
                            st.success("✅ Login successful!")
                            st.rerun()
                        else:
                            st.error("❌ Login failed. Please check your credentials.")
                            
                    except Exception as e:
                        error_msg = str(e)
                        if "invalid login credentials" in error_msg.lower():
                            st.error("❌ **Invalid credentials**. Please check your email and password.")
                        else:
                            st.error(f"Login failed: {error_msg}")
                            logger.error(f"Login error for {email}: {error_msg}")

    with col2:
        with st.form("signup_form"):
            st.markdown("#### 🚀 Sign Up")
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            signup_button = st.form_submit_button("Sign Up")

            if signup_button:
                if not email or not password:
                    st.error("Please fill in all fields")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters long")
                else:
                    try:
                        user_session = supabase_client.auth.sign_up({
                            "email": email,
                            "password": password
                        })
                        
                        if user_session.user:
                            # Clear any existing UI states
                            for key in list(st.session_state.keys()):
                                if key.startswith('ui_') or key in ['messages', 'processed_content', 'file_type']:
                                    st.session_state.pop(key, None)
                                    
                            st.session_state['user'] = user_session.user
                            st.session_state['authenticated'] = True  # Explicitly mark as authenticated
                            logger.info(f"New user signed up and logged in: {user_session.user.email}")
                            st.success("✅ Sign up successful! You are now logged in.")
                            st.rerun()
                        else:
                            try:
                                user_session = supabase_client.auth.sign_in_with_password({
                                    "email": email,
                                    "password": password
                                })
                                if user_session.user:
                                    # Clear any existing UI states
                                    for key in list(st.session_state.keys()):
                                        if key.startswith('ui_') or key in ['messages', 'processed_content', 'file_type']:
                                            st.session_state.pop(key, None)
                                            
                                    st.session_state['user'] = user_session.user
                                    st.session_state['authenticated'] = True  # Explicitly mark as authenticated
                                    logger.info(f"Existing user logged in after signup attempt: {user_session.user.email}")
                                    st.success("✅ Welcome back! You are now logged in.")
                                    st.rerun()
                                else:
                                    st.error("An error occurred during signup. Please try again.")
                            except Exception:
                                st.error("This email may already be registered. Please try logging in.")

                    except Exception as e:
                        error_msg = str(e)
                        if "User already registered" in error_msg or "already registered" in error_msg.lower():
                            st.warning("This email is already registered. Please log in.")
                        else:
                            st.error(f"Sign up failed: {error_msg}")
                            logger.error(f"Signup error for {email}: {error_msg}")
    
    return None

def handle_logout():
    """Clean logout - reset session state."""
    if st.sidebar.button("Logout"):
        # Clear authentication state
        if 'user' in st.session_state:
            del st.session_state['user']
        
        # Clear authenticated flag
        if 'authenticated' in st.session_state:
            del st.session_state['authenticated']
            
        # Clear all UI state
        for key in list(st.session_state.keys()):
            if key.startswith('ui_') or key in ['messages', 'processed_content', 'file_type', 'uploaded_file_name']:
                st.session_state.pop(key, None)
        
        logger.info("User logged out")
        st.rerun()
