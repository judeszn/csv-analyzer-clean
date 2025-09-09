import logging
import logging.config
import os
from datetime import datetime
from pathlib import Path

def setup_logging(log_level: str = "INFO"):
    """
    Setup comprehensive logging configuration for CSV Analyzer Pro.
    
    Features:
    - File rotation with timestamp
    - Console and file handlers
    - Structured format for production monitoring
    - Performance and error tracking
    """
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Generate timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"csv_analyzer_{timestamp}.log"
    
    # Logging configuration
    LOGGING_CONFIG = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'detailed': {
                'format': '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'simple': {
                'format': '%(levelname)s | %(message)s'
            },
            'production': {
                'format': '{"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "function": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s"}',
                'datefmt': '%Y-%m-%dT%H:%M:%S'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'simple',
                'stream': 'ext://sys.stdout'
            },
            'file': {
                'class': 'logging.FileHandler',
                'level': 'DEBUG',
                'formatter': 'detailed',
                'filename': str(log_file),
                'mode': 'a'
            },
            'error_file': {
                'class': 'logging.FileHandler',
                'level': 'ERROR',
                'formatter': 'production',
                'filename': str(logs_dir / "errors.log"),
                'mode': 'a'
            }
        },
        'loggers': {
            'csv_analyzer': {
                'level': log_level,
                'handlers': ['console', 'file', 'error_file'],
                'propagate': False
            },
            'agents': {
                'level': log_level,
                'handlers': ['console', 'file'],
                'propagate': False
            },
            'auth': {
                'level': log_level,
                'handlers': ['console', 'file', 'error_file'],
                'propagate': False
            },
            'payments': {
                'level': log_level,
                'handlers': ['console', 'file', 'error_file'],
                'propagate': False
            }
        },
        'root': {
            'level': log_level,
            'handlers': ['console', 'file']
        }
    }
    
    logging.config.dictConfig(LOGGING_CONFIG)
    
    # Create specific loggers for different modules
    logger = logging.getLogger('csv_analyzer')
    logger.info(f"CSV Analyzer Pro logging initialized - Log file: {log_file}")
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module."""
    return logging.getLogger(name)

# Performance monitoring decorator
def log_performance(func):
    """Decorator to log function execution time."""
    import functools
    import time
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger('csv_analyzer')
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"Performance: {func.__name__} executed in {execution_time:.2f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Performance: {func.__name__} failed after {execution_time:.2f}s - Error: {e}")
            raise
    
    return wrapper