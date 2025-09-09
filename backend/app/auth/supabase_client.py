import os
from supabase import create_client, Client
from app.config.settings import settings
from app.utils.logging_config import get_logger

logger = get_logger('csv_analyzer')

class SupabaseManager:
    """
    Professional Supabase client manager for CSV Analyzer Pro.
    
    Handles Supabase initialization, authentication, and user management.
    """
    _client: Client = None

    @classmethod
    def get_client(cls) -> Client:
        """
        Get a Supabase client instance.
        
        Initializes the client if it doesn't exist.
        """
        if cls._client is None:
            try:
                url = settings.SUPABASE_URL
                key = settings.SUPABASE_KEY
                
                if not url or not key:
                    raise ValueError("Supabase URL and Key must be set in environment variables")
                
                # Check if we're in test mode
                if url == "https://test.supabase.co" or key == "test-key":
                    logger.warning("Running in test mode - Supabase client disabled")
                    cls._client = None
                    return cls._client
                
                cls._client = create_client(url, key)
                logger.info("Supabase client initialized successfully")
                
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase client (test mode): {e}")
                cls._client = None
        
        return cls._client

# Global Supabase client instance (can be None in test mode)
try:
    supabase_client = SupabaseManager.get_client()
except Exception:
    supabase_client = None
