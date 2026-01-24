#!/bin/bash
"""
Start the Guardrails demo environment
This script starts both the gateway server and demo web server
"""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[DEMO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[DEMO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[DEMO]${NC} $1"
}

print_error() {
    echo -e "${RED}[DEMO]${NC} $1"
}

# Function to cleanup background processes
cleanup() {
    print_status "Shutting down demo environment..."
    if [ ! -z "$GATEWAY_PID" ]; then
        kill $GATEWAY_PID 2>/dev/null || true
        print_status "Gateway server stopped"
    fi
    if [ ! -z "$DEMO_PID" ]; then
        kill $DEMO_PID 2>/dev/null || true
        print_status "Demo server stopped"
    fi
    print_success "Demo environment stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    print_error "Please run this script from the guardrails project root directory"
    exit 1
fi

print_success "🛡️  Starting Guardrails Demo Environment"
print_status "========================================"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    print_error "uv is not installed. Please install it first: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check environment variables
print_status "Checking environment..."
if [ -f ".env" ]; then
    print_success "Found .env file"
    set -a  # automatically export all variables
    source .env
    set +a  # stop automatically exporting
    
    # Verify key is loaded
    if [ ! -z "$OPENAI_API_KEY" ]; then
        print_success "OpenAI API key loaded (${OPENAI_API_KEY:0:10}...)"
    else
        print_warning "OPENAI_API_KEY not found in .env file"
    fi
else
    print_warning "No .env file found. You may need to set OPENAI_API_KEY for full functionality"
fi

# Start Redis if needed (optional)
if command -v redis-server &> /dev/null; then
    if ! pgrep -x "redis-server" > /dev/null; then
        print_status "Starting Redis server..."
        redis-server --daemonize yes --port 6379 2>/dev/null || print_warning "Could not start Redis (optional)"
    else
        print_success "Redis server already running"
    fi
else
    print_warning "Redis not found. Gateway will work but without caching"
fi

# Start the gateway server
print_status "Starting Gateway server on port 8000..."
uv run python -m bifrost.main &
GATEWAY_PID=$!

# Wait for gateway to start
sleep 3

# Check if gateway is running
if kill -0 $GATEWAY_PID 2>/dev/null; then
    print_success "Gateway server started (PID: $GATEWAY_PID)"
else
    print_error "Failed to start gateway server"
    exit 1
fi

# Start the demo server
print_status "Starting Demo server on port 3000..."
uv run python demo/server.py &
DEMO_PID=$!

# Wait for demo server to start
sleep 2

# Check if demo server is running
if kill -0 $DEMO_PID 2>/dev/null; then
    print_success "Demo server started (PID: $DEMO_PID)"
else
    print_error "Failed to start demo server"
    cleanup
    exit 1
fi

print_success "🚀 Demo environment is ready!"
print_status "==============================="
print_status "📱 Demo UI: http://localhost:3000"
print_status "🔌 Gateway API: http://localhost:8000"
print_status "📖 API Docs: http://localhost:8000/docs"
print_status ""
print_status "Available policies:"
print_status "  • enterprise_default_v1 (PII + Politics + Toxicity + Schema)"
print_status "  • simple_test (PII + Politics)"
print_status ""
print_status "Test scenarios:"
print_status "  📧 PII: 'My email is john@example.com'"
print_status "  🗳️  Politics: 'Vote for the best candidate'"
print_status "  🚫 Toxicity: 'You are such an idiot'"
print_status "  ✅ Clean: 'What's the weather like today?'"
print_status ""
print_warning "Press Ctrl+C to stop all servers"

# Keep the script running
wait
