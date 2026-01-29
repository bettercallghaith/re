#!/bin/bash

# Sales Dashboard Quick Start Script

echo "🚀 Starting Sales Dashboard..."
echo ""

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check for Node
if ! command -v npm &> /dev/null; then
    echo "❌ Node.js/npm is required but not installed"
    exit 1
fi

# Start Backend
echo "📦 Installing backend dependencies..."
cd "$(dirname "$0")/backend"
pip3 install -r requirements.txt --quiet

echo "🔧 Starting backend server on port 8000..."
python3 main.py &
BACKEND_PID=$!
cd ..

# Wait for backend to start
sleep 2

# Start Frontend
echo "📦 Installing frontend dependencies..."
cd "$(dirname "$0")/frontend"
npm install --silent

echo "🌐 Starting frontend on port 3000..."
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Dashboard is starting!"
echo ""
echo "   Frontend:  http://localhost:3000"
echo "   Backend:   http://localhost:8000"
echo ""
echo "📝 Note: For AI insights, install Ollama:"
echo "   curl -fsSL https://ollama.com/install.sh | sh"
echo "   ollama pull mistral"
echo ""
echo "Press Ctrl+C to stop all services"

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

# Keep running
wait
