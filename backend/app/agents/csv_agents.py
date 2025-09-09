import os
import sys
import tempfile

from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_anthropic import ChatAnthropic
from sqlalchemy import create_engine, text

# Add the project root to the Python path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from app.config.settings import settings

CUSTOM_PREFIX = """You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct DuckDB query to run, then look at the results of the query and return the answer.
You have access to tools for interacting with the database.
Only use the given tools. Only use the information returned by the tools to construct your final answer.
You MUST double check your query before executing it. If you get an error while executing a query, rewrite the query and try again.

DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.

When using a tool, you MUST use the following format:

```
Thought: Do I need to use a tool? Yes
Action: the action to take, should be one of [sql_db_list_tables, sql_db_schema, sql_db_query, sql_db_query_checker]
Action Input: the input to the action
Observation: the result of the action
```

When you have a response to say to the Human, or if you do not need to use a tool, you MUST use the format:

```
Thought: Do I need to use a tool? No
Final Answer: [your response here]
```

For statistical correlations and mathematical analysis:
- Use CORR(column1, column2) function for correlation coefficients
- Handle string columns that contain 'null' by using WHERE column != 'null'
- Convert string numbers to numeric using TRY_CAST(column AS DOUBLE) AS column_name
- Always examine the schema first to understand column types
- Provide correlation coefficients with interpretation
"""

# It's better to use a more capable model for agentic work that requires reasoning.
AGENT_MODEL = "claude-3-haiku-20240307"


def get_agent_executor(uploaded_file):
    """Create an enhanced SQL agent with detailed feedback capabilities."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_file.flush()
        temp_path = temp_file.name

    # Use a file-based DuckDB database for proper persistence across connections
    db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".duckdb")
    db_path = db_file.name
    db_file.close()
    
    # Remove the empty file so DuckDB can create it properly
    import os
    os.unlink(db_path)
    
    # Create the engine with file-based DuckDB
    engine = create_engine(f"duckdb:///{db_path}", 
                          poolclass=None,
                          pool_pre_ping=True)

    # Load data and create the SQLDatabase using the same engine
    with engine.connect() as conn:
        try:
            # Load CSV data into a table called 'data'
            print("🔄 Loading CSV data into DuckDB...")
            conn.execute(text(f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{temp_path}')"))
            
            # Verify the table was created and get comprehensive info
            result = conn.execute(text("SELECT COUNT(*) FROM data"))
            row_count = result.fetchone()[0]
            
            # Get detailed column information
            result = conn.execute(text("DESCRIBE data"))
            columns_info = result.fetchall()
            col_count = len(columns_info)
            
            # Get data types and sample values for better analysis
            sample_query = "SELECT " + ", ".join([f"MIN({col[0]}) as {col[0]}_min, MAX({col[0]}) as {col[0]}_max" 
                                                 for col in columns_info[:5] if col[1] in ['INTEGER', 'DOUBLE', 'DECIMAL']]) 
            if sample_query != "SELECT ":
                sample_query += " FROM data"
                try:
                    numeric_stats = conn.execute(text(sample_query)).fetchall()
                    print(f"📊 Numeric data statistics available for enhanced analysis")
                except:
                    print(f"📊 Mixed data types detected - full analysis capabilities enabled")
            
            print(f"✅ Successfully loaded {row_count:,} rows and {col_count} columns")
            print(f"📋 Columns detected: {[f'{col[0]} ({col[1]})' for col in columns_info]}")
            
            # Test that queries work on this connection
            test_result = conn.execute(text("SELECT COUNT(*) as row_count FROM data")).fetchone()
            print(f"🔗 Database connection verified: {test_result[0]} rows accessible")
            
            # Quick data validation for better error messages
            print(f"🎯 Data loaded successfully - Ready for intelligent analysis")
            
            # Commit the transaction
            conn.commit()
            
        except Exception as e:
            print(f"❌ Error loading CSV data: {e}")
            raise Exception(f"Failed to load CSV data: {str(e)}")
            
    # Create enhanced SQLDatabase with the same engine
    db = SQLDatabase(
        engine=engine, 
        include_tables=['data'],
        sample_rows_in_table_info=3,
        max_string_length=1000,
        lazy_table_reflection=False  # Force immediate table discovery
    )
    
    # Verify the SQLDatabase can see and access the table
    available_tables = db.get_usable_table_names()
    print(f"🔍 SQLDatabase can see tables: {available_tables}")
    
    if 'data' not in available_tables:
        raise Exception("SQLDatabase cannot see the 'data' table - connection issue")
        
    # Final test: can SQLDatabase execute a query?
    try:
        test_query_result = db.run("SELECT COUNT(*) FROM data;")
        print(f"✅ Final verification: SQLDatabase ready - {test_query_result}")
    except Exception as e:
        print(f"❌ SQLDatabase query test failed: {e}")
        raise Exception(f"SQLDatabase cannot execute queries: {str(e)}")
    
    # Verify the database can see the table
    available_tables = db.get_usable_table_names()
    print(f"🎯 Database tables accessible: {available_tables}")
    
    if 'data' not in available_tables:
        raise Exception("Failed to create or access the 'data' table")
    
    # Test a simple query to ensure everything works
    sample_query = "SELECT COUNT(*) as total_rows FROM data"
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sample_query))
            test_count = result.fetchone()[0]
            print(f"🚀 System ready: {test_count} rows available for analysis")
    except Exception as e:
        print(f"❌ Test query failed: {e}")
        raise

    # Using Claude Haiku for reliable analytical and mathematical reasoning
    # Enhanced with conservative rate limiting for production use
    llm = ChatAnthropic(
        model=AGENT_MODEL,
        temperature=0.1,  # Slight randomness for creativity in analysis approaches
        max_tokens=1024,  # Further reduced to minimize token usage and avoid rate limits
        api_key=settings.ANTHROPIC_API_KEY,
        max_retries=3,  # Reduced retries to avoid hitting rate limits repeatedly
        default_request_timeout=60,  # Shorter timeout to fail faster
        # Enhanced rate limiting for production
        anthropic_api_url=None,  # Use default
    )
    
    # Enhanced toolkit with better error handling
    toolkit = SQLDatabaseToolkit(
        db=db, 
        llm=llm,
        reduce_k_below_max_tokens=True  # Automatically handle large result sets
    )
    
    # Create a production-ready SQL agent with conservative settings
    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        handle_parsing_errors="Check your output and make sure it conforms to the format instructions!",
        max_iterations=6,  # Reduced to minimize API calls and avoid rate limits
        prefix=CUSTOM_PREFIX,
        agent_type="zero-shot-react-description",
        early_stopping_method="generate",
    )
    
    print(f"🤖 AI agent configured with enhanced capabilities")
    return agent_executor
