#!/bin/sh

# CSV Analyzer Pro - Development Startup Script

echo "🚀 Starting CSV Analyzer Pro Development Environment"
echo "=================================================="

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check if Python is available
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check if Node.js is available
if ! command -v node >/dev/null 2>&1; then
    echo "❌ Node.js is required but not installed."
    exit 1
fi

# Check if we're in the right directory and backend folder exists
if [ ! -d "backend" ]; then
    echo "❌ Error: backend folder not found. Please run this script from the project root."
    exit 1
fi

if [ ! -f "backend/backend_adapter.py" ]; then
    echo "❌ Error: backend/backend_adapter.py not found."
    exit 1
fi

# Check if requirements.txt exists in backend folder
if [ ! -f "backend/requirements.txt" ]; then
    echo "❌ Error: backend/requirements.txt not found."
    exit 1
fi

# Install Python dependencies for backend
echo "📦 Installing Python dependencies..."
if [ ! -d "venv" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Change to backend directory and install dependencies
cd backend
echo "📦 Installing all dependencies from requirements.txt..."
pip install -q -r requirements.txt

# Check for environment variables
if [ ! -f ".env" ] && [ ! -f "../.env" ]; then
    echo "⚠️  Warning: No .env file found in backend or root. You may need to set up API keys."
    echo "   Create a .env file with your ANTHROPIC_API_KEY and other required variables."
fi

# Start Python backend in background from backend directory
echo "🐍 Starting Python backend on port 8000..."
python3 -m uvicorn backend_adapter:app --port 8000 --reload &
BACKEND_PID=$!

# Go back to root directory
cd ..

# Wait a moment for backend to start
sleep 5

# Check if backend started successfully
if ! curl -s http://127.0.0.1:8000/ >/dev/null 2>&1; then
    echo "❌ Backend failed to start properly"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo "✅ Backend started successfully on http://127.0.0.1:8000"

# Check if frontend folder exists
if [ -d "frontend" ]; then
    echo "⚡ Starting Next.js frontend from frontend folder..."
    cd frontend
elif [ -d "Frontend/nextjs-app" ]; then
    echo "⚡ Starting Next.js frontend from Frontend/nextjs-app..."
    cd Frontend/nextjs-app
else
    echo "⚠️  Frontend folder not found. Backend is running on http://127.0.0.1:8000"
    echo "📚 API Docs: http://127.0.0.1:8000/docs"
    echo ""
    echo "Press Ctrl+C to stop backend server"
    
    # Function to cleanup on exit
    cleanup() {
        echo ""
        echo "🛑 Stopping backend..."
        if [ -n "$BACKEND_PID" ]; then
            kill "$BACKEND_PID" 2>/dev/null
        fi
        echo "✅ Backend stopped"
        exit 0
    }
    
    # Set trap to cleanup on script exit
    trap cleanup INT TERM
    
    # Wait for user to stop
    wait
    exit 0
fi

# Install npm dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    npm install
fi

# Start frontend on port 3007 (current configuration)
PORT=3007 npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Both servers are starting up!"
echo ""
echo "🌐 Frontend: http://localhost:3007"
echo "🔧 Backend API: http://127.0.0.1:8000"
echo "📚 API Docs: http://127.0.0.1:8000/docs"
echo "🔍 Analysis Page: http://localhost:3007/analyze"
echo ""
echo "Press Ctrl+C to stop both servers"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping servers..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null
    fi
    echo "✅ Servers stopped"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup INT TERM

# Wait for user to stop
wait