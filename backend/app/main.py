import streamlit as st
import sys
import os
import time
import uuid
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add the project root to the Python path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import safe components first (non-blocking)
from app.core.file_processor import file_processor
from app.auth.supabase_client import supabase_client
from app.core.db_usage_tracker import db_usage_tracker as usage_tracker, SubscriptionTier
from app.auth.authentication import display_auth_form, handle_logout
from app.services.stripe_service import create_checkout_session
from app.core.analysis_history import analysis_history, ExportFormat
from app.services.export_service import report_exporter

# Initialize session state for guaranteed UI loading first
if 'ui_initialized' not in st.session_state:
    st.session_state.ui_initialized = True
    st.session_state.universal_agent = None
    st.session_state.agent_loading = False
    st.session_state.agent_error = None
    st.session_state.ai_available = False
    st.session_state.ai_load_attempted = False
    st.session_state.ai_load_time = None

# Guaranteed safe imports - NEVER import anthropic or AI models here
# DO NOT import: from app.agents.universal_agent import universal_agent

@st.cache_resource(show_spinner="🤖 Initializing AI Agent for the first time...")
def load_agent():
    """
    Load the UniversalInsightAgent using Streamlit's caching.
    This will run only once and the result will be cached.
    """
    # Ensure environment variables are loaded
    load_dotenv()
    from app.agents.universal_agent import universal_agent
    
    # Verify the agent is working before returning
    if not hasattr(universal_agent, 'claude_model') or universal_agent.claude_model is None:
        error_msg = getattr(universal_agent, 'model_error', 'Claude model failed to initialize')
        st.error(f"AI Model Error: {error_msg}")
        # Return None to indicate failure, cache will not store this
        return None
        
    return universal_agent

def is_ai_ready():
    """Check if AI is available without initializing it"""
    # This is tricky with cache_resource, as checking involves loading.
    # We'll rely on the UI to show the loading spinner.
    return True

# Initialize webhook service in production - TEMPORARILY DISABLED
try:
    # from app.core.webhook_server_integration import initialize_webhook_service, show_webhook_status
    WEBHOOK_AVAILABLE = False  # Temporarily disabled to prevent port conflicts
except ImportError:
    WEBHOOK_AVAILABLE = False

def display_analysis_history(user_id):
    """Display user's analysis history with export options."""
    st.markdown("# 📊 Analysis History")
    
    if st.button("← Back to Analysis", type="secondary"):
        st.session_state.show_history = False
        st.rerun()
    
    # Get user's analyses
    user_analyses = analysis_history.get_user_analyses(user_id)
    
    st.info(f"Found {len(user_analyses)} analyses for user ID: {user_id}")
    
    if not user_analyses:
        st.info("No analyses found. Start analyzing your data to build your history!")
        return
    
    # Statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Analyses", len(user_analyses))
    with col2:
        recent_count = len([a for a in user_analyses if (datetime.now() - datetime.fromisoformat(a['timestamp'])).days <= 7])
        st.metric("This Week", recent_count)
    with col3:
        avg_time = sum(a.get('execution_time', 0) for a in user_analyses) / len(user_analyses)
        st.metric("Avg. Time", f"{avg_time:.1f}s")
    
    st.markdown("---")
    
    # Display analyses in reverse chronological order
    for i, analysis in enumerate(reversed(user_analyses)):
        with st.expander(f"Analysis #{len(user_analyses)-i} - {analysis['filename']} ({analysis['timestamp'][:10]})"):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"**Question:** {analysis['question']}")
                st.markdown(f"**File:** {analysis['filename']}")
                st.markdown(f"**Date:** {analysis['timestamp'][:19].replace('T', ' ')}")
                st.markdown(f"**Execution Time:** {analysis.get('execution_time', 0):.2f}s")
                st.markdown(f"**Plan:** {analysis.get('subscription_tier', 'free').title()}")
                
            with col2:
                if st.button(f"📥 Export", key=f"export_{analysis['id']}"):
                    export_single_analysis(analysis)
            
            st.markdown("**Response:**")
            st.markdown(analysis['response'])

