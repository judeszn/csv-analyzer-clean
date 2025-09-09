"""
Universal AI Agent for multimodal analysis using Claude Haiku
Handles CSV, PDF, TXT, and Image files with advanced AI capabilities
"""

import os
import pandas as pd
import tempfile
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain.schema import AIMessage, HumanMessage, SystemMessage

# Load environment variables
load_dotenv()

class UniversalInsightAgent:
    """
    Multimodal AI agent that can analyze different file types
    """
    
    def __init__(self):
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.is_test_mode = self.anthropic_api_key == "sk-ant-test-key-for-testing"
        self.claude_model = None
        self.model_error = None
        
        # Initialize Claude model with error handling to prevent UI blocking
        if not self.is_test_mode:
            try:
                self.claude_model = ChatAnthropic(
                    model="claude-3-haiku-20240307",
                    temperature=0,
                    anthropic_api_key=self.anthropic_api_key,
                    timeout=10  # Add timeout to prevent hanging
                )
            except Exception as e:
                self.model_error = str(e)
                self.is_test_mode = True  # Fall back to test mode on error
        
        # CSV analysis - now using direct Claude analysis instead of SQL agent
        self.current_db_path = None
    
    def cleanup_database(self):
        """Clean up temporary database files"""
        if self.current_db_path and os.path.exists(self.current_db_path):
            try:
                os.unlink(self.current_db_path)
                self.current_db_path = None
            except Exception:
                pass  # Ignore cleanup errors

    def analyze_csv(self, processed_data: Dict[str, Any], user_question: str) -> str:
        """Analyze CSV data using direct Claude analysis"""
        try:
            # Get the text summary and metadata
            text_summary = processed_data['text_summary']
            metadata = processed_data['metadata']
            
            # Create enhanced prompt for CSV analysis
            system_prompt = """You are an expert data analyst. Your task is to analyze the provided CSV dataset summary and answer the user's question comprehensively.

Provide insights that are:
1. Directly relevant to the user's question
2. Supported by the data characteristics shown
3. Include specific statistics and patterns
4. Offer actionable recommendations
5. Highlight key trends and outliers

Be thorough but concise in your analysis."""

            user_prompt = f"""
CSV Dataset Analysis Request:

Dataset Summary:
{text_summary}

Dataset Metadata:
- Rows: {metadata.get('rows', 'unknown')}
- Columns: {metadata.get('columns', 'unknown')}
- Column Names: {', '.join(metadata.get('column_names', []))}

User Question: {user_question}

Please provide a comprehensive analysis addressing the user's question with specific insights, patterns, and recommendations based on the dataset characteristics provided.
"""

            # Use Claude for analysis
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.claude_model.invoke(messages)
            return response.content
            
        except Exception as e:
            return f"Error analyzing CSV: {str(e)}"
    
    def analyze_text(self, processed_data: Dict[str, Any], user_question: str) -> str:
        """Analyze text content (PDF or TXT)"""
        try:
            text_content = processed_data['content']
            metadata = processed_data['metadata']
            
            # Create enhanced prompt for text analysis
            system_prompt = """You are an expert text analyzer. Your task is to carefully read and analyze the provided text content to answer the user's question comprehensively. 

Provide insights that are:
1. Directly relevant to the user's question
2. Supported by specific evidence from the text
3. Well-structured and easy to understand
4. Include key quotes or references when appropriate

Be thorough but concise in your analysis."""

            user_prompt = f"""
Text Content Analysis Request:

Document Metadata:
- Type: {processed_data['type'].upper()}
- Length: {metadata.get('text_length', 'unknown')} characters
- Word count: {metadata.get('word_count', 'unknown')} words
{f"- Pages: {metadata.get('pages', 'unknown')}" if 'pages' in metadata else ""}

User Question: {user_question}

Text Content:
{text_content[:8000]}{"..." if len(text_content) > 8000 else ""}

Please analyze the above text content and provide a comprehensive answer to the user's question.
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.claude_model.invoke(messages)
            return response.content
            
        except Exception as e:
            return f"Error analyzing text: {str(e)}"
    
    def analyze_image(self, processed_data: Dict[str, Any], user_question: str) -> str:
        """Analyze image content using Claude's vision capabilities"""
        try:
            base64_image = processed_data['content']  # Fixed: content field, not base64
            metadata = processed_data['metadata']
            
            # Create enhanced prompt for image analysis
            system_prompt = """You are an expert image analyzer with capabilities to extract and interpret information from various types of images including:
- Charts, graphs, and data visualizations
- Screenshots of text, tables, and documents
- Diagrams, flowcharts, and technical drawings
- General photographs and illustrations

Your task is to carefully examine the provided image and answer the user's question with detailed, accurate information based on what you can see in the image.

Provide analysis that is:
1. Specific and detailed about visual elements
2. Directly addresses the user's question
3. Includes extracted text, data, or measurements when visible
4. Describes relationships, patterns, or trends shown
5. Professional and thorough"""

            user_prompt = f"""
Image Analysis Request:

Image Metadata:
- Format: {metadata.get('format', 'unknown')}
- Size: {metadata.get('width', 'unknown')} x {metadata.get('height', 'unknown')} pixels
- File size: {metadata.get('file_size_bytes', 'unknown')} bytes

User Question: {user_question}

Please analyze the provided image and answer the user's question based on what you can see in the image. If the image contains text, data, charts, or other specific information, please extract and interpret it accurately.
"""

            # Determine the correct media type based on image format
            image_format = metadata.get('format', 'JPEG').lower()
            # Map common formats to their MIME types
            format_to_mime = {
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'gif': 'image/gif',
                'webp': 'image/webp',
                'bmp': 'image/bmp'
            }
            media_type = format_to_mime.get(image_format, 'image/jpeg')

            # Create message with image
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=[
                    {
                        "type": "text", 
                        "text": user_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{base64_image}"
                        }
                    }
                ])
            ]
            
            response = self.claude_model.invoke(messages)
            return response.content
            
        except Exception as e:
            return f"Error analyzing image: {str(e)}"
    
    def analyze_content(self, processed_data: Dict[str, Any], user_question: str) -> str:
        """Main analysis function that routes to appropriate analyzer"""
        content_type = processed_data.get('type')
        
        # Test mode - return mock responses
        if self.is_test_mode:
            return self._get_test_mode_response(content_type, user_question, processed_data)
        
        if content_type == 'csv':
            return self.analyze_csv(processed_data, user_question)
        elif content_type in ['pdf', 'text']:
            return self.analyze_text(processed_data, user_question)
        elif content_type == 'image':
            return self.analyze_image(processed_data, user_question)
        else:
            return f"Unsupported content type: {content_type}"
    
    def _get_test_mode_response(self, content_type: str, user_question: str, processed_data: Dict[str, Any]) -> str:
        """Generate mock responses for test mode"""
        if content_type == 'csv':
            return f"""## CSV Data Analysis (Test Mode)

**Your Question:** {user_question}

**Analysis Results:**
- **Dataset Overview:** Your CSV contains {processed_data.get('metadata', {}).get('rows', 'multiple')} rows and {processed_data.get('metadata', {}).get('columns', 'several')} columns
- **Key Insights:** The data shows interesting patterns across different categories
- **Data Quality:** Good data structure with minimal missing values
- **Recommendations:** Consider analyzing trends by category and time period

**Sample Findings:**
- Top performing categories identified
- Regional distribution patterns observed
- Customer satisfaction metrics above average

*Note: This is a test mode response. Connect a real API key for actual AI analysis.*"""

        elif content_type == 'image':
            return f"""## Image Analysis (Test Mode)

**Your Question:** {user_question}

**Visual Analysis Results:**
- **Image Type:** Screenshot/Document image detected
- **Content:** The image appears to contain structured information, possibly a dashboard or data visualization
- **Text Elements:** Multiple text sections and data points visible
- **Layout:** Well-organized information presentation
- **Quality:** Clear and readable image quality

**Key Observations:**
- Professional interface design
- Data-driven content structure
- Multiple information sections
- Good visual hierarchy

*Note: This is a test mode response. Connect a real API key for detailed visual analysis.*"""

        elif content_type in ['pdf', 'text']:
            return f"""## Text Analysis (Test Mode)

**Your Question:** {user_question}

**Document Analysis Results:**
- **Content Type:** Business/technical document
- **Structure:** Well-organized with clear sections
- **Key Topics:** Strategic insights and recommendations
- **Tone:** Professional and analytical

**Summary:**
The document presents comprehensive analysis with actionable insights. It covers multiple aspects of business performance and provides strategic recommendations for future growth.

*Note: This is a test mode response. Connect a real API key for actual document analysis.*"""

        else:
            return f"**Test Mode:** Mock analysis for {content_type} file type. Your question: '{user_question}'"
    
    def cleanup(self):
        """Clean up temporary resources"""
        if self.current_db_path and os.path.exists(self.current_db_path):
            try:
                os.unlink(self.current_db_path)
            except:
                pass
    
    def get_content_summary(self, processed_data: Dict[str, Any]) -> str:
        """Get a brief summary of the processed content"""
        content_type = processed_data.get('type')
        metadata = processed_data.get('metadata', {})
        
        if content_type == 'csv':
            return f"CSV file with {metadata.get('rows', 'unknown')} rows and {metadata.get('columns', 'unknown')} columns"
        elif content_type == 'pdf':
            return f"PDF document with {metadata.get('pages', 'unknown')} pages and {metadata.get('word_count', 'unknown')} words"
        elif content_type == 'text':
            return f"Text file with {metadata.get('word_count', 'unknown')} words and {metadata.get('line_count', 'unknown')} lines"
        elif content_type == 'image':
            return f"Image file ({metadata.get('format', 'unknown')}) - {metadata.get('width', 'unknown')}x{metadata.get('height', 'unknown')} pixels"
        else:
            return f"Unknown content type: {content_type}"

# Singleton instance
universal_agent = UniversalInsightAgent()
