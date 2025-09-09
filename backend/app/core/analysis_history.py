import json
import os
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from app.utils.logging_config import get_logger, log_performance

logger = get_logger('csv_analyzer')

class ExportFormat(Enum):
    PDF = "pdf"
    EXCEL = "xlsx"
    CSV = "csv"
    JSON = "json"

@dataclass
class AnalysisRecord:
    """Represents a single analysis record."""
    id: str
    user_id: str
    timestamp: str
    filename: str
    question: str
    response: str
    file_hash: str
    execution_time: float
    subscription_tier: str
    created_at: str = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

class AnalysisHistoryManager:
    """
    Professional analysis history management for CSV Analyzer Pro.
    
    Features:
    - Store user analyses with metadata
    - Retention policies based on subscription tier
    - Export functionality (PDF, Excel, CSV)
    - Search and filter capabilities
    - Automatic cleanup of expired records
    """
    
    RETENTION_POLICIES = {
        'free': 7,      # 7 days for free users
        'pro': 30,      # 30 days for pro users
        'enterprise': 90 # 90 days for enterprise users
    }
    
    def __init__(self, storage_path: str = "analysis_history"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        logger.info(f"Analysis history manager initialized with storage: {storage_path}")
    
    def _get_user_history_file(self, user_id: str) -> str:
        """Get the file path for user's analysis history."""
        return os.path.join(self.storage_path, f"user_{user_id}_history.json")
    
    def _generate_analysis_id(self, user_id: str, question: str, timestamp: str) -> str:
        """Generate a unique analysis ID."""
        content = f"{user_id}_{question}_{timestamp}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _calculate_file_hash(self, file_content: Any) -> str:
        """Calculate hash of uploaded file for deduplication."""
        if isinstance(file_content, bytes):
            return hashlib.sha256(file_content).hexdigest()[:16]
        elif isinstance(file_content, str):
            return hashlib.sha256(file_content.encode('utf-8')).hexdigest()[:16]
        
        # Fallback for other types, like dictionaries from file_processor
        try:
            # Attempt to serialize to JSON string then hash
            serialized_content = json.dumps(file_content, sort_keys=True, default=str)
            return hashlib.sha256(serialized_content.encode('utf-8')).hexdigest()[:16]
        except Exception as e:
            logger.warning(f"Could not hash file content of type {type(file_content)}: {e}")
            # Return a default hash if serialization fails
            return hashlib.sha256(b"unhashable_content").hexdigest()[:16]

    @log_performance
    def save_analysis(self, user_id: str, filename: str, question: str, 
                     response: str, file_content: Any, execution_time: float,
                     subscription_tier: str = "free") -> str:
        """
        Save an analysis record.
        
        Returns:
            str: Analysis ID
        """
        try:
            timestamp = datetime.now().isoformat()
            file_hash = self._calculate_file_hash(file_content)
            analysis_id = self._generate_analysis_id(user_id, question, timestamp)
            
            # Create analysis record
            record = AnalysisRecord(
                id=analysis_id,
                user_id=user_id,
                timestamp=timestamp,
                filename=filename,
                question=question,
                response=response,
                file_hash=file_hash,
                execution_time=execution_time,
                subscription_tier=subscription_tier
            )
            
            # Load existing history
            history = self._load_user_history(user_id)
            
            # Add new record
            history.append(asdict(record))
            
            # Save updated history
            self._save_user_history(user_id, history)
            
            logger.info(f"Analysis saved for user {user_id}: {analysis_id}")
            return analysis_id
            
        except Exception as e:
            logger.error(f"Error saving analysis for user {user_id}: {e}")
            raise
    
    def _load_user_history(self, user_id: str) -> List[Dict]:
        """Load user's analysis history."""
        file_path = self._get_user_history_file(user_id)
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading history for user {user_id}: {e}")
                return []
        
        return []
    
    def _save_user_history(self, user_id: str, history: List[Dict]) -> bool:
        """Save user's analysis history."""
        try:
            file_path = self._get_user_history_file(user_id)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving history for user {user_id}: {e}")
            return False
    
    @log_performance
    def get_user_analyses(self, user_id: str, limit: int = 50) -> List[Dict]:
        """
        Get user's recent analyses.
        
        Args:
            user_id: User identifier
            limit: Maximum number of analyses to return
            
        Returns:
            List of analysis records sorted by timestamp (newest first)
        """
        try:
            history = self._load_user_history(user_id)
            
            # Sort by timestamp (newest first)
            history.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # Apply limit
            return history[:limit]
            
        except Exception as e:
            logger.error(f"Error getting analyses for user {user_id}: {e}")
            return []
    
    def get_analysis_by_id(self, user_id: str, analysis_id: str) -> Optional[Dict]:
        """Get a specific analysis by ID."""
        try:
            history = self._load_user_history(user_id)
            
            for record in history:
                if record['id'] == analysis_id:
                    return record
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting analysis {analysis_id} for user {user_id}: {e}")
            return None
    
    @log_performance
    def cleanup_expired_analyses(self, user_id: str, subscription_tier: str = "free") -> int:
        """
        Clean up expired analyses based on retention policy.
        
        Returns:
            int: Number of analyses removed
        """
        try:
            retention_days = self.RETENTION_POLICIES.get(subscription_tier, 7)
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            history = self._load_user_history(user_id)
            original_count = len(history)
            
            # Filter out expired analyses
            valid_history = []
            for record in history:
                record_date = datetime.fromisoformat(record['timestamp'])
                if record_date >= cutoff_date:
                    valid_history.append(record)
            
            # Save cleaned history
            self._save_user_history(user_id, valid_history)
            
            removed_count = original_count - len(valid_history)
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} expired analyses for user {user_id}")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error cleaning up analyses for user {user_id}: {e}")
            return 0
    
    def get_analysis_stats(self, user_id: str) -> Dict[str, Any]:
        """Get analysis statistics for a user."""
        try:
            history = self._load_user_history(user_id)
            
            if not history:
                return {
                    'total_analyses': 0,
                    'avg_execution_time': 0,
                    'most_recent': None,
                    'unique_files': 0
                }
            
            # Calculate statistics
            total_analyses = len(history)
            avg_execution_time = sum(r.get('execution_time', 0) for r in history) / total_analyses
            most_recent = max(history, key=lambda x: x['timestamp'])
            unique_files = len(set(r['file_hash'] for r in history))
            
            return {
                'total_analyses': total_analyses,
                'avg_execution_time': round(avg_execution_time, 2),
                'most_recent': most_recent['timestamp'],
                'unique_files': unique_files
            }
            
        except Exception as e:
            logger.error(f"Error getting stats for user {user_id}: {e}")
            return {'total_analyses': 0, 'avg_execution_time': 0, 'most_recent': None, 'unique_files': 0}

# Global analysis history manager instance
analysis_history = AnalysisHistoryManager()