def display_export_interface(user_id):
    """Display export interface for analyses."""
    st.markdown("# 📥 Export Analysis Reports")
    
    if st.button("← Back to Analysis", type="secondary"):
        st.session_state.show_export = False
        st.rerun()
    
    # Get user's analyses
    user_analyses = analysis_history.get_user_analyses(user_id)
    
    if not user_analyses:
        st.info("No analyses to export. Start analyzing your data first!")
        return
    
    # Export options
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Export Format")
        export_format = st.selectbox(
            "Choose format:",
            options=[format.value for format in ExportFormat],
            format_func=lambda x: {
                "pdf": "📄 PDF Report",
                "excel": "📊 Excel Spreadsheet", 
                "csv": "📋 CSV File",
                "json": "🔧 JSON Data"
            }.get(x, x)
        )
    
    with col2:
        st.markdown("### Export Scope")
        export_scope = st.radio(
            "What to export:",
            ["All Analyses", "Recent (Last 7 days)", "Custom Selection"]
        )
    
    # Filter analyses based on scope
    if export_scope == "Recent (Last 7 days)":
        cutoff_date = datetime.now() - timedelta(days=7)
        analyses_to_export = [
            a for a in user_analyses 
            if datetime.fromisoformat(a['timestamp']) > cutoff_date
        ]
    elif export_scope == "Custom Selection":
        st.markdown("### Select Analyses")
        selected_analyses = []
        for analysis in reversed(user_analyses):
            if st.checkbox(
                f"{analysis['filename']} - {analysis['timestamp'][:10]}",
                key=f"select_{analysis['id']}"
            ):
                selected_analyses.append(analysis)
        analyses_to_export = selected_analyses
    else:
        analyses_to_export = user_analyses
    
    st.markdown(f"**Selected:** {len(analyses_to_export)} analyses")
    
    # Export button
    if st.button("📥 Generate Export", type="primary", disabled=len(analyses_to_export) == 0):
        if len(analyses_to_export) > 0:
            try:
                with st.spinner("Generating export..."):
                    format_enum = ExportFormat(export_format)
                    
                    if len(analyses_to_export) == 1:
                        file_content = report_exporter.export_single_analysis(analyses_to_export[0], format_enum)
                    else:
                        file_content = report_exporter.export_multiple_analyses(analyses_to_export, format_enum)
                    
                    filename = report_exporter.get_filename(format_enum)
                    
                    st.download_button(
                        label=f"📥 Download {export_format.upper()} Report",
                        data=file_content,
                        file_name=filename,
                        mime=get_mime_type(format_enum)
                    )
                    
                st.success(f"✅ Export ready! {len(analyses_to_export)} analyses exported to {export_format.upper()}")
                
            except Exception as e:
                st.error(f"Export failed: {e}")

def export_single_analysis(analysis):
    """Quick export for a single analysis."""
    try:
        # Default to PDF for single exports
        format_enum = ExportFormat.PDF
        file_content = report_exporter.export_single_analysis(analysis, format_enum)
        filename = report_exporter.get_filename(format_enum, analysis['id'])
        
        st.download_button(
            label="📄 Download PDF Report",
            data=file_content,
            file_name=filename,
            mime="application/pdf",
            key=f"download_{analysis['id']}"
        )
        
    except Exception as e:
        st.error(f"Export failed: {e}")

def get_mime_type(format: ExportFormat) -> str:
    """Get MIME type for export format."""
    mime_types = {
        ExportFormat.PDF: "application/pdf",
        ExportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ExportFormat.CSV: "text/csv",
        ExportFormat.JSON: "application/json"
    }
    return mime_types.get(format, "application/octet-stream")

def get_user_id():
    """
    Get user ID from session state with safeguards.
    Returns user ID if available, otherwise None.
    """
    # Check if we've explicitly authenticated this session
    if 'authenticated' in st.session_state and st.session_state.authenticated:
        if 'user' in st.session_state and st.session_state.user and hasattr(st.session_state.user, 'id'):
            return st.session_state.user.id
    
    # First check for fallback mode
    if os.environ.get('FALLBACK_TO_TEST_USER', 'false').lower() == 'true':
        if 'user' not in st.session_state or not st.session_state.user:
            # Create fallback test user
            test_user = type('TestUser', (), {
                'id': 'fallback-test-user',
                'email': 'fallback-test@example.com',
                'user_metadata': {'name': 'Fallback Test User'}
            })()
            st.session_state['user'] = test_user
            st.session_state['authenticated'] = True  # Mark as authenticated
        return st.session_state.user.id
    
    # Only return user ID if user is already in session state
    if 'user' in st.session_state and st.session_state.user and hasattr(st.session_state.user, 'id'):
        return st.session_state.user.id
    
    # If no user in session, try to get session silently (don't show errors)
    try:
        if supabase_client:
            session = supabase_client.auth.get_session()
            if session and session.user:
                st.session_state['user'] = session.user
                st.session_state['authenticated'] = True  # Mark as authenticated
                return session.user.id
    except Exception:
        # Silent failure - let the authentication form handle it
        pass
    
    return None

# Callback class for real-time agent feedback
class RealTimeCallback:
    def __init__(self, status_callback):
        self.status_callback = status_callback
        self.step_count = 0
    
    def on_llm_start(self, *args, **kwargs):
        self.step_count += 1
        if self.status_callback:
            self.status_callback(f"🧠 AI thinking... (Step {self.step_count})")
    
    def on_tool_start(self, *args, **kwargs):
        if self.status_callback:
            tool_name = kwargs.get('name', 'unknown')
            if 'sql' in tool_name.lower():
                self.status_callback(f"🔍 Executing SQL query...")
            elif 'schema' in tool_name.lower():
                self.status_callback(f"📋 Examining data structure...")
            else:
                self.status_callback(f"⚙️ Using tool: {tool_name}")
    
    def on_tool_end(self, *args, **kwargs):
        if self.status_callback:
            self.status_callback(f"✅ Tool execution completed")
    
    def on_agent_action(self, *args, **kwargs):
        if self.status_callback:
            self.status_callback(f"🤖 Agent taking action...")
    
    def on_agent_finish(self, *args, **kwargs):
        if self.status_callback:
            self.status_callback(f"🎯 Analysis complete!")

