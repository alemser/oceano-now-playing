#!/bin/bash

# Setup script for spi-now-playing development environment
# Installs dependencies and configures git hooks

set -e  # Exit on any error

echo "🔧 Setting up spi-now-playing development environment..."
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION found"
echo ""

# Create virtual environment (optional, but recommended)
echo "Setting up virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt
pip install -r requirements-dev.txt
echo "✅ Dependencies installed (runtime + development)"
echo ""

# Install git hooks
echo "Installing git hooks..."
chmod +x .git/hooks/pre-push
echo "✅ Pre-push hook installed"
echo ""

echo "================================="
echo "✅ Setup complete!"
echo "================================="
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Run tests anytime:"
echo "   make test"
echo ""
echo "3. Push to GitHub (tests run automatically):"
echo "   make push"
echo ""
echo "4. View all available commands:"
echo "   make help"
echo ""
