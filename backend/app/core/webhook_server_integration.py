"""
Integrated webhook endpoint that runs alongside Streamlit.
This adds webhook handling to the main Streamlit application via threading.
"""

import streamlit as st
import threading
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import json
from typing import Optional
import os

from app.services.webhook_service import webhook_handler
from app.utils.logging_config import get_logger

logger = get_logger('webhook_integration')

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
                logger.error("Missing Stripe signature")
                raise HTTPException(status_code=400, detail="Missing Stripe signature")
            
            # Verify webhook signature
            if not webhook_handler.verify_webhook_signature(body, signature):
                logger.error("Invalid webhook signature")
                raise HTTPException(status_code=400, detail="Invalid webhook signature")
            
            # Parse and handle the event
            event_data = json.loads(body)
            result = webhook_handler.handle_webhook_event(event_data)
            
            logger.info(f"Webhook processed successfully: {result}")
            return JSONResponse(content=result)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook body: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/webhook/health")
    async def webhook_health():
        """Health check for webhook service."""
        return {
            "status": "healthy", 
            "service": "stripe_webhooks",
            "timestamp": time.time()
        }
    
    @app.get("/")
    async def webhook_root():
        """Root endpoint for webhook service."""
        return {
            "service": "CSV Analyzer Pro Webhooks",
            "status": "active",
            "endpoints": ["/webhook/stripe", "/webhook/health"]
        }
    
    return app

def start_webhook_server():
    """Start webhook server in background thread."""
    try:
        webhook_port = int(os.environ.get("WEBHOOK_PORT", "8001"))
        webhook_app = create_webhook_app()
        
        logger.info(f"Starting webhook server on port {webhook_port}")
        
        # Run with minimal logging to avoid conflicts with Streamlit
        uvicorn.run(
            webhook_app, 
            host="0.0.0.0", 
            port=webhook_port,
            log_level="warning"  # Reduce log noise
        )
    except Exception as e:
        logger.error(f"Failed to start webhook server: {e}")

def initialize_webhook_service():
    """Initialize webhook service if not already running."""
    if not hasattr(st.session_state, 'webhook_server_started'):
        try:
            # Start webhook server in daemon thread
            webhook_thread = threading.Thread(
                target=start_webhook_server, 
                daemon=True,
                name="WebhookServer"
            )
            webhook_thread.start()
            
            st.session_state.webhook_server_started = True
            logger.info("Webhook server thread started successfully")
            
            # Give it a moment to start
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Failed to initialize webhook service: {e}")
            st.session_state.webhook_server_started = False

def show_webhook_status():
    """Display webhook status in Streamlit (for debugging)."""
    if hasattr(st.session_state, 'webhook_server_started') and st.session_state.webhook_server_started:
        webhook_port = os.environ.get("WEBHOOK_PORT", "8001")
        st.sidebar.success(f"🎣 Webhook Server: Active (Port {webhook_port})")
    else:
        st.sidebar.error("🚨 Webhook Server: Not Running")