def display_usage_sidebar(user_id):
    """Display usage information and upgrade options in sidebar."""
    if not user_id:
        return
    
    # Show AI status in the sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🤖 AI Status")
    
    # Display AI status dynamically
    try:
        # Attempt to get the agent from cache. This will trigger loading on first run.
        agent = load_agent()
        if agent:
            st.sidebar.success("✅ AI Agent: **Ready**")
        else:
            # This case is hit if load_agent returns None due to an error
            st.sidebar.error("❌ AI Agent: **Error**")
            st.sidebar.info("Please check your ANTHROPIC_API_KEY in the .env file.")
            
    except Exception as e:
        # This catches errors during the initial loading spinner
        st.sidebar.error("❌ AI Agent: **Failed to Load**")
        with st.sidebar.expander("See error details"):
            st.code(str(e))
        
    tier_info = usage_tracker.get_user_tier_info(user_id)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Your Usage")
    
    # Display current tier
    tier_color = {"free": "🆓", "pro": "⭐", "enterprise": "💎", "admin": "👑"}
    tier_name = tier_info['current_tier'].title()
    tier_icon = tier_color.get(tier_info['current_tier'], "📊")
    
    st.sidebar.markdown(f"**{tier_icon} {tier_name} Plan**")
    
    # Special display for admin users
    if tier_info['current_tier'] == 'admin':
        st.sidebar.success("👑 **Admin Access** - Unlimited Everything!")
        st.sidebar.markdown("**Today:** ♾️ Unlimited analyses")
        st.sidebar.markdown("**File Limit:** 1GB")
        st.sidebar.markdown("**Features:** All Advanced")
        st.sidebar.markdown(f"**Total:** {tier_info['total_analyses']} analyses")
        return  # Skip the rest for admin users
    
    # Display usage stats for non-admin users
    if tier_info['daily_analyses_limit'] > 0:
        remaining = tier_info['analyses_remaining']
        used = tier_info['daily_analyses_used']
        limit = tier_info['daily_analyses_limit']
        
        st.sidebar.progress(used / limit if limit > 0 else 0)
        st.sidebar.markdown(f"**Today:** {used}/{limit} analyses")
        
        if remaining <= 1 and remaining >= 0:
            st.sidebar.warning(f"⚠️ Only {remaining} analysis remaining today!")
    else:
        st.sidebar.markdown("**Today:** ♾️ Unlimited analyses")
    
    st.sidebar.markdown(f"**Total:** {tier_info['total_analyses']} analyses")
    
    # Always show upgrade option for free users
    if tier_info['current_tier'] == 'free':
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🚀 Upgrade to Pro")
        st.sidebar.info("Unlock unlimited analyses, larger files, and advanced features!")
        
        if st.sidebar.button("Upgrade Now 💳"):
            checkout_url = create_checkout_session(user_id, st.session_state.user.email)
            if checkout_url:
                st.sidebar.markdown(f"[**Click here to upgrade to Pro**]({checkout_url})", unsafe_allow_html=True)
                st.sidebar.success("Redirecting to payment...")
            else:
                st.sidebar.error("Could not create payment session. Please try again later.")
    
    # Also show upgrade prompt if usage is high
    should_upgrade, reason = usage_tracker.should_show_upgrade_prompt(user_id)
    if should_upgrade and tier_info['current_tier'] == 'free':
        st.sidebar.markdown("---")
        st.sidebar.warning(f"💡 **Usage Alert:** {reason}")
        st.sidebar.markdown("Consider upgrading for unlimited access!")

def check_file_size_limits(uploaded_file, user_tier_info):
    """Check if uploaded file meets tier size limits."""
    if uploaded_file is None:
        return True, ""
    
    file_size_mb = uploaded_file.size / (1024 * 1024)
    max_size = user_tier_info['max_file_size_mb']
    
    if file_size_mb > max_size:
        return False, f"File size ({file_size_mb:.1f}MB) exceeds {user_tier_info['current_tier'].title()} plan limit of {max_size}MB"
    
    return True, ""

