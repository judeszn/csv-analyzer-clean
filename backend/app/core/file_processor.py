"""
Universal File Processor for Multimodal Insight Engine
Handles CSV, PDF, TXT, and Image files for AI analysis
"""

import os
import base64
import tempfile
from io import BytesIO
from typing import Union, Tuple, Dict, Any
import PyPDF2
import pdfplumber
from PIL import Image
import streamlit as st
import pandas as pd

class UniversalFileProcessor:
    """
    Handles processing of multiple file types for AI analysis
    """
    
    SUPPORTED_EXTENSIONS = {
        'csv': ['csv'],
        'pdf': ['pdf'],
        'text': ['txt', 'text'],
        'image': ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp']
    }
    
    MAX_FILE_SIZES = {
        'csv': 100 * 1024 * 1024,
        'pdf': 50 * 1024 * 1024,
        'text': 10 * 1024 * 1024,
        'image': 10 * 1024 * 1024
    }
    
    def __init__(self):
        pass

    def _get_file_bytes(self, uploaded_file: Any) -> bytes:
        """Safely get bytes from a file-like object provided by Streamlit."""
        if not uploaded_file:
            raise ValueError("No file provided to _get_file_bytes.")
            
        if hasattr(uploaded_file, 'getvalue'):
            # Handles Streamlit's UploadedFile and BytesIO
            buffer = uploaded_file.getvalue()
            if isinstance(buffer, str):
                return buffer.encode('utf-8')
            return buffer
        elif hasattr(uploaded_file, 'read'):
            # Handles standard file objects
            uploaded_file.seek(0)
            buffer = uploaded_file.read()
            if isinstance(buffer, str):
                return buffer.encode('utf-8')
            return buffer
        
        raise TypeError("File object does not support getvalue() or read() methods.")

    def get_file_type(self, filename: str) -> str:
        """Determine file type from extension"""
        if not filename:
            return 'unknown'
        ext = filename.lower().split('.')[-1]
        for file_type, extensions in self.SUPPORTED_EXTENSIONS.items():
            if ext in extensions:
                return file_type
        return 'unknown'
    
    def validate_file(self, uploaded_file, file_type: str) -> Tuple[bool, str]:
        """Validate file size and type"""
        if file_type == 'unknown':
            return False, "Unsupported file type"
        
        try:
            file_size = uploaded_file.size
        except:
            file_size = len(uploaded_file.getvalue())

        max_size = self.MAX_FILE_SIZES.get(file_type, 0)
        
        if file_size > max_size:
            size_mb = file_size / (1024 * 1024)
            max_mb = max_size / (1024 * 1024)
            return False, f"File too large ({size_mb:.1f}MB). Max size for {file_type.upper()}: {max_mb:.0f}MB"
        
        return True, "File validation successful"
    
    def process_csv(self, file_bytes: bytes) -> Dict[str, Any]:
        """Process CSV file and return data info"""
        try:
            file_data = BytesIO(file_bytes)
            df = pd.read_csv(file_data)
        except pd.errors.EmptyDataError:
            raise ValueError("The CSV file is empty.")
        except Exception as e:
            raise ValueError(f"Error reading CSV file: {e}")
            
        metadata = {
            'rows': len(df),
            'columns': len(df.columns),
            'column_names': df.columns.tolist(),
        }
        
        return {
            'type': 'csv',
            'content': self._df_to_text_summary(df),  # Add content field for consistency
            'dataframe': df, # The agent needs this
            'metadata': metadata,
            'text_summary': self._df_to_text_summary(df)
        }

    def process_pdf(self, file_bytes: bytes) -> Dict[str, Any]:
        """Extract text from PDF file"""
        if not file_bytes.startswith(b'%PDF'):
            raise ValueError("File does not appear to be a valid PDF.")
        
        extracted_text = ""
        metadata = {'pages': 0}
        
        try:
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                metadata['pages'] = len(pdf.pages)
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        extracted_text += page_text + "\n\n"
        except Exception as e:
            raise IOError(f"Could not process PDF file. It might be corrupted or password-protected. Error: {e}")

        metadata['word_count'] = len(extracted_text.split())
        
        return {
            'content': extracted_text,
            'type': 'pdf',
            'metadata': metadata
        }

    def process_txt(self, file_bytes: bytes) -> Dict[str, Any]:
        """Process text file"""
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252']
        text_content = None
        for encoding in encodings_to_try:
            try:
                text_content = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if text_content is None:
            raise ValueError("Failed to decode text file with common encodings.")
            
        return {
            'content': text_content,
            'type': 'text',
            'metadata': {'word_count': len(text_content.split())}
        }

    def process_image(self, file_bytes: bytes) -> Dict[str, Any]:
        """Process image file and convert to base64"""
        try:
            image = Image.open(BytesIO(file_bytes))
            width, height = image.size
            format_name = image.format or 'unknown'
            
            base64_image = base64.b64encode(file_bytes).decode('utf-8')
            
            return {
                'content': base64_image,
                'type': 'image',
                'metadata': {'width': width, 'height': height, 'format': format_name}
            }
        except Exception as e:
            raise IOError(f"Cannot process image file. It might be corrupted or in an unsupported format. Error: {e}")
    
    def process_file(self, uploaded_file: Any) -> Dict[str, Any]:
        """Main processing function that routes to appropriate handler"""
        file_type = self.get_file_type(uploaded_file.name)
        
        is_valid, validation_message = self.validate_file(uploaded_file, file_type)
        if not is_valid:
            raise ValueError(validation_message)
        
        try:
            file_bytes = self._get_file_bytes(uploaded_file)
        except Exception as e:
            raise IOError(f"Could not read file content: {e}")

        processing_functions = {
            'csv': self.process_csv,
            'pdf': self.process_pdf,
            'text': self.process_txt,
            'image': self.process_image,
        }
        
        process_function = processing_functions.get(file_type)
        
        if not process_function:
            raise ValueError(f"Unsupported file type: {file_type}")
            
        try:
            processed_data = process_function(file_bytes)
            processed_data['raw_content'] = file_bytes # Add raw bytes for hashing
            return processed_data
        except Exception as e:
            raise RuntimeError(f"Failed to process {file_type} file: {e}")

    def _df_to_text_summary(self, df: pd.DataFrame) -> str:
        """Convert DataFrame to text summary for AI analysis"""
        summary = f"Dataset Overview:\n"
        summary += f"- Shape: {df.shape[0]} rows, {df.shape[1]} columns\n"
        summary += f"- Columns: {', '.join(df.columns.tolist())}\n\n"
        
        summary += "Column Data Types:\n"
        for col, dtype in df.dtypes.items():
            summary += f"- {col}: {dtype}\n"
        
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            summary += f"\nNumeric Columns Summary:\n"
            summary += df[numeric_cols].describe().to_string()
        
        summary += f"\n\nFirst 5 rows:\n"
        summary += df.head().to_string()
        
        return summary

# Singleton instance
file_processor = UniversalFileProcessor()
