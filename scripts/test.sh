#!/bin/bash

# Test script for Guardrails
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

# Run unit tests
run_unit_tests() {
    echo_info "Running unit tests..."
    uv run pytest tests/unit/ -v --cov=cga_core --cov=guard_packs --cov=gateway --cov=cga_sdk
}

# Run integration tests
run_integration_tests() {
    echo_info "Running integration tests..."
    uv run pytest tests/integration/ -v
}

# Run linting
run_linting() {
    echo_info "Running linting..."
    uv run ruff check .
    uv run black --check .
    uv run mypy .
}

# Run corpus tests
run_corpus_tests() {
    echo_info "Running corpus tests..."
    uv run pytest tests/integration/test_corpus.py -v
}

# Run all tests
run_all_tests() {
    echo_info "Running all tests..."
    run_unit_tests
    run_integration_tests
    run_corpus_tests
}

# Main function
main() {
    case "${1:-all}" in
        "unit")
            run_unit_tests
            ;;
        "integration")
            run_integration_tests
            ;;
        "corpus")
            run_corpus_tests
            ;;
        "lint")
            run_linting
            ;;
        "all")
            run_linting
            run_all_tests
            ;;
        *)
            echo "Usage: $0 [unit|integration|corpus|lint|all]"
            echo "  unit        - Run unit tests only"
            echo "  integration - Run integration tests only"
            echo "  corpus      - Run corpus tests only"
            echo "  lint        - Run linting only"
            echo "  all         - Run all tests and linting (default)"
            exit 1
            ;;
    esac
}

main "$@"