def execute_with_rate_limiting(agent_executor, prompt, max_retries=2, status_callback=None):
    """Execute agent with exponential backoff and real-time feedback."""
    for attempt in range(max_retries):
        try:
            if status_callback:
                status_callback(f"🤖 Initializing AI analysis (Attempt {attempt + 1}/{max_retries})...")
            
            # Execute with enhanced monitoring
            import sys
            from io import StringIO
            
            # Capture output for real-time feedback
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                response = agent_executor.invoke({"input": prompt})
                
                # Parse captured output to show SQL queries and reasoning
                output_lines = captured_output.getvalue().split('\n')
                for line in output_lines:
                    if status_callback and line.strip():
                        if 'SELECT' in line.upper() or 'FROM' in line.upper():
                            status_callback(f"💾 Executing SQL: {line.strip()[:50]}...")
                        elif 'Thought:' in line:
                            status_callback(f"🧠 AI thinking: {line.replace('Thought:', '').strip()[:50]}...")
                        elif 'Action:' in line:
                            status_callback(f"⚡ AI action: {line.replace('Action:', '').strip()}")
                        elif 'Observation:' in line:
                            status_callback(f"👀 Processing results...")
                
            finally:
                sys.stdout = old_stdout
            
            return response, None
        
        # Handle various API errors - no imports needed, using generic handling    
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if it's a rate limit error based on message
            if "rate limit" in error_str or "too many requests" in error_str:
                wait_time = (2 ** attempt) * 10  # 10, 20 seconds (more conservative)
                if attempt < max_retries - 1:
                    if status_callback:
                        status_callback(f"⏳ Rate limit reached - waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    return None, f"Rate limit exceeded after {max_retries} attempts. Please try again in a few minutes.\n\nFor Production Use: Consider upgrading to a higher tier API plan for complex mathematical analysis at scale."
            else:
                # Handle all other exceptions
                return None, f"AI Error: {str(e)}"
    
    return None, "Maximum retries exceeded"

def show_realtime_analysis_feedback(progress_container, status_container, prompt, agent_executor):
    """Show detailed real-time feedback during analysis with AI reasoning steps."""
    
    # Create dynamic status components
    progress_bar = progress_container.progress(0)
    status_text = status_container.empty()
    detail_text = status_container.empty()
    reasoning_text = status_container.empty()
    
    # Phase 1: Initialization
    status_text.markdown("### 🚀 **Analysis Starting**")
    detail_text.info("🔍 **Phase 1:** Preparing analysis environment...")
    progress_bar.progress(0.05)
    time.sleep(0.5)
    
    # Phase 2: Question Understanding
    status_text.markdown("### 🧠 **Understanding Your Question**")
    detail_text.info("� **Phase 2:** AI is parsing your question...")
    reasoning_text.markdown(f"🤔 **Your Question:** *{prompt}*")
    progress_bar.progress(0.15)
    time.sleep(0.4)
    
    detail_text.info("🎯 **Phase 2:** Determining analysis strategy...")
    progress_bar.progress(0.25)
    time.sleep(0.3)
    
    # Phase 3: Data Exploration
    status_text.markdown("### 📊 **Data Exploration**")
    detail_text.info("🔎 **Phase 3:** Examining data structure and schema...")
    reasoning_text.markdown("🔍 **AI Reasoning:** *Checking column types and relationships...*")
    progress_bar.progress(0.35)
    time.sleep(0.4)
    
    detail_text.info("� **Phase 3:** Understanding data patterns...")
    reasoning_text.markdown("🧮 **AI Reasoning:** *Analyzing data distribution and quality...*")
    progress_bar.progress(0.45)
    time.sleep(0.3)
    
    # Phase 4: Query Planning
    status_text.markdown("### 🛠️ **Query Planning**")
    detail_text.info("📝 **Phase 4:** AI designing SQL queries...")
    reasoning_text.markdown("🧠 **AI Reasoning:** *Planning optimal query strategy...*")
    progress_bar.progress(0.55)
    time.sleep(0.4)
    
    # Phase 5: Execution with enhanced callback for updates
    status_text.markdown("### ⚡ **Executing Analysis**")
    
    # Real-time callback for agent steps
    current_step = {"count": 0}
    
    def status_callback(message):
        current_step["count"] += 1
        detail_text.info(f"🔄 **Phase 5:** {message}")
        
        # Show different reasoning based on the step
        if "thinking" in message.lower():
            reasoning_text.markdown("🤖 **AI Reasoning:** *Processing your question and formulating approach...*")
        elif "sql" in message.lower():
            reasoning_text.markdown("💾 **AI Reasoning:** *Executing database queries to extract insights...*")
        elif "schema" in message.lower():
            reasoning_text.markdown("📊 **AI Reasoning:** *Analyzing data structure for optimal query design...*")
        elif "tool" in message.lower():
            reasoning_text.markdown("⚙️ **AI Reasoning:** *Using specialized tools for data analysis...*")
        else:
            reasoning_text.markdown(f"🔄 **AI Reasoning:** *{message}*")
        
        # Dynamic progress based on steps
        step_progress = min(0.60 + (current_step["count"] * 0.03), 0.80)
        progress_bar.progress(step_progress)
    
    detail_text.info("⚡ **Phase 5:** Executing intelligent queries...")
    reasoning_text.markdown("🚀 **AI Reasoning:** *Beginning analysis execution...*")
    progress_bar.progress(0.60)
    
    # Execute the analysis with enhanced monitoring
    try:
        response, error = execute_with_rate_limiting(agent_executor, prompt, status_callback=status_callback)
        
        if error:
            # Show error feedback
            status_text.markdown("### ❌ **Analysis Error**")
            detail_text.error(f"💥 **Error:** {error}")
            reasoning_text.markdown("🚫 **AI Status:** *Analysis interrupted due to error*")
            progress_bar.progress(1.0)
            return None, error
            
    except Exception as e:
        status_text.markdown("### ❌ **Unexpected Error**")
        detail_text.error(f"💥 **Error:** {str(e)}")
        reasoning_text.markdown("🚫 **AI Status:** *Unexpected error occurred*")
        progress_bar.progress(1.0)
        return None, str(e)
    
    # Phase 6: Results Processing
    status_text.markdown("### 📈 **Generating Insights**")
    detail_text.info("📊 **Phase 6:** Processing results and generating insights...")
    reasoning_text.markdown("🎯 **AI Reasoning:** *Interpreting results and formulating insights...*")
    progress_bar.progress(0.85)
    time.sleep(0.3)
    
    detail_text.info("� **Phase 6:** Formatting professional analysis report...")
    reasoning_text.markdown("📝 **AI Reasoning:** *Structuring findings into professional format...*")
    progress_bar.progress(0.95)
    time.sleep(0.3)
    
    # Phase 7: Completion
    status_text.markdown("### ✅ **Analysis Complete**")
    detail_text.success("🎉 **Phase 7:** Professional analysis ready!")
    reasoning_text.markdown("🏆 **AI Status:** *Analysis successfully completed with insights!*")
    progress_bar.progress(1.0)
    time.sleep(0.2)
    
    return response, None

st.set_page_config(
    page_title="Universal Insight Engine", 
    page_icon="🔍", 
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/judeszn/csv-analyzer-pro',
        'Report a bug': 'https://github.com/judeszn/csv-analyzer-pro/issues',
        'About': "# Universal Insight Engine\nAI-Powered Analysis for CSV, PDF, Text & Images"
    }
)

