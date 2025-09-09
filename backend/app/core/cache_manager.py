import json
import hashlib
import pickle
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import os

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from ..utils.logging_config import get_logger, log_performance

logger = get_logger('csv_analyzer')

class CacheManager:
    """
    Professional cache manager for CSV Analyzer Pro.
    
    Features:
    - Redis backend for production
    - Local file cache as fallback
    - Automatic expiration
    - Query result caching
    - Analysis result caching
    - Performance monitoring
    """
    
    def __init__(self):
        self.redis_client = None
        self.use_redis = False
        
        # Try to connect to Redis
        if REDIS_AVAILABLE:
            try:
                redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
                self.redis_client = redis.from_url(redis_url)
                self.redis_client.ping()  # Test connection
                self.use_redis = True
                logger.info("Redis cache backend initialized successfully")
            except Exception as e:
                logger.warning(f"Redis connection failed, falling back to local cache: {e}")
        
        # Fallback to local file cache
        if not self.use_redis:
            self.cache_dir = "cache"
            os.makedirs(self.cache_dir, exist_ok=True)
            logger.info("Local file cache backend initialized")
    
    def _generate_key(self, query: str, file_hash: str = None) -> str:
        """Generate a unique cache key for a query."""
        key_data = f"{query}_{file_hash}" if file_hash else query
        return hashlib.md5(key_data.encode()).hexdigest()
    
    @log_performance
    def get(self, key: str) -> Optional[Any]:
        """Retrieve cached data."""
        try:
            if self.use_redis:
                cached_data = self.redis_client.get(key)
                if cached_data:
                    return pickle.loads(cached_data)
            else:
                cache_file = os.path.join(self.cache_dir, f"{key}.cache")
                if os.path.exists(cache_file):
                    with open(cache_file, 'rb') as f:
                        cache_entry = pickle.load(f)
                    
                    # Check expiration
                    if cache_entry['expires_at'] > datetime.now():
                        logger.debug(f"Cache hit for key: {key}")
                        return cache_entry['data']
                    else:
                        os.remove(cache_file)
                        logger.debug(f"Cache expired for key: {key}")
            
            logger.debug(f"Cache miss for key: {key}")
            return None
            
        except Exception as e:
            logger.error(f"Cache retrieval error for key {key}: {e}")
            return None
    
    @log_performance
    def set(self, key: str, data: Any, ttl_seconds: int = 3600) -> bool:
        """Store data in cache with TTL."""
        try:
            if self.use_redis:
                serialized_data = pickle.dumps(data)
                self.redis_client.setex(key, ttl_seconds, serialized_data)
                logger.debug(f"Cached data for key: {key} (TTL: {ttl_seconds}s)")
            else:
                cache_entry = {
                    'data': data,
                    'created_at': datetime.now(),
                    'expires_at': datetime.now() + timedelta(seconds=ttl_seconds)
                }
                
                cache_file = os.path.join(self.cache_dir, f"{key}.cache")
                with open(cache_file, 'wb') as f:
                    pickle.dump(cache_entry, f)
                
                logger.debug(f"Cached data for key: {key} (TTL: {ttl_seconds}s)")
            
            return True
            
        except Exception as e:
            logger.error(f"Cache storage error for key {key}: {e}")
            return False
    
    def cache_query_result(self, query: str, file_hash: str, result: Any, ttl_seconds: int = 1800) -> str:
        """Cache SQL query results."""
        key = f"query_{self._generate_key(query, file_hash)}"
        self.set(key, result, ttl_seconds)
        return key
    
    def get_cached_query_result(self, query: str, file_hash: str) -> Optional[Any]:
        """Retrieve cached SQL query results."""
        key = f"query_{self._generate_key(query, file_hash)}"
        return self.get(key)
    
    def cache_analysis_result(self, analysis_type: str, parameters: Dict, result: Any, ttl_seconds: int = 3600) -> str:
        """Cache complex analysis results."""
        param_str = json.dumps(parameters, sort_keys=True)
        key = f"analysis_{analysis_type}_{self._generate_key(param_str)}"
        self.set(key, result, ttl_seconds)
        return key
    
    def get_cached_analysis_result(self, analysis_type: str, parameters: Dict) -> Optional[Any]:
        """Retrieve cached analysis results."""
        param_str = json.dumps(parameters, sort_keys=True)
        key = f"analysis_{analysis_type}_{self._generate_key(param_str)}"
        return self.get(key)
    
    def clear_cache(self) -> bool:
        """Clear all cached data."""
        try:
            if self.use_redis:
                self.redis_client.flushall()
                logger.info("Redis cache cleared successfully")
            else:
                import shutil
                if os.path.exists(self.cache_dir):
                    shutil.rmtree(self.cache_dir)
                    os.makedirs(self.cache_dir, exist_ok=True)
                logger.info("Local cache cleared successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            if self.use_redis:
                info = self.redis_client.info()
                return {
                    'backend': 'redis',
                    'connected_clients': info.get('connected_clients', 0),
                    'used_memory': info.get('used_memory_human', 'Unknown'),
                    'keyspace_hits': info.get('keyspace_hits', 0),
                    'keyspace_misses': info.get('keyspace_misses', 0)
                }
            else:
                cache_files = [f for f in os.listdir(self.cache_dir) if f.endswith('.cache')]
                total_size = sum(os.path.getsize(os.path.join(self.cache_dir, f)) for f in cache_files)
                return {
                    'backend': 'local_file',
                    'cache_files': len(cache_files),
                    'total_size_bytes': total_size,
                    'total_size_mb': round(total_size / (1024 * 1024), 2)
                }
                
        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {'backend': 'unknown', 'error': str(e)}

# Global cache instance
cache_manager = CacheManager()