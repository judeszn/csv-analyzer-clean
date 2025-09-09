import stripe
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from app.config.settings import settings
from app.utils.logging_config import get_logger
from app.core.usage_tracker import usage_tracker, SubscriptionTier

logger = get_logger('csv_analyzer')

class StripeWebhookHandler:
    """
    Handles Stripe webhook events for subscription management.
    
    Key Events Handled:
    - checkout.session.completed: User successfully upgraded
    - customer.subscription.updated: Subscription changes
    - customer.subscription.deleted: Subscription cancelled
    - invoice.payment_succeeded: Successful recurring payment
    - invoice.payment_failed: Failed payment
    """
    
    def __init__(self):
        self.webhook_secret = settings.WEBHOOK_SECRET
        logger.info("Webhook handler initialized")
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify that the webhook actually came from Stripe.
        This is crucial for security!
        """
        try:
            stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
            return True
        except ValueError as e:
            logger.error(f"Invalid payload in webhook: {e}")
            return False
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid signature in webhook: {e}")
            return False
    
    def handle_webhook_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process different types of Stripe webhook events.
        """
        event_type = event_data.get('type')
        event_object = event_data.get('data', {}).get('object', {})
        
        logger.info(f"Processing webhook event: {event_type}")
        
        try:
            if event_type == 'checkout.session.completed':
                return self._handle_checkout_completed(event_object)
            
            elif event_type == 'customer.subscription.updated':
                return self._handle_subscription_updated(event_object)
            
            elif event_type == 'customer.subscription.deleted':
                return self._handle_subscription_cancelled(event_object)
            
            elif event_type == 'invoice.payment_succeeded':
                return self._handle_payment_succeeded(event_object)
            
            elif event_type == 'invoice.payment_failed':
                return self._handle_payment_failed(event_object)
            
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
                return {"status": "ignored", "message": f"Event type {event_type} not handled"}
        
        except Exception as e:
            logger.error(f"Error processing webhook event {event_type}: {e}")
            return {"status": "error", "message": str(e)}
    
    def _handle_checkout_completed(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Handle successful checkout completion."""
        user_id = session.get('metadata', {}).get('user_id')
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        
        if not user_id:
            logger.error("No user_id in checkout session metadata")
            return {"status": "error", "message": "Missing user_id"}
        
        # Upgrade user to Pro tier
        success = usage_tracker.upgrade_user_subscription(
            user_id=user_id,
            tier=SubscriptionTier.PRO,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id
        )
        
        if success:
            logger.info(f"Successfully upgraded user {user_id} to Pro")
            return {"status": "success", "message": "User upgraded to Pro"}
        else:
            logger.error(f"Failed to upgrade user {user_id}")
            return {"status": "error", "message": "Failed to upgrade user"}
    
    def _handle_subscription_updated(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription updates (plan changes, etc.)."""
        customer_id = subscription.get('customer')
        subscription_id = subscription.get('id')
        status = subscription.get('status')
        
        # Find user by customer ID
        user_id = usage_tracker.get_user_by_customer_id(customer_id)
        if not user_id:
            logger.warning(f"No user found for customer {customer_id}")
            return {"status": "ignored", "message": "User not found"}
        
        # Update subscription status
        if status == 'active':
            tier = SubscriptionTier.PRO
        elif status in ['past_due', 'unpaid']:
            tier = SubscriptionTier.FREE  # Downgrade for non-payment
        else:
            tier = SubscriptionTier.FREE
        
        success = usage_tracker.update_user_subscription_status(
            user_id=user_id,
            tier=tier,
            stripe_subscription_id=subscription_id,
            status=status
        )
        
        logger.info(f"Updated subscription for user {user_id}: {status}")
        return {"status": "success", "message": f"Subscription updated: {status}"}
    
    def _handle_subscription_cancelled(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription cancellation."""
        customer_id = subscription.get('customer')
        subscription_id = subscription.get('id')
        
        # Find user by customer ID
        user_id = usage_tracker.get_user_by_customer_id(customer_id)
        if not user_id:
            logger.warning(f"No user found for customer {customer_id}")
            return {"status": "ignored", "message": "User not found"}
        
        # Downgrade to free tier
        success = usage_tracker.downgrade_user_subscription(
            user_id=user_id,
            reason="subscription_cancelled"
        )
        
        logger.info(f"Downgraded user {user_id} due to subscription cancellation")
        return {"status": "success", "message": "User downgraded to free tier"}
    
    def _handle_payment_succeeded(self, invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Handle successful recurring payment."""
        customer_id = invoice.get('customer')
        subscription_id = invoice.get('subscription')
        
        # Find user by customer ID
        user_id = usage_tracker.get_user_by_customer_id(customer_id)
        if not user_id:
            logger.warning(f"No user found for customer {customer_id}")
            return {"status": "ignored", "message": "User not found"}
        
        # Ensure user remains on Pro tier
        success = usage_tracker.confirm_user_subscription(
            user_id=user_id,
            stripe_subscription_id=subscription_id
        )
        
        logger.info(f"Payment succeeded for user {user_id}")
        return {"status": "success", "message": "Payment processed successfully"}
    
    def _handle_payment_failed(self, invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Handle failed payment."""
        customer_id = invoice.get('customer')
        subscription_id = invoice.get('subscription')
        
        # Find user by customer ID
        user_id = usage_tracker.get_user_by_customer_id(customer_id)
        if not user_id:
            logger.warning(f"No user found for customer {customer_id}")
            return {"status": "ignored", "message": "User not found"}
        
        # Optionally downgrade after multiple failed payments
        # You might want to implement a grace period
        logger.warning(f"Payment failed for user {user_id}")
        
        # For now, just log it - you can implement grace period logic
        return {"status": "warning", "message": "Payment failed - monitoring"}

# Global webhook handler instance
webhook_handler = StripeWebhookHandler()
