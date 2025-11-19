#!/bin/bash
# Desktop Agent Test Runner
# Quick script to run tests with common options

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Desktop Agent Test Suite"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Please install test dependencies:"
    echo "   pip install -r requirements/test.txt"
    exit 1
fi

# Parse arguments
MODE="${1:-all}"

case "$MODE" in
    "fast")
        echo "🏃 Running fast tests only..."
        pytest -v -m "not slow"
        ;;
    "coverage")
        echo "📊 Running tests with coverage..."
        pytest -v --cov=modules --cov-report=term-missing --cov-report=html
        echo ""
        echo "✅ Coverage report generated: htmlcov/index.html"
        ;;
    "verbose")
        echo "🔍 Running tests with verbose output..."
        pytest -vv --tb=long
        ;;
    "quick")
        echo "⚡ Quick test run (stop on first failure)..."
        pytest -x --tb=short
        ;;
    "help")
        echo "Usage: ./run_tests.sh [MODE]"
        echo ""
        echo "Modes:"
        echo "  all       - Run all tests (default)"
        echo "  fast      - Run only fast tests (exclude slow tests)"
        echo "  coverage  - Run tests with coverage report"
        echo "  verbose   - Run tests with detailed output"
        echo "  quick     - Stop on first failure"
        echo "  help      - Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./run_tests.sh              # Run all tests"
        echo "  ./run_tests.sh fast         # Fast tests only"
        echo "  ./run_tests.sh coverage     # With coverage"
        exit 0
        ;;
    "all"|*)
        echo "🧪 Running all tests..."
        pytest -v
        ;;
esac

EXIT_CODE=$?

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All tests passed!"
else
    echo "❌ Some tests failed (exit code: $EXIT_CODE)"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit $EXIT_CODE
