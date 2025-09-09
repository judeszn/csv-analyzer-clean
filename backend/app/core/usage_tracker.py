from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import json
import os
from dataclasses import dataclass, asdict
from enum import Enum

from app.utils.logging_config import get_logger, log_performance

logger = get_logger('csv_analyzer')

class SubscriptionTier(Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    ADMIN = "admin"

@dataclass
class UsageStats:
    """User usage statistics."""
    daily_analyses: int = 0
    total_analyses: int = 0
    last_analysis_date: Optional[str] = None
    subscription_tier: str = SubscriptionTier.FREE.value
    subscription_expires: Optional[str] = None
    created_at: str = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    subscription_status: str = "active"
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

@dataclass
class UsageLimits:
    """Usage limits for different tiers."""
    daily_analyses: int
    monthly_analyses: int
    max_file_size_mb: int
    advanced_features: bool
    priority_support: bool

class UsageTracker:
    """
    Professional usage tracking for CSV Analyzer Pro freemium model.
    
    Features:
    - Daily analysis limits for free tier
    - Subscription tier management
    - Usage analytics and reporting
    - Rate limiting enforcement
    - Upgrade prompts and conversion tracking
    """
    
    TIER_LIMITS = {
        SubscriptionTier.FREE: UsageLimits(
            daily_analyses=1,
            monthly_analyses=30,
            max_file_size_mb=10,
            advanced_features=False,
            priority_support=False
        ),
        SubscriptionTier.PRO: UsageLimits(
            daily_analyses=-1,  # Unlimited
            monthly_analyses=-1,  # Unlimited
            max_file_size_mb=100,
            advanced_features=True,
            priority_support=True
        ),
        SubscriptionTier.ENTERPRISE: UsageLimits(
            daily_analyses=-1,  # Unlimited
            monthly_analyses=-1,  # Unlimited
            max_file_size_mb=500,
            advanced_features=True,
            priority_support=True
        ),
        SubscriptionTier.ADMIN: UsageLimits(
            daily_analyses=-1,  # Unlimited
            monthly_analyses=-1,  # Unlimited
            max_file_size_mb=1000,  # 1GB limit for admin
            advanced_features=True,
            priority_support=True
        )
    }
    
    def __init__(self, storage_path: str = "user_data"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        logger.info(f"Usage tracker initialized with storage: {storage_path}")
    
    def _get_user_file_path(self, user_id: str) -> str:
        """Get the file path for user usage data."""
        return os.path.join(self.storage_path, f"user_{user_id}_usage.json")
    
    def _load_user_stats(self, user_id: str) -> UsageStats:
        """Load user usage statistics."""
        file_path = self._get_user_file_path(user_id)
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                return UsageStats(**data)
            except Exception as e:
                logger.error(f"Error loading user stats for {user_id}: {e}")
        
        # Return new user stats
        return UsageStats()
    
    def _save_user_stats(self, user_id: str, stats: UsageStats) -> bool:
        """Save user usage statistics."""
        try:
            file_path = self._get_user_file_path(user_id)
            with open(file_path, 'w') as f:
                json.dump(asdict(stats), f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving user stats for {user_id}: {e}")
            return False
    
    @log_performance
    def can_perform_analysis(self, user_id: str) -> Tuple[bool, str, Dict]:
        """
        Check if user can perform another analysis.
        
        Returns:
            (can_perform, reason, usage_info)
        """
        stats = self._load_user_stats(user_id)
        today = datetime.now().date().isoformat()
        
        # Reset daily count if new day
        if stats.last_analysis_date != today:
            stats.daily_analyses = 0
        
        # Get user's tier limits
        tier = SubscriptionTier(stats.subscription_tier)
        limits = self.TIER_LIMITS[tier]
        
        # Check subscription expiry for paid tiers
        if tier != SubscriptionTier.FREE and stats.subscription_expires:
            expiry_date = datetime.fromisoformat(stats.subscription_expires).date()
            if datetime.now().date() > expiry_date:
                # Downgrade to free tier
                stats.subscription_tier = SubscriptionTier.FREE.value
                stats.subscription_expires = None
                self._save_user_stats(user_id, stats)
                tier = SubscriptionTier.FREE
                limits = self.TIER_LIMITS[tier]
                logger.info(f"User {user_id} subscription expired, downgraded to free tier")
        
        # Check daily limits
        if limits.daily_analyses > 0 and stats.daily_analyses >= limits.daily_analyses:
            usage_info = {
                'current_tier': tier.value,
                'daily_analyses_used': stats.daily_analyses,
                'daily_analyses_limit': limits.daily_analyses,
                'analyses_remaining': 0
            }
            return False, f"Daily limit reached ({limits.daily_analyses} analyses per day)", usage_info
        
        # Calculate remaining analyses
        remaining = limits.daily_analyses - stats.daily_analyses if limits.daily_analyses > 0 else -1
        
        usage_info = {
            'current_tier': tier.value,
            'daily_analyses_used': stats.daily_analyses,
            'daily_analyses_limit': limits.daily_analyses,
            'analyses_remaining': remaining,
            'total_analyses': stats.total_analyses
        }
        
        return True, "Analysis allowed", usage_info
    
    @log_performance
    def record_analysis(self, user_id: str, analysis_type: str = "general") -> Dict:
        """Record a completed analysis."""
        stats = self._load_user_stats(user_id)
        today = datetime.now().date().isoformat()
        
        # Reset daily count if new day
        if stats.last_analysis_date != today:
            stats.daily_analyses = 0
        
        # Increment counters
        stats.daily_analyses += 1
        stats.total_analyses += 1
        stats.last_analysis_date = today
        
        # Save updated stats
        self._save_user_stats(user_id, stats)
        
        logger.info(f"Analysis recorded for user {user_id}: {analysis_type}")
        
        # Return updated usage info
        tier = SubscriptionTier(stats.subscription_tier)
        limits = self.TIER_LIMITS[tier]
        remaining = limits.daily_analyses - stats.daily_analyses if limits.daily_analyses > 0 else -1
        
        return {
            'daily_analyses_used': stats.daily_analyses,
            'total_analyses': stats.total_analyses,
            'analyses_remaining': remaining,
            'current_tier': tier.value
        }
    
    def upgrade_user_subscription(self, user_id: str, new_tier: SubscriptionTier, 
                                expires_at: Optional[datetime] = None) -> bool:
        """Upgrade user to a paid tier."""
        try:
            stats = self._load_user_stats(user_id)
            stats.subscription_tier = new_tier.value
            
            if expires_at:
                stats.subscription_expires = expires_at.isoformat()
            elif new_tier != SubscriptionTier.FREE:
                # Default to 30 days for paid subscriptions
                stats.subscription_expires = (datetime.now() + timedelta(days=30)).isoformat()
            
            self._save_user_stats(user_id, stats)
            logger.info(f"User {user_id} upgraded to {new_tier.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error upgrading user {user_id}: {e}")
            return False
    
    def get_user_tier_info(self, user_id: str) -> Dict:
        """Get comprehensive user tier and usage information."""
        stats = self._load_user_stats(user_id)
        tier = SubscriptionTier(stats.subscription_tier)
        limits = self.TIER_LIMITS[tier]
        
        today = datetime.now().date().isoformat()
        if stats.last_analysis_date != today:
            daily_used = 0
        else:
            daily_used = stats.daily_analyses
        
        remaining = limits.daily_analyses - daily_used if limits.daily_analyses > 0 else -1
        
        tier_info = {
            'current_tier': tier.value,
            'subscription_expires': stats.subscription_expires,
            'daily_analyses_used': daily_used,
            'daily_analyses_limit': limits.daily_analyses,
            'analyses_remaining': remaining,
            'total_analyses': stats.total_analyses,
            'max_file_size_mb': limits.max_file_size_mb,
            'advanced_features': limits.advanced_features,
            'priority_support': limits.priority_support,
            'created_at': stats.created_at
        }
        
        return tier_info
    
    def should_show_upgrade_prompt(self, user_id: str) -> Tuple[bool, str]:
        """Determine if user should see upgrade prompt."""
        stats = self._load_user_stats(user_id)
        
        if stats.subscription_tier != SubscriptionTier.FREE.value:
            return False, "User is already on paid tier"
        
        # Show upgrade prompt if user has used 2+ analyses today
        if stats.daily_analyses >= 2:
            return True, "Approaching daily limit"
        
        # Show upgrade prompt if user has made 20+ total analyses
        if stats.total_analyses >= 20:
            return True, "Heavy usage detected"
        
        return False, "No upgrade prompt needed"
    
    # Webhook-related methods for Stripe integration
    
    def upgrade_user_subscription(self, user_id: str, tier: SubscriptionTier, 
                                 stripe_customer_id: str = None, 
                                 stripe_subscription_id: str = None) -> bool:
        """Upgrade user subscription tier (called from webhooks)."""
        try:
            stats = self._load_user_stats(user_id)
            stats.subscription_tier = tier.value
            stats.stripe_customer_id = stripe_customer_id
            stats.stripe_subscription_id = stripe_subscription_id
            stats.subscription_status = "active"
            
            # Set expiry date for paid tiers (monthly subscription)
            if tier != SubscriptionTier.FREE:
                expiry_date = datetime.now() + timedelta(days=30)
                stats.subscription_expires = expiry_date.isoformat()
            
            success = self._save_user_stats(user_id, stats)
            if success:
                logger.info(f"Upgraded user {user_id} to {tier.value}")
            return success
            
        except Exception as e:
            logger.error(f"Error upgrading user {user_id}: {e}")
            return False
    
    def downgrade_user_subscription(self, user_id: str, reason: str = "manual") -> bool:
        """Downgrade user to free tier."""
        try:
            stats = self._load_user_stats(user_id)
            stats.subscription_tier = SubscriptionTier.FREE.value
            stats.subscription_expires = None
            stats.subscription_status = "cancelled"
            
            success = self._save_user_stats(user_id, stats)
            if success:
                logger.info(f"Downgraded user {user_id} to free tier (reason: {reason})")
            return success
            
        except Exception as e:
            logger.error(f"Error downgrading user {user_id}: {e}")
            return False
    
    def get_user_by_customer_id(self, customer_id: str) -> Optional[str]:
        """Find user ID by Stripe customer ID."""
        try:
            for filename in os.listdir(self.data_dir):
                if filename.endswith('.json'):
                    user_id = filename[:-5]  # Remove .json extension
                    stats = self._load_user_stats(user_id)
                    if stats.stripe_customer_id == customer_id:
                        return user_id
            return None
        except Exception as e:
            logger.error(f"Error finding user by customer ID {customer_id}: {e}")
            return None
    
    def update_user_subscription_status(self, user_id: str, tier: SubscriptionTier,
                                       stripe_subscription_id: str, status: str) -> bool:
        """Update user subscription status from webhooks."""
        try:
            stats = self._load_user_stats(user_id)
            stats.subscription_tier = tier.value
            stats.stripe_subscription_id = stripe_subscription_id
            stats.subscription_status = status
            
            # Update expiry based on status
            if status == 'active' and tier != SubscriptionTier.FREE:
                expiry_date = datetime.now() + timedelta(days=30)
                stats.subscription_expires = expiry_date.isoformat()
            elif status in ['cancelled', 'unpaid', 'past_due']:
                stats.subscription_tier = SubscriptionTier.FREE.value
                stats.subscription_expires = None
            
            success = self._save_user_stats(user_id, stats)
            if success:
                logger.info(f"Updated user {user_id} subscription status: {status}")
            return success
            
        except Exception as e:
            logger.error(f"Error updating user {user_id} subscription status: {e}")
            return False
    
    def confirm_user_subscription(self, user_id: str, stripe_subscription_id: str) -> bool:
        """Confirm user subscription is active (for successful payments)."""
        try:
            stats = self._load_user_stats(user_id)
            if stats.stripe_subscription_id == stripe_subscription_id:
                stats.subscription_status = "active"
                # Extend subscription by 30 days
                if stats.subscription_tier != SubscriptionTier.FREE.value:
                    expiry_date = datetime.now() + timedelta(days=30)
                    stats.subscription_expires = expiry_date.isoformat()
                
                success = self._save_user_stats(user_id, stats)
                if success:
                    logger.info(f"Confirmed subscription for user {user_id}")
                return success
            else:
                logger.warning(f"Subscription ID mismatch for user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error confirming subscription for user {user_id}: {e}")
            return False

# Global usage tracker instance
usage_tracker = UsageTracker()