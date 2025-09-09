import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
import hashlib
import json
from io import StringIO
from datetime import datetime

from app.core.cache_manager import cache_manager
from app.utils.logging_config import get_logger, log_performance

logger = get_logger('csv_analyzer')

class DataProcessor:
    """
    Advanced data processing capabilities for CSV Analyzer Pro.
    
    Features:
    - Intelligent data profiling and quality assessment
    - Statistical analysis and correlation detection
    - Outlier detection and anomaly identification
    - Data cleaning and preprocessing recommendations
    - Performance optimization with caching
    """
    
    def __init__(self):
        self.cache_enabled = True
        logger.info("Data processor initialized with caching support")
    
    def _generate_cache_key(self, data_hash: str, operation: str, params: Dict = None) -> str:
        """Generate a unique cache key for data operations."""
        key_parts = [data_hash, operation]
        if params:
            key_parts.append(json.dumps(params, sort_keys=True))
        return hashlib.md5("_".join(key_parts).encode()).hexdigest()
    
    def _get_data_hash(self, df: pd.DataFrame) -> str:
        """Generate a hash for the dataframe to use in caching."""
        # Use shape, column names, and first few rows for hash
        hash_data = {
            'shape': df.shape,
            'columns': list(df.columns),
            'dtypes': df.dtypes.to_dict(),
            'sample': df.head(3).to_dict() if len(df) > 0 else {}
        }
        return hashlib.md5(json.dumps(hash_data, default=str, sort_keys=True).encode()).hexdigest()
    
    @log_performance
    def analyze_data_quality(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Comprehensive data quality assessment.
        
        Returns detailed quality metrics including:
        - Missing value analysis
        - Data type recommendations
        - Duplicate detection
        - Statistical summaries
        """
        data_hash = self._get_data_hash(df)
        cache_key = self._generate_cache_key(data_hash, "data_quality")
        
        # Check cache first
        if self.cache_enabled:
            cached_result = cache_manager.get(cache_key)
            if cached_result:
                logger.info("Data quality analysis retrieved from cache")
                return cached_result
        
        logger.info(f"Performing data quality analysis on dataset: {df.shape}")
        
        try:
            quality_report = {
                'dataset_info': {
                    'rows': len(df),
                    'columns': len(df.columns),
                    'total_cells': len(df) * len(df.columns),
                    'memory_usage_mb': df.memory_usage(deep=True).sum() / 1024 / 1024
                },
                'missing_data': self._analyze_missing_data(df),
                'data_types': self._analyze_data_types(df),
                'duplicates': self._analyze_duplicates(df),
                'statistics': self._generate_statistics(df),
                'recommendations': self._generate_recommendations(df)
            }
            
            # Cache the result
            if self.cache_enabled:
                cache_manager.set(cache_key, quality_report, expire_time=3600)  # 1 hour
            
            logger.info("Data quality analysis completed successfully")
            return quality_report
            
        except Exception as e:
            logger.error(f"Error in data quality analysis: {e}")
            raise
    
    def _analyze_missing_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze missing data patterns."""
        missing_info = {}
        total_cells = len(df) * len(df.columns)
        
        # Overall missing data
        total_missing = df.isnull().sum().sum()
        missing_info['total_missing'] = int(total_missing)
        missing_info['missing_percentage'] = round((total_missing / total_cells) * 100, 2)
        
        # Per column analysis
        column_missing = df.isnull().sum()
        missing_info['by_column'] = {}
        
        for col in df.columns:
            missing_count = int(column_missing[col])
            missing_pct = round((missing_count / len(df)) * 100, 2)
            missing_info['by_column'][col] = {
                'count': missing_count,
                'percentage': missing_pct
            }
        
        # Identify problematic columns (>50% missing)
        problematic_cols = [col for col, info in missing_info['by_column'].items() 
                          if info['percentage'] > 50]
        missing_info['problematic_columns'] = problematic_cols
        
        return missing_info
    
    def _analyze_data_types(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze and recommend data type optimizations."""
        type_info = {}
        
        for col in df.columns:
            current_dtype = str(df[col].dtype)
            type_info[col] = {
                'current_type': current_dtype,
                'recommended_type': self._recommend_data_type(df[col]),
                'unique_values': int(df[col].nunique()),
                'unique_percentage': round((df[col].nunique() / len(df)) * 100, 2)
            }
        
        return type_info
    
    def _recommend_data_type(self, series: pd.Series) -> str:
        """Recommend optimal data type for a series."""
        if series.dtype == 'object':
            # Try to convert to numeric
            try:
                pd.to_numeric(series, errors='raise')
                return 'numeric (int/float)'
            except:
                # Try to convert to datetime
                try:
                    pd.to_datetime(series, errors='raise')
                    return 'datetime'
                except:
                    # Check if it's categorical
                    unique_ratio = series.nunique() / len(series)
                    if unique_ratio < 0.1:  # Less than 10% unique values
                        return 'category'
                    return 'text'
        
        elif series.dtype in ['int64', 'float64']:
            # Check if we can downcast
            if series.dtype == 'int64':
                if series.min() >= 0 and series.max() <= 255:
                    return 'uint8'
                elif series.min() >= -128 and series.max() <= 127:
                    return 'int8'
                elif series.min() >= -32768 and series.max() <= 32767:
                    return 'int16'
                else:
                    return 'int32'
            return str(series.dtype)
        
        return str(series.dtype)
    
    def _analyze_duplicates(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze duplicate records."""
        # Full row duplicates
        duplicate_rows = df.duplicated().sum()
        
        # Partial duplicates (by key columns if identifiable)
        duplicate_info = {
            'full_duplicates': int(duplicate_rows),
            'duplicate_percentage': round((duplicate_rows / len(df)) * 100, 2),
            'unique_rows': int(len(df) - duplicate_rows)
        }
        
        # Identify potential ID columns
        potential_ids = []
        for col in df.columns:
            if df[col].nunique() == len(df) and not df[col].isnull().any():
                potential_ids.append(col)
        
        duplicate_info['potential_id_columns'] = potential_ids
        
        return duplicate_info
    
    def _generate_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate comprehensive statistical summary."""
        stats = {}
        
        # Numeric columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            stats['numeric'] = {}
            for col in numeric_cols:
                col_stats = {
                    'mean': float(df[col].mean()) if not df[col].isnull().all() else None,
                    'median': float(df[col].median()) if not df[col].isnull().all() else None,
                    'std': float(df[col].std()) if not df[col].isnull().all() else None,
                    'min': float(df[col].min()) if not df[col].isnull().all() else None,
                    'max': float(df[col].max()) if not df[col].isnull().all() else None,
                    'outliers': self._detect_outliers(df[col])
                }
                stats['numeric'][col] = col_stats
        
        # Categorical columns
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns
        if len(categorical_cols) > 0:
            stats['categorical'] = {}
            for col in categorical_cols:
                top_values = df[col].value_counts().head(5).to_dict()
                stats['categorical'][col] = {
                    'unique_count': int(df[col].nunique()),
                    'most_frequent': top_values
                }
        
        return stats
    
    def _detect_outliers(self, series: pd.Series) -> Dict[str, Any]:
        """Detect outliers using IQR method."""
        if series.dtype not in [np.number] or series.isnull().all():
            return {'count': 0, 'percentage': 0.0}
        
        Q1 = series.quantile(0.25)
        Q3 = series.quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        outliers = series[(series < lower_bound) | (series > upper_bound)]
        
        return {
            'count': len(outliers),
            'percentage': round((len(outliers) / len(series)) * 100, 2),
            'bounds': {'lower': float(lower_bound), 'upper': float(upper_bound)}
        }
    
    def _generate_recommendations(self, df: pd.DataFrame) -> List[str]:
        """Generate data quality recommendations."""
        recommendations = []
        
        # Missing data recommendations
        missing_data = self._analyze_missing_data(df)
        if missing_data['missing_percentage'] > 10:
            recommendations.append(f"High missing data detected ({missing_data['missing_percentage']:.1f}%). Consider data imputation strategies.")
        
        # Duplicate recommendations
        duplicate_data = self._analyze_duplicates(df)
        if duplicate_data['duplicate_percentage'] > 5:
            recommendations.append(f"Significant duplicates found ({duplicate_data['duplicate_percentage']:.1f}%). Consider deduplication.")
        
        # Data type recommendations
        type_data = self._analyze_data_types(df)
        memory_optimization = False
        for col, info in type_data.items():
            if info['current_type'] != info['recommended_type']:
                memory_optimization = True
                break
        
        if memory_optimization:
            recommendations.append("Data type optimization opportunities detected. Consider converting to more efficient types.")
        
        # Size recommendations
        memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
        if memory_mb > 100:
            recommendations.append(f"Large dataset detected ({memory_mb:.1f}MB). Consider data sampling for faster analysis.")
        
        return recommendations
    
    @log_performance
    def detect_correlations(self, df: pd.DataFrame, threshold: float = 0.7) -> Dict[str, Any]:
        """
        Detect strong correlations between numeric variables.
        
        Args:
            df: DataFrame to analyze
            threshold: Correlation threshold (default 0.7)
        
        Returns:
            Dictionary with correlation analysis results
        """
        data_hash = self._get_data_hash(df)
        cache_key = self._generate_cache_key(data_hash, "correlations", {"threshold": threshold})
        
        # Check cache
        if self.cache_enabled:
            cached_result = cache_manager.get(cache_key)
            if cached_result:
                logger.info("Correlation analysis retrieved from cache")
                return cached_result
        
        logger.info(f"Detecting correlations with threshold: {threshold}")
        
        try:
            numeric_df = df.select_dtypes(include=[np.number])
            
            if len(numeric_df.columns) < 2:
                return {
                    'correlations': [],
                    'correlation_matrix': {},
                    'strong_correlations': 0,
                    'message': 'Insufficient numeric columns for correlation analysis'
                }
            
            # Calculate correlation matrix
            corr_matrix = numeric_df.corr()
            
            # Find strong correlations
            strong_correlations = []
            for i, col1 in enumerate(corr_matrix.columns):
                for j, col2 in enumerate(corr_matrix.columns):
                    if i < j:  # Avoid duplicates and self-correlation
                        corr_value = corr_matrix.loc[col1, col2]
                        if abs(corr_value) >= threshold and not np.isnan(corr_value):
                            strong_correlations.append({
                                'variable1': col1,
                                'variable2': col2,
                                'correlation': round(float(corr_value), 3),
                                'strength': self._interpret_correlation_strength(abs(corr_value))
                            })
            
            # Sort by absolute correlation value
            strong_correlations.sort(key=lambda x: abs(x['correlation']), reverse=True)
            
            result = {
                'correlations': strong_correlations,
                'correlation_matrix': corr_matrix.round(3).to_dict(),
                'strong_correlations': len(strong_correlations),
                'analyzed_variables': list(numeric_df.columns)
            }
            
            # Cache the result
            if self.cache_enabled:
                cache_manager.set(cache_key, result, expire_time=3600)
            
            logger.info(f"Found {len(strong_correlations)} strong correlations")
            return result
            
        except Exception as e:
            logger.error(f"Error in correlation analysis: {e}")
            raise
    
    def _interpret_correlation_strength(self, abs_corr: float) -> str:
        """Interpret correlation strength."""
        if abs_corr >= 0.9:
            return "Very Strong"
        elif abs_corr >= 0.7:
            return "Strong"
        elif abs_corr >= 0.5:
            return "Moderate"
        elif abs_corr >= 0.3:
            return "Weak"
        else:
            return "Very Weak"

# Global data processor instance
data_processor = DataProcessor()

# Legacy function for backward compatibility
def get_data_preview(upload_file, samples_rows: int = 1000) -> pd.DataFrame:
    """
    Reads a CSV file and returns a preview of the data.

    Parameters:
    - upload_file: The uploaded CSV file.
    - samples_rows: The number of rows to preview (default is 1000).

    Returns:
    - A DataFrame containing the preview of the data.
    """
    string_io = StringIO(upload_file.getvalue().decode("utf-8"))
    preview_df = pd.read_csv(string_io, nrows=samples_rows)
    return preview_df