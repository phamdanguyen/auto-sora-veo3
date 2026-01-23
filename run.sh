#!/bin/bash
echo "Starting Uni-Video Automation..."

# Check for venv
if [ -d "venv" ]; then
    echo "Using virtual environment..."
    PYTHON_CMD="./venv/bin/python"
else
    echo "Virtual environment not found, using system python..."
    if ! command -v python3 &> /dev/null; then
        echo "Python3 could not be found. Please install Python3."
        exit 1
    fi
    PYTHON_CMD="python3"
fi

# Load .env variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Run
$PYTHON_CMD -m app.main
