#!/bin/bash

# Development setup script for Guardrails
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Install dependencies
install_dependencies() {
    echo_info "Installing dependencies with UV..."
    uv sync --all-extras
    echo_info "Dependencies installed successfully"
}

# Start development environment
start_dev() {
    echo_info "Starting development environment..."
    
    # Start Redis if not running
    if ! docker ps | grep -q redis; then
        echo_info "Starting Redis container..."
        docker run -d --name guardrails-redis -p 6379:6379 redis:7-alpine
    else
        echo_warn "Redis container already running"
    fi
    
    # Start gateway in development mode
    echo_info "Starting gateway server..."
    uv run gateway.main:main &
    GATEWAY_PID=$!
    
    # Wait for gateway to start
    sleep 5
    
    # Test gateway
    if curl -f http://localhost:8000/health; then
        echo_info "Gateway is running at http://localhost:8000"
    else
        echo_error "Gateway failed to start"
        kill $GATEWAY_PID
        exit 1
    fi
    
    echo_info "Development environment ready!"
    echo_info "Gateway: http://localhost:8000"
    echo_info "Health check: http://localhost:8000/health"
    echo_info "Press Ctrl+C to stop"
    
    # Wait for interrupt
    trap 'echo_info "Stopping development environment..."; kill $GATEWAY_PID; docker stop guardrails-redis; docker rm guardrails-redis; exit 0' INT
    wait $GATEWAY_PID
}

# Run tests
run_tests() {
    echo_info "Running tests..."
    uv run pytest tests/ -v
}

# Format code
format_code() {
    echo_info "Formatting code..."
    uv run black .
    uv run ruff check --fix .
    echo_info "Code formatted successfully"
}

# Install pre-commit hooks
install_pre_commit() {
    echo_info "Installing pre-commit hooks..."
    uv run pre-commit install
    echo_info "Pre-commit hooks installed successfully"
}

# Show help
show_help() {
    echo "Guardrails Development Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  install     - Install dependencies"
    echo "  start       - Start development environment"
    echo "  test        - Run tests"
    echo "  format      - Format code"
    echo "  hooks       - Install pre-commit hooks"
    echo "  help        - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 install    # Install all dependencies"
    echo "  $0 start      # Start gateway with Redis"
    echo "  $0 test       # Run test suite"
}

# Main function
main() {
    case "${1:-help}" in
        "install")
            install_dependencies
            ;;
        "start")
            start_dev
            ;;
        "test")
            run_tests
            ;;
        "format")
            format_code
            ;;
        "hooks")
            install_pre_commit
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            echo_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
