"""
Database-backed Usage Tracker for CSV Analyzer Pro.

This module replaces the file-based usage tracker with a robust, scalable
solution using the Supabase PostgreSQL database. It manages user profiles,
subscription tiers, and usage statistics.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from enum import Enum

from app.utils.logging_config import get_logger, log_performance
from app.auth.supabase_client import supabase_client

logger = get_logger('csv_analyzer')

class SubscriptionTier(Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    ADMIN = "admin"

class UsageLimits:
    """Static class for usage limits per tier."""
    TIER_LIMITS = {
        SubscriptionTier.FREE: {
            "daily_analyses": 1,
            "max_file_size_mb": 10,
        },
        SubscriptionTier.PRO: {
            "daily_analyses": -1,  # Unlimited
            "max_file_size_mb": 100,
        },
        SubscriptionTier.ENTERPRISE: {
            "daily_analyses": -1,  # Unlimited
            "max_file_size_mb": 500,
        },
        SubscriptionTier.ADMIN: {
            "daily_analyses": -1,  # Unlimited
            "max_file_size_mb": 1000,  # 1GB limit for admin
        }
    }

class DBUsageTracker:
    """
    Manages user usage and subscriptions using a Supabase database backend.
    """
    
    def _is_test_mode(self) -> bool:
        """Check if we're running in test mode (no Supabase connection or fallback mode)"""
        import os
        return supabase_client is None or os.environ.get('FALLBACK_TO_TEST_USER', 'false').lower() == 'true'
    
    def _get_test_profile(self, user_id: str) -> Dict:
        """Return a test profile for test mode"""
        return {
            'id': user_id,
            'subscription_tier': SubscriptionTier.FREE.value,
            'subscription_status': 'active',
            'daily_analyses': 0,  # Changed from daily_analysis_count to match expected key
            'last_analysis_date': datetime.now().date().isoformat(),  # Changed from daily_analysis_date
            'total_analyses': 0,  # Added this key
            'stripe_customer_id': None,
            'stripe_subscription_id': None
        }

    @log_performance
    def _get_or_create_user_profile(self, user_id: str) -> Optional[Dict]:
        """
        Retrieves a user's profile from the database, creating it if it doesn't exist.
        The user profile table is expected to be created via Supabase Auth triggers.
        """
        # Check test mode first - before any database operations
        if self._is_test_mode() or user_id == 'fallback-test-user':
            logger.info("Running in test mode or using fallback user - returning mock profile")
            return self._get_test_profile(user_id)
            
        try:
            # First, try to select the profile
            response = supabase_client.table("profiles").select("*").eq("id", user_id).execute()
            
            if response.data:
                return response.data[0]

            # If no profile, it might be a new user from Auth.
            # The profile is usually created by a trigger on the `auth.users` table.
            # We can insert a basic profile if it's missing.
            logger.info(f"No profile found for user_id {user_id}. Creating one.")
            insert_response = supabase_client.table("profiles").insert({
                "id": user_id,
                "subscription_tier": SubscriptionTier.FREE.value,
                "subscription_status": "active"
            }).execute()

            if insert_response.data:
                return insert_response.data[0]
            else:
                logger.error(f"Failed to create profile for user {user_id}: {insert_response.error}")
                return None

        except Exception as e:
            logger.error(f"Error getting or creating profile for user {user_id}: {e}")
            return None

    @log_performance
    def can_perform_analysis(self, user_id: str) -> Tuple[bool, str, Dict]:
        """Checks if a user can perform another analysis based on their subscription."""
        profile = self._get_or_create_user_profile(user_id)
        if not profile:
            return False, "Could not retrieve user profile.", {}

        tier = SubscriptionTier(profile.get("subscription_tier", "free"))
        limits = UsageLimits.TIER_LIMITS[tier]

        # Pro/Enterprise users have unlimited analyses
        if limits["daily_analyses"] < 0:
            return True, "Analysis allowed", self._get_usage_info(profile)

        # Check daily usage for free users
        last_analysis_str = profile.get("last_analysis_date")
        daily_analyses = profile.get("daily_analyses", 0)
        today_str = datetime.now().date().isoformat()

        # Reset daily count if it's a new day
        if last_analysis_str != today_str:
            daily_analyses = 0

        if daily_analyses >= limits["daily_analyses"]:
            reason = f"Daily limit of {limits['daily_analyses']} analysis reached for Free plan."
            return False, reason, self._get_usage_info(profile, daily_analyses)

        return True, "Analysis allowed", self._get_usage_info(profile, daily_analyses)

    @log_performance
    def record_analysis(self, user_id: str, analysis_type: str = "general") -> Dict:
        """Records a completed analysis and updates usage stats in the database."""
        if self._is_test_mode():
            logger.info("Running in test mode - skipping analysis recording")
            return self._get_test_profile(user_id)
            
        profile = self._get_or_create_user_profile(user_id)
        if not profile:
            logger.error(f"Cannot record analysis, user profile not found for {user_id}")
            return {}

        today_str = datetime.now().date().isoformat()
        daily_analyses = profile.get("daily_analyses", 0)

        # Reset daily count if it's a new day
        if profile.get("last_analysis_date") != today_str:
            daily_analyses = 0

        update_data = {
            "daily_analyses": daily_analyses + 1,
            "total_analyses": profile.get("total_analyses", 0) + 1,
            "last_analysis_date": today_str
        }

        try:
            response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
            if response.data:
                logger.info(f"Analysis recorded for user {user_id}: {analysis_type}")
                # Return updated info
                updated_profile = response.data[0]
                return self._get_usage_info(updated_profile)
            else:
                logger.error(f"Failed to record analysis for user {user_id}: {response.error}")
                return {}
        except Exception as e:
            logger.error(f"DB error recording analysis for user {user_id}: {e}")
            return {}

    def _get_usage_info(self, profile: Dict, current_daily_count: Optional[int] = None) -> Dict:
        """Helper to construct the usage info dictionary."""
        tier = SubscriptionTier(profile.get("subscription_tier", "free"))
        limits = UsageLimits.TIER_LIMITS[tier]
        
        daily_used = current_daily_count if current_daily_count is not None else profile.get("daily_analyses", 0)
        
        # Reset daily count display if it's a new day
        if profile.get("last_analysis_date") != datetime.now().date().isoformat():
            daily_used = 0

        remaining = -1 # Unlimited
        if limits["daily_analyses"] > 0:
            remaining = limits["daily_analyses"] - daily_used

        return {
            'current_tier': tier.value,
            'daily_analyses_used': daily_used,
            'daily_analyses_limit': limits["daily_analyses"],
            'analyses_remaining': remaining,
            'total_analyses': profile.get("total_analyses", 0),
            'max_file_size_mb': limits["max_file_size_mb"],
        }

    def get_user_tier_info(self, user_id: str) -> Dict:
        """Gets comprehensive tier and usage info for a user."""
        profile = self._get_or_create_user_profile(user_id)
        if not profile:
            # Return default free tier info if profile fails
            return {
                'current_tier': 'free',
                'daily_analyses_used': 0,
                'daily_analyses_limit': UsageLimits.TIER_LIMITS[SubscriptionTier.FREE]['daily_analyses'],
                'analyses_remaining': UsageLimits.TIER_LIMITS[SubscriptionTier.FREE]['daily_analyses'],
                'total_analyses': 0,
                'max_file_size_mb': UsageLimits.TIER_LIMITS[SubscriptionTier.FREE]['max_file_size_mb'],
            }
        return self._get_usage_info(profile)

    @log_performance
    def should_show_upgrade_prompt(self, user_id: str) -> Tuple[bool, str]:
        """
        Determines if an upgrade prompt should be shown to the user.
        Returns (should_show, reason).
        """
        try:
            profile = self._get_or_create_user_profile(user_id)
            if not profile:
                return False, "Unable to check user profile"
            
            # Get current tier
            tier_str = profile.get("subscription_tier", "free")
            try:
                tier = SubscriptionTier(tier_str)
            except ValueError:
                tier = SubscriptionTier.FREE
            
            # Admin users never need upgrade prompts
            if tier == SubscriptionTier.ADMIN:
                return False, "Admin user"
            
            # Pro and Enterprise users don't need upgrade prompts if subscription is active
            if tier in [SubscriptionTier.PRO, SubscriptionTier.ENTERPRISE]:
                subscription_status = profile.get("subscription_status", "inactive")
                if subscription_status == "active":
                    return False, "Active subscription"
                else:
                    return True, "Subscription expired or inactive"
            
            # Free users: check if they've hit their daily limit
            if tier == SubscriptionTier.FREE:
                can_analyze, reason, _ = self.can_perform_analysis(user_id)
                if not can_analyze and "limit" in reason.lower():
                    return True, "Daily analysis limit reached"
                else:
                    return False, "Within daily limits"
            
            return False, "No upgrade needed"
            
        except Exception as e:
            logger.error(f"Error checking upgrade prompt for user {user_id}: {e}")
            return False, f"Error: {e}"

    # --- Webhook-related methods ---

    @log_performance
    def upgrade_user_subscription(self, user_id: str, tier: SubscriptionTier,
                                 stripe_customer_id: str, stripe_subscription_id: str) -> bool:
        """Upgrades a user's subscription tier in the database."""
        update_data = {
            "subscription_tier": tier.value,
            "subscription_status": "active",
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "subscription_expires_at": (datetime.now() + timedelta(days=31)).isoformat() # Grace period
        }
        try:
            response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
            if response.data:
                logger.info(f"Successfully upgraded user {user_id} to {tier.value}")
                return True
            logger.error(f"Failed to upgrade user {user_id} in DB: {response.error}")
            return False
        except Exception as e:
            logger.error(f"DB error upgrading user {user_id}: {e}")
            return False

    @log_performance
    def downgrade_user_subscription(self, user_id: str, reason: str) -> bool:
        """Downgrades a user to the free tier."""
        update_data = {
            "subscription_tier": SubscriptionTier.FREE.value,
            "subscription_status": "cancelled",
            "stripe_subscription_id": None,
            "subscription_expires_at": None
        }
        try:
            response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
            if response.data:
                logger.info(f"Downgraded user {user_id} to free (reason: {reason})")
                return True
            logger.error(f"Failed to downgrade user {user_id} in DB: {response.error}")
            return False
        except Exception as e:
            logger.error(f"DB error downgrading user {user_id}: {e}")
            return False

    @log_performance
    def get_user_by_customer_id(self, customer_id: str) -> Optional[str]:
        """Finds a user ID by their Stripe Customer ID."""
        try:
            response = supabase_client.table("profiles").select("id").eq("stripe_customer_id", customer_id).limit(1).execute()
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            logger.error(f"Error finding user by customer ID {customer_id}: {e}")
            return None

    @log_performance
    def update_user_subscription_status(self, user_id: str, tier: SubscriptionTier, status: str) -> bool:
        """Updates a user's subscription status, potentially downgrading them."""
        update_data = {"subscription_status": status}
        
        # If subscription is no longer active, downgrade to free
        if status != 'active':
            update_data["subscription_tier"] = SubscriptionTier.FREE.value
            update_data["subscription_expires_at"] = None
        else:
            # If it's active, ensure tier is correct and extend expiry
            update_data["subscription_tier"] = tier.value
            update_data["subscription_expires_at"] = (datetime.now() + timedelta(days=31)).isoformat()

        try:
            response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
            if response.data:
                logger.info(f"Updated subscription status for user {user_id} to '{status}'")
                return True
            logger.error(f"Failed to update status for user {user_id}: {response.error}")
            return False
        except Exception as e:
            logger.error(f"DB error updating status for user {user_id}: {e}")
            return False

    @log_performance
    def confirm_user_subscription(self, user_id: str) -> bool:
        """Confirms a subscription is active, typically after a successful recurring payment."""
        update_data = {
            "subscription_status": "active",
            "subscription_expires_at": (datetime.now() + timedelta(days=31)).isoformat()
        }
        try:
            response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
            if response.data:
                logger.info(f"Confirmed active subscription for user {user_id}")
                return True
            logger.error(f"Failed to confirm subscription for user {user_id}: {response.error}")
            return False
        except Exception as e:
            logger.error(f"DB error confirming subscription for user {user_id}: {e}")
            return False

    @log_performance
    def upgrade_to_admin(self, user_id: str) -> bool:
        """Upgrades a user to admin tier with unlimited access."""
        update_data = {
            "subscription_tier": SubscriptionTier.ADMIN.value,
            "subscription_status": "active",
            "subscription_expires_at": None  # Admin never expires
        }
        try:
            response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
            if response.data:
                logger.info(f"Successfully upgraded user {user_id} to ADMIN tier")
                return True
            logger.error(f"Failed to upgrade user {user_id} to admin: {response.error}")
            return False
        except Exception as e:
            logger.error(f"DB error upgrading user {user_id} to admin: {e}")
            return False

    @log_performance
    def get_user_by_email(self, email: str) -> Optional[str]:
        """Finds a user ID by their email address."""
        try:
            # First try to get from profiles table if email is stored there
            response = supabase_client.table("profiles").select("id, email").eq("email", email).execute()
            if response.data:
                return response.data[0]["id"]
            
            # If not found in profiles, query auth.users through RPC or direct query
            # Note: This might require additional permissions or a custom RPC function
            try:
                # Alternative: Use a stored procedure/function if available
                rpc_response = supabase_client.rpc('get_user_id_by_email', {'user_email': email}).execute()
                if rpc_response.data:
                    return rpc_response.data
            except:
                # If RPC doesn't exist, we'll need the user to sign up first
                pass
                
            logger.warning(f"No user found with email: {email}")
            return None
        except Exception as e:
            logger.error(f"Error finding user by email {email}: {e}")
            return None

    @log_performance
    def upgrade_user_by_email(self, email: str, tier: SubscriptionTier = SubscriptionTier.ADMIN) -> bool:
        """Upgrades a user to specified tier by email address."""
        try:
            # Try to find existing profile by email
            response = supabase_client.table("profiles").select("id").eq("email", email).execute()
            
            if response.data:
                user_id = response.data[0]["id"]
                logger.info(f"Found user {user_id} with email {email}")
            else:
                # If no profile found with email, try to create one
                # This assumes the user exists in auth.users
                logger.info(f"No profile found for {email}, will create one if user exists")
                
                # For now, we'll need the user to sign up first
                logger.error(f"User with email {email} not found. Please ensure user has signed up first.")
                return False
            
            # Upgrade the user
            if tier == SubscriptionTier.ADMIN:
                return self.upgrade_to_admin(user_id)
            else:
                return self.upgrade_user_subscription(user_id, tier, "admin_override", "admin_override")
                
        except Exception as e:
            logger.error(f"Error upgrading user by email {email}: {e}")
            return False

# Global instance for the application to use
db_usage_tracker = DBUsageTracker()