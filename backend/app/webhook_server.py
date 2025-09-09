"""
Production-ready webhook endpoint for Stripe events.

Usage:
    pip install fastapi uvicorn
    uvicorn app.webhook_server:app --host 0.0.0.0 --port 8001

For production deployment:
    - Use a proper WSGI server like Gunicorn
    - Set up SSL/TLS certificates
    - Configure reverse proxy (nginx)
    - Set up monitoring and logging
"""

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import json
import asyncio
from typing import Optional

from app.services.webhook_service import webhook_handler
from app.utils.logging_config import get_logger

logger = get_logger('webhook_server')

app = FastAPI(
    title="CSV Analyzer Pro - Webhook Server",
    description="Stripe webhook handler for subscription management",
    version="1.0.0"
)

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "CSV Analyzer Pro Webhook Server"}

@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "timestamp": "2025-09-05T00:00:00Z",
        "version": "1.0.0",
        "webhook_handler": "active"
    }

@app.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature")
):
    """
    Handle Stripe webhook events.
    
    This endpoint:
    1. Verifies the webhook signature for security
    2. Processes the event based on type
    3. Updates user subscriptions accordingly
    4. Returns appropriate HTTP status codes
    """
    try:
        # Get the raw payload
        payload = await request.body()
        
        if not stripe_signature:
            logger.error("Missing Stripe signature header")
            raise HTTPException(status_code=400, detail="Missing stripe-signature header")
        
        # Verify webhook signature
        if not webhook_handler.verify_webhook_signature(payload, stripe_signature):
            logger.error("Invalid webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Parse the event
        try:
            event_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        # Process the webhook event
        result = webhook_handler.handle_webhook_event(event_data)
        
        # Log the result
        event_type = event_data.get('type', 'unknown')
        event_id = event_data.get('id', 'unknown')
        logger.info(f"Processed webhook {event_id} ({event_type}): {result}")
        
        # Return appropriate status based on result
        if result.get('status') == 'error':
            return JSONResponse(
                status_code=500,
                content={"error": result.get('message', 'Processing failed')}
            )
        elif result.get('status') == 'ignored':
            return JSONResponse(
                status_code=200,
                content={"message": "Event ignored", "details": result.get('message')}
            )
        else:
            return JSONResponse(
                status_code=200,
                content={"message": "Event processed successfully", "details": result}
            )
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error in webhook handler: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = asyncio.get_event_loop().time()
    
    # Log request
    logger.info(f"Incoming request: {request.method} {request.url}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    process_time = asyncio.get_event_loop().time() - start_time
    logger.info(f"Request completed: {response.status_code} in {process_time:.3f}s")
    
    return response

if __name__ == "__main__":
    import uvicorn
    
    # For development only
    uvicorn.run(
        "app.webhook_server:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
