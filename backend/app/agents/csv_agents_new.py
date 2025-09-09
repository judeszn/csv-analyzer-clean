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

CUSTOM_PREFIX = """You are a data analyst agent that MUST use SQL database tools for all analysis. Never provide theoretical answers.

**CRITICAL RULE: You MUST execute actual SQL queries using the sql_db_query tool. Never give hypothetical responses.**

**Required Process:**
1. Use sql_db_schema to examine data structure
2. Use sql_db_query to execute actual SQL queries
3. Present only real query results, never make up data

**For Statistical Correlations:**
- First examine sample data with LIMIT queries
- Convert string columns to numeric using CAST and REPLACE functions
- Use CORR() function for actual correlation calculations
- Handle data cleaning (remove currency symbols, commas, etc.)

**Example Query Structure:**
```sql
SELECT CORR(
  CAST(REPLACE(REPLACE(column1, '₹', ''), ',', '') AS DOUBLE),
  CAST(REPLACE(REPLACE(column2, '₹', ''), ',', '') AS DOUBLE)
) AS correlation_value
FROM data WHERE column1 != '' AND column2 != '';
```

**Communication:**
- Always execute queries using tools
- Show actual results, not hypothetical numbers
- Be concise but factual
- If queries fail, debug and retry with corrected SQL
"""

# Use Claude Haiku for reliable analytical reasoning
AGENT_MODEL = "claude-3-haiku-20240307"


def get_agent_executor(uploaded_file):
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
                numeric_stats = conn.execute(text(sample_query)).fetchall()
            
            print(f"✓ Successfully loaded {row_count:,} rows and {col_count} columns")
            print(f"✓ Columns: {[f'{col[0]} ({col[1]})' for col in columns_info]}")
            
            # Test that queries work on this connection
            test_result = conn.execute(text("SELECT COUNT(*) as row_count FROM data")).fetchone()
            print(f"✓ Connection test successful: {test_result[0]} rows accessible")
            
            # Quick data validation
            print(f"✓ Data loaded successfully - Ready for advanced mathematical analysis")
            
            # Commit the transaction
            conn.commit()
            
        except Exception as e:
            print(f"✗ Error loading CSV data: {e}")
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
    print(f"✓ SQLDatabase can see tables: {available_tables}")
    
    if 'data' not in available_tables:
        raise Exception("SQLDatabase cannot see the 'data' table - connection issue")
        
    # Final test: can SQLDatabase execute a query?
    try:
        test_query_result = db.run("SELECT COUNT(*) FROM data;")
        print(f"✓ Final verification: SQLDatabase query test successful - {test_query_result}")
    except Exception as e:
        print(f"✗ SQLDatabase query test failed: {e}")
        raise Exception(f"SQLDatabase cannot execute queries: {str(e)}")
    
    # Verify the database can see the table
    available_tables = db.get_usable_table_names()
    print(f"✓ Available tables in SQLDatabase: {available_tables}")
    
    if 'data' not in available_tables:
        raise Exception("Failed to create or access the 'data' table")
    
    # Test a simple query to ensure everything works
    sample_query = "SELECT COUNT(*) as total_rows FROM data"
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sample_query))
            test_count = result.fetchone()[0]
            print(f"✓ Test query successful: {test_count} rows in data table")
    except Exception as e:
        print(f"✗ Test query failed: {e}")
        raise

    # Using Claude Haiku for reliable analytical and mathematical reasoning
    # Enhanced with aggressive rate limiting for production use
    llm = ChatAnthropic(
        model=AGENT_MODEL,
        temperature=0.1,  # Slight randomness for creativity in analysis approaches
        max_tokens=2048,  # Reduced to minimize token usage and avoid rate limits
        api_key=settings.ANTHROPIC_API_KEY,
        max_retries=5,  # More retries for rate limit handling
        default_request_timeout=120,  # Longer timeout for complex queries
        # Enhanced rate limiting configuration
        anthropic_api_url=None,  # Use default
    )
    
    # Enhanced toolkit with better error handling
    toolkit = SQLDatabaseToolkit(
        db=db, 
        llm=llm,
        reduce_k_below_max_tokens=True  # Automatically handle large result sets
    )
    
    # Create a production-ready SQL agent with better error handling
    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10,  # Reduced for better control
        prefix=CUSTOM_PREFIX,
        early_stopping_method="force",
        agent_type="zero-shot-react-description",  # More reliable agent type
    )
    return agent_executor
