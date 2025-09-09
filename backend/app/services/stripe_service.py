import stripe
from app.config.settings import settings
from app.utils.logging_config import get_logger

logger = get_logger('csv_analyzer')

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_checkout_session(user_id: str, user_email: str):
    """
    Creates a Stripe Checkout session for a user to upgrade to the Pro plan.
    """
    try:
        # Check if we have a valid price ID
        if not settings.STRIPE_PRO_PRICE_ID or settings.STRIPE_PRO_PRICE_ID == "price_test_placeholder":
            logger.warning("Stripe Pro Price ID not configured properly")
            return None
            
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price': settings.STRIPE_PRO_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url='http://localhost:8504?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='http://localhost:8504',
            customer_email=user_email,
            metadata={
                'user_id': user_id
            }
        )
        logger.info(f"Created Stripe checkout session for user {user_id}")
        return checkout_session.url
    except Exception as e:
        logger.error(f"Error creating Stripe checkout session: {e}")
        return None
