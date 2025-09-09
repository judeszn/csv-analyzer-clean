"""
Integrated webhook endpoint for Streamlit app.
This adds webhook handling directly to the main Streamlit application.
"""

import streamlit as st
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import json
import threading
import uvicorn
from typing import Optional

from app.services.webhook_service import StripeWebhookHandler
from app.utils.logging_config import get_logger

logger = get_logger('webhook_integration')

# Global webhook handler instance
webhook_handler = StripeWebhookHandler()

def create_webhook_app():
    """Create FastAPI app for webhook handling."""
    app = FastAPI(title="CSV Analyzer Webhooks")
    
    @app.post("/webhook/stripe")
    async def stripe_webhook(request: Request):
        """Handle Stripe webhook events."""
        try:
            # Get the raw body and signature
            body = await request.body()
            signature = request.headers.get('stripe-signature')
            
            if not signature:
                raise HTTPException(status_code=400, detail="Missing Stripe signature")
            
            # Verify webhook signature
            if not webhook_handler.verify_webhook_signature(body, signature):
                raise HTTPException(status_code=400, detail="Invalid webhook signature")
            
            # Parse and handle the event
            event_data = json.loads(body)
            result = webhook_handler.handle_webhook_event(event_data)
            
            logger.info(f"Webhook processed: {result}")
            return JSONResponse(content=result)
            
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/webhook/health")
    async def webhook_health():
        """Health check for webhook service."""
        return {"status": "healthy", "service": "stripe_webhooks"}
    
    return app

def start_webhook_server():
    """Start webhook server in background thread."""
    webhook_app = create_webhook_app()
    uvicorn.run(webhook_app, host="0.0.0.0", port=8001, log_level="info")

def initialize_webhook_service():
    """Initialize webhook service if not already running."""
    if 'webhook_server_started' not in st.session_state:
        thread = threading.Thread(target=start_webhook_server, daemon=True)
        thread.start()
        st.session_state.webhook_server_started = True
        logger.info("Webhook server started on port 8001")
