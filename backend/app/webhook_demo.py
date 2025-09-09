import streamlit as st
import json
import sys
import os
from datetime import datetime

# Add the project root to the Python path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.webhook_service import webhook_handler
from app.utils.logging_config import get_logger

logger = get_logger('csv_analyzer')

def create_webhook_endpoint():
    """
    Creates a webhook endpoint for Stripe events.
    
    Note: In production, you'll want to use a proper web framework like FastAPI
    or Flask for webhook endpoints, not Streamlit.
    
    This is a demonstration of the webhook logic.
    """
    
    st.markdown("# 🔗 Stripe Webhook Configuration")
    
    st.info("""
    **Important**: Streamlit is not ideal for webhook endpoints in production.
    Consider using FastAPI, Flask, or Django for your webhook handler.
    """)
    
    # Webhook configuration guide
    st.markdown("""
    ## 📋 **Webhook Setup Guide**
    
    ### 1. **Create Webhook Endpoint in Stripe Dashboard**
    
    1. Go to [Stripe Dashboard > Developers > Webhooks](https://dashboard.stripe.com/webhooks)
    2. Click "Add endpoint"
    3. Set endpoint URL: `https://yourdomain.com/webhook/stripe`
    4. Select these events:
       - `checkout.session.completed`
       - `customer.subscription.updated` 
       - `customer.subscription.deleted`
       - `invoice.payment_succeeded`
       - `invoice.payment_failed`
    
    ### 2. **Get Your Webhook Secret**
    
    After creating the webhook:
    1. Click on your webhook endpoint
    2. Click "Reveal" next to "Signing secret"
    3. Copy the secret (starts with `whsec_`)
    4. Update your `.env` file with this secret
    
    ### 3. **Production Webhook URL**
    
    Your webhook URL should be:
    ```
    https://yourdomain.com/webhook/stripe
    ```
    
    For testing, you can use:
    ```
    https://your-ngrok-url.ngrok.io/webhook/stripe
    ```
    """)
    
    # Current configuration
    st.markdown("## ⚙️ **Current Configuration**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        webhook_secret = st.text_input(
            "Webhook Secret",
            value="whsec_your_secret_here",
            type="password",
            help="Get this from your Stripe webhook settings"
        )
    
    with col2:
        webhook_url = st.text_input(
            "Webhook URL",
            value="https://yourdomain.com/webhook/stripe",
            help="Your production webhook endpoint"
        )
    
    # Test webhook payload
    st.markdown("## 🧪 **Test Webhook Handling**")
    
    sample_event = {
        "id": "evt_test_webhook",
        "object": "event",
        "api_version": "2020-08-27",
        "created": int(datetime.now().timestamp()),
        "data": {
            "object": {
                "id": "cs_test_checkout_session",
                "object": "checkout.session",
                "customer": "cus_test_customer",
                "subscription": "sub_test_subscription",
                "metadata": {
                    "user_id": "test_user_123"
                },
                "payment_status": "paid"
            }
        },
        "type": "checkout.session.completed"
    }
    
    if st.button("🔬 Test Checkout Completion Event"):
        try:
            result = webhook_handler.handle_webhook_event(sample_event)
            st.success(f"✅ Webhook processed: {result}")
        except Exception as e:
            st.error(f"❌ Webhook error: {e}")
    
    # Show sample webhook events
    with st.expander("📄 Sample Webhook Events"):
        st.code(json.dumps(sample_event, indent=2), language="json")
    
    # Security considerations
    st.markdown("""
    ## 🔒 **Security Best Practices**
    
    1. **Verify Signatures**: Always verify webhook signatures from Stripe
    2. **Idempotency**: Handle duplicate events gracefully
    3. **HTTPS Only**: Never use HTTP for webhook endpoints
    4. **Rate Limiting**: Implement rate limiting on your webhook endpoint
    5. **Error Handling**: Return appropriate HTTP status codes
    6. **Logging**: Log all webhook events for debugging
    """)

if __name__ == "__main__":
    create_webhook_endpoint()
