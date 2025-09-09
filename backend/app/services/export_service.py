import io
import json
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from app.utils.logging_config import get_logger, log_performance
from app.core.analysis_history import ExportFormat

logger = get_logger('csv_analyzer')

class ReportExporter:
    """
    Professional report export service for CSV Analyzer Pro.
    
    Features:
    - Export analyses to PDF, Excel, CSV, JSON
    - Professional formatting and branding
    - Batch export capabilities
    - Custom report templates
    """
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        logger.info("Report exporter initialized")
    
    def _setup_custom_styles(self):
        """Setup custom styles for PDF reports."""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            textColor=colors.HexColor('#2E86C1')
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#1B4F72')
        ))
    
    @log_performance
    def export_single_analysis(self, analysis_record: Dict, format: ExportFormat) -> bytes:
        """
        Export a single analysis to the specified format.
        
        Args:
            analysis_record: Analysis data dictionary
            format: Export format (PDF, Excel, CSV, JSON)
            
        Returns:
            bytes: Exported file content
        """
        try:
            if format == ExportFormat.PDF:
                return self._export_to_pdf([analysis_record])
            elif format == ExportFormat.EXCEL:
                return self._export_to_excel([analysis_record])
            elif format == ExportFormat.CSV:
                return self._export_to_csv([analysis_record])
            elif format == ExportFormat.JSON:
                return self._export_to_json([analysis_record])
            else:
                raise ValueError(f"Unsupported export format: {format}")
                
        except Exception as e:
            logger.error(f"Error exporting analysis: {e}")
            raise
    
    @log_performance
    def export_multiple_analyses(self, analysis_records: List[Dict], format: ExportFormat) -> bytes:
        """Export multiple analyses to the specified format."""
        try:
            if format == ExportFormat.PDF:
                return self._export_to_pdf(analysis_records)
            elif format == ExportFormat.EXCEL:
                return self._export_to_excel(analysis_records)
            elif format == ExportFormat.CSV:
                return self._export_to_csv(analysis_records)
            elif format == ExportFormat.JSON:
                return self._export_to_json(analysis_records)
            else:
                raise ValueError(f"Unsupported export format: {format}")
                
        except Exception as e:
            logger.error(f"Error exporting multiple analyses: {e}")
            raise
    
    def _export_to_pdf(self, analyses: List[Dict]) -> bytes:
        """Export analyses to PDF format."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        
        # Title
        title = Paragraph("CSV Analyzer Pro - Analysis Report", self.styles['CustomTitle'])
        story.append(title)
        story.append(Spacer(1, 20))
        
        # Report metadata
        metadata = [
            ["Report Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ["Total Analyses:", str(len(analyses))],
            ["Export Format:", "PDF Report"]
        ]
        
        metadata_table = Table(metadata, colWidths=[2*inch, 3*inch])
        metadata_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8F9FA')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        
        story.append(metadata_table)
        story.append(Spacer(1, 30))
        
        # Individual analyses
        for i, analysis in enumerate(analyses, 1):
            # Analysis header
            header = Paragraph(f"Analysis #{i}", self.styles['CustomHeading'])
            story.append(header)
            
            # Analysis details
            details = [
                ["File:", analysis.get('filename', 'N/A')],
                ["Timestamp:", analysis.get('timestamp', 'N/A')],
                ["Question:", analysis.get('question', 'N/A')],
                ["Execution Time:", f"{analysis.get('execution_time', 0):.2f} seconds"],
                ["Subscription Tier:", analysis.get('subscription_tier', 'free').title()]
            ]
            
            details_table = Table(details, colWidths=[1.5*inch, 4*inch])
            details_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#E8F4FD')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#D5DBDB'))
            ]))
            
            story.append(details_table)
            story.append(Spacer(1, 15))
            
            # Response
            response_header = Paragraph("Analysis Results:", self.styles['Heading3'])
            story.append(response_header)
            
            # Format response text
            response_text = analysis.get('response', 'No response available')
            response_para = Paragraph(response_text, self.styles['Normal'])
            story.append(response_para)
            story.append(Spacer(1, 30))
        
        # Footer
        footer = Paragraph(
            "Generated by CSV Analyzer Pro - Professional Data Analysis Platform",
            self.styles['Normal']
        )
        story.append(footer)
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    
    def _export_to_excel(self, analyses: List[Dict]) -> bytes:
        """Export analyses to Excel format."""
        buffer = io.BytesIO()
        
        # Create DataFrame
        df_data = []
        for analysis in analyses:
            df_data.append({
                'Analysis ID': analysis.get('id', ''),
                'Filename': analysis.get('filename', ''),
                'Timestamp': analysis.get('timestamp', ''),
                'Question': analysis.get('question', ''),
                'Response': analysis.get('response', ''),
                'Execution Time (s)': analysis.get('execution_time', 0),
                'Subscription Tier': analysis.get('subscription_tier', 'free')
            })
        
        df = pd.DataFrame(df_data)
        
        # Write to Excel with formatting
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Analysis History', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Analysis History']
            
            # Format headers
            header_font = workbook.create_named_style("header_font")
            header_font.font.bold = True
            header_font.font.color = "FFFFFF"
            header_font.fill.start_color = "2E86C1"
            header_font.fill.end_color = "2E86C1"
            header_font.fill.fill_type = "solid"
            
            for cell in worksheet[1]:
                cell.style = header_font
            
            # Auto-adjust column widths
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def _export_to_csv(self, analyses: List[Dict]) -> bytes:
        """Export analyses to CSV format."""
        buffer = io.StringIO()
        
        if analyses:
            # Create DataFrame
            df_data = []
            for analysis in analyses:
                df_data.append({
                    'analysis_id': analysis.get('id', ''),
                    'filename': analysis.get('filename', ''),
                    'timestamp': analysis.get('timestamp', ''),
                    'question': analysis.get('question', ''),
                    'response': analysis.get('response', ''),
                    'execution_time_seconds': analysis.get('execution_time', 0),
                    'subscription_tier': analysis.get('subscription_tier', 'free')
                })
            
            df = pd.DataFrame(df_data)
            df.to_csv(buffer, index=False, encoding='utf-8')
        
        return buffer.getvalue().encode('utf-8')
    
    def _export_to_json(self, analyses: List[Dict]) -> bytes:
        """Export analyses to JSON format."""
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'total_analyses': len(analyses),
            'analyses': analyses
        }
        
        return json.dumps(export_data, indent=2, ensure_ascii=False).encode('utf-8')
    
    def get_filename(self, format: ExportFormat, analysis_id: Optional[str] = None) -> str:
        """Generate appropriate filename for export."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if analysis_id:
            base_name = f"analysis_{analysis_id}_{timestamp}"
        else:
            base_name = f"analyses_export_{timestamp}"
        
        return f"{base_name}.{format.value}"

# Global report exporter instance
report_exporter = ReportExporter()
