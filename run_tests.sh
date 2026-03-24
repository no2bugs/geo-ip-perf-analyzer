#!/usr/bin/env bash
# Run the E2E test suite for geo-ip-perf-analyzer.
# Usage: ./run_tests.sh [pytest-args...]
# Examples:
#   ./run_tests.sh                  # run all tests
#   ./run_tests.sh -k scan          # only scan-related tests
#   ./run_tests.sh -x               # stop on first failure
#   ./run_tests.sh --co             # list tests without running

set -e
cd "$(dirname "$0")"

# Create venv if missing
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install deps if pytest is missing
if ! python -c "import pytest" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -q pytest pyyaml flask geoip2 requests apscheduler python-dotenv
fi

echo "Running tests..."
python -m pytest tests/ -v --tb=short "$@"