def main():
    # Start by initializing session state first to make sure UI loads
    # regardless of authentication state
    if "ui_loaded" not in st.session_state:
        st.session_state.ui_loaded = True
        st.session_state.auth_loading = False
        st.session_state.auth_error = None
        st.session_state.processed_content = None
        st.session_state.agent_executor = None
        st.session_state.messages = []
        st.session_state.uploaded_file_name = None
        st.session_state.file_type = None
    
    # Custom CSS for better display
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 100%;
    }
    .stApp > header {
        background-color: transparent;
    }
    .stApp {
        margin: 0;
        padding: 0;
    }
    div[data-testid="stSidebar"] > div:first-child {
        width: 300px;
    }
    div[data-testid="stSidebar"] > div:first-child {
        margin-left: -300px;
    }
    .css-1d391kg {
        padding-top: 1rem;
    }
    .stMarkdown {
        width: 100%;
    }
    .element-container {
        width: 100%;
    }
    .stSelectbox, .stFileUploader, .stButton {
        width: 100%;
    }
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("Universal Insight Engine")
    # Removed subtitle to customize the presentation

    # Initialize webhook service in production - TEMPORARILY DISABLED
    if WEBHOOK_AVAILABLE:
        # initialize_webhook_service()  # Temporarily disabled
        pass

    # Try to get user ID from session
    user_id = get_user_id()
    
    # Main application logic
    if user_id:
        # Sidebar for file upload and usage info
        with st.sidebar:
            if 'user' in st.session_state and hasattr(st.session_state.user, 'email'):
                user_email = st.session_state.user.email
                
                # Show welcome message without mentioning fallback mode
                if user_email == 'fallback-test@example.com':
                    st.markdown("**Welcome!**")
                else:
                    st.markdown(f"**Welcome,**\n`{user_email}`")
                
                # Special admin welcome message
                tier_info = usage_tracker.get_user_tier_info(user_id)
                if tier_info.get('current_tier') == 'admin':
                    st.success("👑 **Admin Access Active**")
            
            st.markdown("### 📁 Upload Your File")
            
            # Mobile-friendly file upload with guidance
            st.markdown("""
            <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
            📱 <strong>Mobile Users</strong>: If you don't see PDF/TXT options, this is a browser limitation. 
            You can still upload images, or try opening this page in Chrome/Safari on desktop.
            </div>
            """, unsafe_allow_html=True)
            
            uploaded_file = st.file_uploader(
                "Choose your file to analyze",
                type=["csv", "pdf", "txt", "jpg", "jpeg", "png", "webp", "gif", "bmp"],
                help="📊 CSV • 📄 PDF • 📝 TXT • 🖼️ Images (JPG, PNG, WEBP, etc.)",
                accept_multiple_files=False
            )
            
            # Show supported file types
            with st.expander("📋 Supported File Types", expanded=False):
                st.markdown("""
                **📊 CSV Files**: Data analysis, statistics, visualization  
                **📄 PDF Documents**: Text extraction and analysis  
                **📝 Text Files**: Content analysis and insights  
                **🖼️ Images**: Charts, graphs, screenshots, documents  
                
                *Maximum file sizes: CSV (100MB), PDF (50MB), Text (10MB), Images (10MB)*
                """)
            
            # File type detection and info
            if uploaded_file:
                file_type = file_processor.get_file_type(uploaded_file.name)
                file_size_mb = uploaded_file.size / (1024 * 1024)
                
                # Display file info
                type_icons = {
                    'csv': '📊',
                    'pdf': '📄', 
                    'text': '📝',
                    'image': '🖼️',
                    'unknown': '❓'
                }
                
                st.info(f"""
                **File Selected**: {type_icons.get(file_type, '❓')} {uploaded_file.name}  
                **Type**: {file_type.upper()}  
                **Size**: {file_size_mb:.2f} MB
                """)
                
                # Show file type specific capabilities
                if file_type == 'csv':
                    st.success("🧮 **Ready for**: Statistical analysis, data exploration, SQL queries, charts")
                elif file_type == 'pdf':
                    st.success("📖 **Ready for**: Text extraction, content analysis, document insights")
                elif file_type == 'text':
                    st.success("✍️ **Ready for**: Content analysis, text mining, language insights")
                elif file_type == 'image':
                    st.success("👁️ **Ready for**: Visual analysis, text extraction from images, chart interpretation")
                else:
                    st.error("❌ **Unsupported file type**. Please upload a CSV, PDF, TXT, or image file.")
            
            # Display usage information and logout button
            display_usage_sidebar(user_id)
            
            # Analysis History Section
            st.markdown("---")
            st.markdown("### 📊 Analysis History")
            
            if st.button("📋 View History", use_container_width=True):
                st.session_state.show_history = True
                st.rerun()
                
            if st.button("📥 Export Reports", use_container_width=True):
                st.session_state.show_export = True
                st.rerun()
                
            handle_logout()

        # Check for history/export display requests
        if st.session_state.get('show_history', False):
            display_analysis_history(user_id)
            return
        
        if st.session_state.get('show_export', False):
            display_export_interface(user_id)
            return
    
        # Check usage limits before allowing analysis
        if uploaded_file:
            user_tier_info = usage_tracker.get_user_tier_info(user_id)
            
            # Check file size limits based on file type
            file_type = file_processor.get_file_type(uploaded_file.name)
            is_valid, validation_error = file_processor.validate_file(uploaded_file, file_type)
            
            if not is_valid:
                st.error(f"🚫 **File Validation Error**: {validation_error}")
                if "too large" in validation_error.lower():
                    st.info("💡 **Upgrade to Pro** for larger file support or **Enterprise** for maximum file sizes")
                uploaded_file = None

            # If no file is uploaded, clear all related session state
            if not uploaded_file:
                st.session_state.processed_content = None
                st.session_state.agent_executor = None
                st.session_state.messages = []
                st.session_state.uploaded_file_name = None
                st.session_state.file_type = None
                
            # If a file is uploaded and it's a new file or there's no processed content, initialize
            elif (st.session_state.processed_content is None or 
                  st.session_state.uploaded_file_name != uploaded_file.name):
                
                st.session_state.uploaded_file_name = uploaded_file.name
                st.session_state.file_type = file_type
                st.session_state.messages = [] # Reset chat history
                
                # Enhanced file processing with real-time feedback
                with st.status("🔧 **Processing File with Universal Engine**", expanded=True) as status:
                    try:
                        # Step 1: File type detection and validation
                        st.write(f"📁 **Step 1:** Analyzing file type: {file_type.upper()}")
                        file_size_mb = uploaded_file.size / (1024 * 1024)
                        st.write(f"   ✅ File: `{uploaded_file.name}` ({file_size_mb:.2f} MB)")
                        time.sleep(0.2)
                        
                        # Step 2: File processing based on type
                        st.write(f"⚙️ **Step 2:** Processing {file_type} content...")
                        
                        if file_type == 'csv':
                            st.write("   � Loading CSV data and analyzing structure...")
                        elif file_type == 'pdf':
                            st.write("   📄 Extracting text from PDF document...")
                        elif file_type == 'text':
                            st.write("   📝 Reading and processing text content...")
                        elif file_type == 'image':
                            st.write("   🖼️ Processing image and preparing for vision analysis...")
                        
                        time.sleep(0.3)
                        
                        # Actually process the file with robust error handling
                        try:
                            processed_content = file_processor.process_file(uploaded_file)
                            st.session_state.processed_content = processed_content
                        except Exception as e:
                            st.error(f"⚠️ Error processing file: {str(e)}")
                            # Add detailed error logging
                            import traceback
                            st.write(f"```\n{traceback.format_exc()}\n```")
                            # Clear status
                            status.update(label="❌ File Processing Failed", state="error", expanded=True)
                            return
                        
                        # Step 3: File processing complete - no AI loading yet
                        st.write("✅ **Step 3:** File processed and ready for analysis!")
                        st.write("   📁 File uploaded and validated successfully")
                        
                        # Step 4: AI agent preparation - DOES NOT ACTUALLY LOAD AI YET
                        st.write("ℹ️ **Step 4:** AI Agent Status...")
                        st.write("   🧠 AI will initialize in background when you request analysis")
                        st.write("   ⚡ This prevents UI blocking during startup")
                        time.sleep(0.2)
                        time.sleep(0.2)
                        
                        # Final success
                        st.write("🎉 **Complete:** File ready for universal analysis!")
                        status.update(label="✅ **Universal Engine Ready**", state="complete", expanded=False)
                        
                        # Show file-specific success message
                        if file_type == 'csv':
                            st.success(f"📊 **CSV Ready**: `{uploaded_file.name}` loaded with {processed_content['metadata']['rows']} rows and {processed_content['metadata']['columns']} columns")
                        elif file_type == 'pdf':
                            st.success(f"📄 **PDF Ready**: `{uploaded_file.name}` processed - {processed_content['metadata']['pages']} pages, {processed_content['metadata']['word_count']} words")
                        elif file_type == 'text':
                            st.success(f"📝 **Text Ready**: `{uploaded_file.name}` loaded - {processed_content['metadata']['word_count']} words")
                        elif file_type == 'image':
                            st.success(f"🖼️ **Image Ready**: `{uploaded_file.name}` processed - {processed_content['metadata']['width']}x{processed_content['metadata']['height']} pixels")
                        
                        st.info("💬 **Ask any question about your content to get AI-powered insights!**")
                        
                    except Exception as e:
                        st.write(f"❌ **Error:** {e}")
                        status.update(label="❌ **Processing Failed**", state="error", expanded=True)
                        st.error(f"🚫 **Processing Failed:** {e}")
                        st.session_state.processed_content = None
                        st.session_state.uploaded_file_name = None
                        st.session_state.file_type = None

        # Display chat messages from history
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Main chat interface with usage tracking
        if st.session_state.processed_content:
            # Check usage limits before each analysis
            can_analyze, reason, usage_info = usage_tracker.can_perform_analysis(user_id)
            
            if not can_analyze:
                st.warning(f"🚫 **Analysis Limit Reached**: {reason}")
                
                # Safe access to current_tier with fallback
                current_tier = usage_info.get('current_tier', 'free') if usage_info else 'free'
                
                if current_tier == 'free':
                    col1, col2 = st.columns(2)
                    with col1:
                        st.info("🆓 **Free Plan Limits:**\n- 5 analyses per day\n- Limited file types")
                    with col2:
                        st.success("⭐ **Pro Plan Benefits:**\n- ♾️ Unlimited analyses\n- All file types\n- Advanced features")
                    
                    st.markdown("### 🚀 Ready to Upgrade?")
                    if st.button("Upgrade to Pro 💳", type="primary"):
                        if 'user' in st.session_state and hasattr(st.session_state.user, 'email'):
                            checkout_url = create_checkout_session(user_id, st.session_state.user.email)
                            if checkout_url:
                                st.markdown(f"[**Click here to upgrade to Pro**]({checkout_url})", unsafe_allow_html=True)
                                st.success("Redirecting to payment...")
                            else:
                                st.error("Could not create payment session. Please try again later.")
                        else:
                            st.error("User session error. Please refresh and try again.")
            
            # Show usage status and file info
            if usage_info and 'analyses_remaining' in usage_info and usage_info['analyses_remaining'] >= 0:
                remaining = usage_info['analyses_remaining']
                if remaining <= 1:
                    st.info(f"⚠️ You have {remaining} analysis remaining today")
            
            # Show current file info
            if st.session_state.processed_content:
                # Show file info without requiring AI initialization
                file_name = st.session_state.uploaded_file_name or "uploaded file"
                file_type = st.session_state.file_type or "unknown"
                
                type_icons = {
                    'csv': '📊',
                    'pdf': '�', 
                    'text': '📝',
                    'image': '🖼️',
                    'unknown': '📄'
                }
                
                icon = type_icons.get(file_type, '📄')
                st.info(f"{icon} **Current File**: {file_name} ({file_type.upper()}) - Ready for analysis")
            
            # Chat interface
            if prompt := st.chat_input(f"Ask about your {st.session_state.file_type} content...", disabled=not can_analyze):
                if not can_analyze:
                    st.error("Please upgrade to continue analyzing data.")
                    st.stop()
                
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                with st.chat_message("assistant"):
                    # Create enhanced real-time analysis display
                    st.markdown("### 🧠 **Universal AI Analysis in Progress**")
                    
                    # Create containers for real-time feedback
                    main_container = st.container()
                    progress_container = main_container.container()
                    status_container = main_container.container()
                    results_container = st.container()
                    
                    try:
                        # Show analysis type
                        file_type = st.session_state.file_type
                        type_messages = {
                            'csv': "📊 Performing statistical analysis on your data...",
                            'pdf': "📄 Analyzing document content and extracting insights...",
                            'text': "📝 Processing text content for comprehensive analysis...",
                            'image': "🖼️ Using AI vision to analyze your image content..."
                        }
                        
                        status_container.info(type_messages.get(file_type, "🔍 Analyzing content..."))
                        
                        # Execute analysis with the universal agent
                        start_time = time.time()
                        
                        # Load the agent using the cached function
                        agent = load_agent()
                        
                        if agent is None:
                            # Agent failed to load, error is shown by load_agent
                            response = "Error: AI Agent failed to initialize. Please check your API key and environment settings."
                            status_container.error("AI Agent could not be loaded.")
                        else:
                            # Agent is ready - proceed with analysis
                            try:
                                response = agent.analyze_content(st.session_state.processed_content, prompt)
                            except Exception as e:
                                response = f"Error: Analysis failed - {str(e)}"
                                status_container.error(f"⚠️ Analysis error: {str(e)}")
                        
                        execution_time = time.time() - start_time
                        
                        if response and not response.startswith("Error"):
                            # Clear progress display
                            main_container.empty()
                            
                            # Record successful analysis
                            usage_stats = usage_tracker.record_analysis(user_id, file_type)
                            
                            # Save analysis to history
                            # Ensure we have valid file content for hashing
                            file_content_for_hash = st.session_state.processed_content.get('raw_content')
                            if file_content_for_hash is None:
                                # Fallback: use the filename as a simple identifier
                                file_content_for_hash = st.session_state.uploaded_file_name.encode('utf-8')
                            
                            analysis_history.save_analysis(
                                user_id=user_id,
                                filename=st.session_state.uploaded_file_name,
                                question=prompt,
                                response=response,
                                file_content=file_content_for_hash,
                                execution_time=execution_time,
                                subscription_tier=usage_stats.get('current_tier', 'free')
                            )
                            
                            # Display results with file-type specific formatting
                            file_icons = {
                                'csv': '📊',
                                'pdf': '📄',
                                'text': '📝', 
                                'image': '🖼️'
                            }
                            
                            results_container.markdown(f"""
### {file_icons.get(file_type, '�')} **Universal AI Analysis Results**

{response}

---
*🧠 Powered by Claude Haiku • {file_type.upper()} Analysis • {execution_time:.2f}s processing time*
""")
                            
                            st.session_state.messages.append({"role": "assistant", "content": response})
                            
                            # Show updated usage info
                            remaining = usage_stats.get('analyses_remaining', -1)
                            if remaining >= 0 and remaining <= 1:
                                results_container.info(f"ℹ️ You have {remaining} analysis remaining today")
                        else:
                            # Clear progress and show error
                            main_container.empty()
                            error_msg = response if response else "Analysis failed"
                            results_container.error(f"⚠️ **Analysis Error:** {error_msg}")
                            st.session_state.messages.append({"role": "assistant", "content": f"❌ Analysis failed: {error_msg}"})
                        
                    except Exception as e:
                        # Fallback for any unexpected errors
                        main_container.empty()
                        error_message = f"⚠️ **Unexpected Error:** {e}\n\nPlease try again or contact support if the issue persists."
                        results_container.error(error_message)
                        st.session_state.messages.append({"role": "assistant", "content": error_message})
        else:
            st.info("👆 **Please upload a file to start universal AI analysis**")
            
            # Add helpful examples for different file types
            st.markdown("""
            ### 🎯 **What You Can Ask Based on File Type:**
            
            **📊 CSV Files:**
            - *"What are the key insights from this dataset?"*
            - *"Show me statistical correlations between variables"*
            - *"Identify outliers and anomalies in the data"*
            - *"What are the main patterns and trends?"*
            
            **📄 PDF Documents:**
            - *"Summarize the main points of this document"*
            - *"What are the key findings mentioned?"*
            - *"Extract important data or statistics"*
            - *"Analyze the arguments presented"*
            
            **📝 Text Files:**
            - *"What is the sentiment of this text?"*
            - *"Identify the main themes"*
            - *"Extract key information"*
            - *"Summarize the content"*
            
            **🖼️ Images:**
            - *"What data does this chart show?"*
            - *"Extract text from this screenshot"*
            - *"Analyze this graph or diagram"*
            - *"What information can you see in this image?"*
            
            ---
            **🚀 Universal Engine**: One interface for all your analysis needs!
            """)
    else:
        # Show authentication form if not logged in
        try:
            with st.spinner("Loading authentication..."):
                user = display_auth_form()
        except Exception as e:
            st.error(f"Authentication service error: {str(e)}. Please try refreshing.")
            user = None
            
        if not user:
            st.markdown("---")
            st.info("Please log in or sign up to access the Universal Insight Engine.")
            
            # Show pricing information
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("""
                ### 🆓 **Free Plan**
                - **1 analysis per day**
                - **CSV**: Up to 10MB
                - **PDF**: Up to 5MB  
                - **Text**: Up to 1MB
                - **Images**: Up to 5MB
                - Basic insights
                
                *Perfect for trying out the platform*
                """)
            
            with col2:
                st.markdown("""
                ### ⭐ **Pro Plan**
                - **♾️ Unlimited analyses**
                - **CSV**: Up to 100MB
                - **PDF**: Up to 50MB
                - **Text**: Up to 10MB
                - **Images**: Up to 10MB
                - Advanced features
                
                *Ideal for professionals*
                """)
            
            with col3:
                st.markdown("""
                ### 💎 **Enterprise Plan**
                - **♾️ Unlimited analyses**
                - **All file types**: Up to 500MB
                - Custom integrations
                - Dedicated support
                - API access
                - Batch processing
                
                *Built for organizations*
                """)

if __name__ == "__main__":
    main()
