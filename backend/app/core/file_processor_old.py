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
    
    # Supported file types
    SUPPORTED_EXTENSIONS = {
        'csv': ['csv'],
        'pdf': ['pdf'],
        'text': ['txt', 'text'],
        'image': ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp']
    }
    
    MAX_FILE_SIZES = {
        'csv': 100 * 1024 * 1024,    # 100MB for CSV
        'pdf': 50 * 1024 * 1024,     # 50MB for PDF
        'text': 10 * 1024 * 1024,    # 10MB for text
        'image': 10 * 1024 * 1024    # 10MB for images
    }
    
    def __init__(self):
        self.processed_content = None
        self.file_type = None
        self.metadata = {}
    
    @property
    def supported_types(self):
        """Return list of all supported file extensions"""
        return sum(self.SUPPORTED_EXTENSIONS.values(), [])
    
    def get_file_type(self, filename: str) -> str:
        """Determine file type from extension"""
        if not filename:
            return 'unknown'
            
        extension = filename.split('.')[-1].lower()
        
        for file_type, extensions in self.SUPPORTED_EXTENSIONS.items():
            if extension in extensions:
                return file_type
        
        return 'unknown'
    
    def validate_file(self, uploaded_file, file_type: str) -> Tuple[bool, str]:
        """Validate file size and type"""
        if not uploaded_file:
            return False, "No file uploaded"
        
        if file_type == 'unknown':
            return False, f"Unsupported file type. Supported: {', '.join(sum(self.SUPPORTED_EXTENSIONS.values(), []))}"
        
        # Check file size
        file_size = uploaded_file.size
        max_size = self.MAX_FILE_SIZES.get(file_type, 5 * 1024 * 1024)  # Default 5MB
        
        if file_size > max_size:
            size_mb = file_size / (1024 * 1024)
            max_mb = max_size / (1024 * 1024)
            return False, f"File too large ({size_mb:.1f}MB). Maximum size for {file_type}: {max_mb:.0f}MB"
        
        return True, "File validation successful"
    
    def process_csv(self, uploaded_file) -> Dict[str, Any]:
        """Process CSV file and return data info"""
        try:
            # Safely get file data - handle both Streamlit UploadedFile and regular file objects
            try:
                # First, try to get the raw bytes from the file
                if hasattr(uploaded_file, 'getvalue'):
                    # For Streamlit UploadedFile objects
                    raw_bytes = uploaded_file.getvalue()
                    if isinstance(raw_bytes, str):
                        # If it's already a string, encode it to bytes
                        raw_bytes = raw_bytes.encode('utf-8')
                    file_data = BytesIO(raw_bytes)
                elif hasattr(uploaded_file, 'read'):
                    # For regular file objects
                    uploaded_file.seek(0)
                    raw_data = uploaded_file.read()
                    if isinstance(raw_data, str):
                        raw_data = raw_data.encode('utf-8')
                    file_data = BytesIO(raw_data)
                else:
                    # Direct file object
                    file_data = uploaded_file
            except Exception as e:
                raise Exception(f"Cannot read CSV file data: {str(e)}")
                
            # Attempt to read CSV with error handling
            try:
                df = pd.read_csv(file_data)
            except pd.errors.EmptyDataError:
                raise Exception("The CSV file is empty")
            except pd.errors.ParserError as e:
                raise Exception(f"CSV parsing error: {str(e)}. The file may be corrupted or not a valid CSV")
            except Exception as e:
                raise Exception(f"Error reading CSV file: {str(e)}")
            
            # Basic statistics
            metadata = {
                'rows': len(df),
                'columns': len(df.columns),
                'column_names': df.columns.tolist(),
                'dtypes': {str(k): str(v) for k, v in df.dtypes.to_dict().items()},  # Convert to strings for serialization
                'memory_usage': int(df.memory_usage(deep=True).sum()),
                'has_null': bool(df.isnull().any().any()),
                'null_counts': {str(k): int(v) for k, v in df.isnull().sum().to_dict().items()}
            }
            
            # Sample data preview
            preview = df.head(10).to_dict('records')
            
            return {
                'type': 'csv',
                'dataframe': df,
                'metadata': metadata,
                'preview': preview,
                'text_representation': self._df_to_text_summary(df)
            }
            
        except Exception as e:
            raise Exception(f"Error processing CSV file: {str(e)}")
    
    def process_pdf(self, uploaded_file) -> Dict[str, Any]:
        """Extract text from PDF file"""
        try:
            # Safely get file bytes - ensure we get proper bytes
            try:
                if hasattr(uploaded_file, 'getvalue'):
                    # For Streamlit's UploadedFile
                    pdf_bytes = uploaded_file.getvalue()
                    if not isinstance(pdf_bytes, bytes):
                        raise Exception("PDF data is not in bytes format")
                elif hasattr(uploaded_file, 'read'):
                    # For regular file objects
                    uploaded_file.seek(0)
                    pdf_bytes = uploaded_file.read()
                    if not isinstance(pdf_bytes, bytes):
                        raise Exception("PDF data is not in bytes format")
                else:
                    raise Exception("Cannot access PDF file data")
            except Exception as e:
                raise Exception(f"Cannot read PDF data: {str(e)}")
            
            # Validate that we have actual PDF bytes
            if not pdf_bytes or len(pdf_bytes) == 0:
                raise Exception("PDF file is empty")
            
            # Check PDF header
            if not pdf_bytes.startswith(b'%PDF'):
                raise Exception("File does not appear to be a valid PDF")
            
            # Save bytes to temporary file
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(pdf_bytes)
                    tmp_file_path = tmp_file.name
            except Exception as e:
                raise Exception(f"Cannot create temporary PDF file: {str(e)}")
            
            extracted_text = ""
            metadata = {'pages': 0, 'extraction_method': 'unknown'}
            
            try:
                # First try with pdfplumber (better for complex layouts)
                with pdfplumber.open(tmp_file_path) as pdf:
                    metadata['pages'] = len(pdf.pages)
                    metadata['extraction_method'] = 'pdfplumber'
                    
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            extracted_text += page_text + "\n\n"
                
            except Exception as e1:
                # Fallback to PyPDF2
                try:
                    with open(tmp_file_path, 'rb') as pdf_file:
                        pdf_reader = PyPDF2.PdfReader(pdf_file)
                        metadata['pages'] = len(pdf_reader.pages)
                        metadata['extraction_method'] = 'PyPDF2'
                        
                        for page in pdf_reader.pages:
                            page_text = page.extract_text()
                            if page_text:
                                extracted_text += page_text + "\n\n"
                                
                except Exception as e2:
                    raise Exception(f"Failed to extract text with both methods. pdfplumber: {e1}, PyPDF2: {e2}")
            
            finally:
                # Clean up temporary file
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
            
            if not extracted_text.strip():
                raise Exception("No text could be extracted from the PDF. The file might be image-based or corrupted.")
            
            metadata['text_length'] = len(extracted_text)
            metadata['word_count'] = len(extracted_text.split())
            
            return {
                'type': 'pdf',
                'text': extracted_text.strip(),
                'metadata': metadata
            }
            
        except Exception as e:
            raise Exception(f"Error processing PDF file: {str(e)}")
    
    def process_txt(self, uploaded_file) -> Dict[str, Any]:
        """Process text file"""
        try:
            # First safely get file bytes
            file_bytes = None
            try:
                # For Streamlit's UploadedFile
                file_bytes = uploaded_file.getvalue()
            except AttributeError:
                # Fall back to read() for standard file objects
                try:
                    uploaded_file.seek(0)
                    file_bytes = uploaded_file.read()
                except Exception as e:
                    raise Exception(f"Cannot read text file data: {str(e)}")
            
            # Try different encodings
            encodings_to_try = ['utf-8', 'latin-1', 'cp1252']
            text_content = None
            used_encoding = None
            
            # Now decode the bytes with various encodings
            for encoding in encodings_to_try:
                try:
                    if isinstance(file_bytes, bytes):
                        text_content = file_bytes.decode(encoding)
                    else:
                        # If somehow we got a string already, use it
                        text_content = str(file_bytes)
                    used_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    print(f"Error with encoding {encoding}: {str(e)}")
            
            # If all encodings failed, raise an error
            if text_content is None:
                raise Exception("Failed to decode text with any encoding")
            
            # Count words for metadata
            word_count = len(text_content.split())
            
            return {
                'content': text_content,
                'type': 'text',
                'metadata': {
                    'word_count': word_count,
                    'encoding': used_encoding or 'unknown',
                    'size_bytes': len(file_bytes) if isinstance(file_bytes, bytes) else -1
                }
            }
        except Exception as e:
            raise Exception(f"Error processing text file: {str(e)}")
    
    def process_image(self, uploaded_file) -> Dict[str, Any]:
        """Process image file and convert to base64"""
        try:
            # Safely get image bytes - ensure we get proper bytes
            try:
                if hasattr(uploaded_file, 'getvalue'):
                    # For Streamlit's UploadedFile
                    image_bytes = uploaded_file.getvalue()
                    if not isinstance(image_bytes, bytes):
                        raise Exception("Image data is not in bytes format")
                elif hasattr(uploaded_file, 'read'):
                    # For regular file objects
                    uploaded_file.seek(0)
                    image_bytes = uploaded_file.read()
                    if not isinstance(image_bytes, bytes):
                        raise Exception("Image data is not in bytes format")
                else:
                    raise Exception("Cannot access image file data")
            except Exception as e:
                raise Exception(f"Cannot read image data: {str(e)}")
            
            # Validate that we have actual image bytes
            if not image_bytes or len(image_bytes) == 0:
                raise Exception("Image file is empty")
            
            try:
                # Open image with PIL to get metadata and validate
                image = Image.open(BytesIO(image_bytes))
                width, height = image.size
                format_name = image.format or 'unknown'
                mode = image.mode
                
                # Convert to RGB if necessary for compatibility
                if mode not in ['RGB', 'RGBA']:
                    image = image.convert('RGB')
                
                # Convert to base64 for Claude vision API
                base64_image = base64.b64encode(image_bytes).decode('utf-8')
                
                return {
                    'content': base64_image,
                    'type': 'image',
                    'metadata': {
                        'width': width,
                        'height': height,
                        'format': format_name,
                        'mode': mode,
                        'size_bytes': len(image_bytes)
                    }
                }
            except Exception as e:
                raise Exception(f"Cannot process image: {str(e)}")
                
        except Exception as e:
            raise Exception(f"Error processing image file: {str(e)}")
                # If getvalue() is not available, try to read directly
                try:
                    uploaded_file.seek(0)
                    image_bytes = uploaded_file.read()
                except Exception:
                    # Last resort, try to read from file path if available
                    if hasattr(uploaded_file, "name"):
                        with open(uploaded_file.name, "rb") as f:
                            image_bytes = f.read()
                    else:
                        raise Exception("Cannot read image data from provided file object")
            
            # Open image from bytes buffer instead of file object
            image = Image.open(BytesIO(image_bytes))
            
            # Get image metadata
            metadata = {
                'format': image.format,
                'mode': image.mode,
                'size': image.size,
                'width': image.width,
                'height': image.height
            }
            
            # Convert to RGB if necessary (for consistency)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Convert to RGB for better compatibility
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                rgb_image.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                image = rgb_image
                metadata['converted_to_rgb'] = True
            
            # Resize if too large (to manage token usage)
            max_dimension = 1024
            if max(image.width, image.height) > max_dimension:
                ratio = max_dimension / max(image.width, image.height)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                metadata['resized'] = True
                metadata['new_size'] = new_size
            
            # Convert to base64
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            img_bytes = buffer.getvalue()
            base64_string = base64.b64encode(img_bytes).decode('utf-8')
            
            metadata['base64_length'] = len(base64_string)
            metadata['file_size_bytes'] = len(img_bytes)
            
            return {
                'type': 'image',
                'base64': base64_string,
                'image': image,
                'metadata': metadata
            }
            
        except Exception as e:
            raise Exception(f"Error processing image file: {str(e)}")
    
    def process_file(self, uploaded_file) -> Dict[str, Any]:
        """Main processing function that routes to appropriate handler"""
        if not uploaded_file:
            raise Exception("No file provided")
        
        try:
            # Verify we have a valid file object with required methods
            if not hasattr(uploaded_file, 'name'):
                raise Exception("Invalid file object: missing name attribute")
                
            # Determine file type
            file_type = self.get_file_type(uploaded_file.name)
            
            # Check if the file has necessary buffer methods
            has_buffer_methods = hasattr(uploaded_file, 'read') or hasattr(uploaded_file, 'getvalue')
            if not has_buffer_methods:
                raise Exception("Invalid file object: missing required buffer methods (read or getvalue)")
            
            # Validate file
            is_valid, validation_message = self.validate_file(uploaded_file, file_type)
            if not is_valid:
                raise Exception(validation_message)
            
            # Reset file pointer if possible
            try:
                if hasattr(uploaded_file, 'seek'):
                    uploaded_file.seek(0)
            except Exception as e:
                # Log but continue - some file objects may not need seek
                print(f"Warning: Could not seek file: {str(e)}")
            
            # Process based on file type with explicit error handling
            if file_type == 'csv':
                return self.process_csv(uploaded_file)
            elif file_type == 'pdf':
                return self.process_pdf(uploaded_file)
            elif file_type == 'text':
                return self.process_txt(uploaded_file)
            elif file_type == 'image':
                return self.process_image(uploaded_file)
            else:
                raise Exception(f"Unsupported file type: {file_type}")
        except Exception as e:
            error_msg = f"Error processing file: {str(e)}"
            import traceback
            traceback_str = traceback.format_exc()
            print(f"File processing error: {error_msg}\n{traceback_str}")
            raise Exception(error_msg)
    
    def _df_to_text_summary(self, df: pd.DataFrame) -> str:
        """Convert DataFrame to text summary for AI analysis"""
        summary = f"Dataset Overview:\n"
        summary += f"- Shape: {df.shape[0]} rows, {df.shape[1]} columns\n"
        summary += f"- Columns: {', '.join(df.columns.tolist())}\n\n"
        
        # Data types
        summary += "Column Data Types:\n"
        for col, dtype in df.dtypes.items():
            summary += f"- {col}: {dtype}\n"
        
        # Basic statistics for numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            summary += f"\nNumeric Columns Summary:\n"
            summary += df[numeric_cols].describe().to_string()
        
        # Sample data
        summary += f"\n\nFirst 5 rows:\n"
        summary += df.head().to_string()
        
        return summary

# Singleton instance
file_processor = UniversalFileProcessor()
