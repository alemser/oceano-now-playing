#!/bin/bash

# Setup script for oceano-now-playing development environment
# Installs dependencies and configures git hooks

set -e  # Exit on any error

echo "🔧 Setting up oceano-now-playing development environment..."
echo ""

if [ -d ".venv" ] && [ ! -d "venv" ]; then
    echo "⚠️  Found .venv in this repository."
    echo "⚠️  The documented development workflow for this project uses ./venv."
    echo "⚠️  setup.sh will create and use ./venv so project scripts and docs stay consistent."
    echo ""
fi

if [ -d ".venv" ] && [ -d "venv" ]; then
    echo "⚠️  Found both .venv and venv."
    echo "⚠️  Use 'source venv/bin/activate' before running make test or pushing changes."
    echo "⚠️  In VS Code, select venv/bin/python for this workspace."
    echo ""
fi

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
echo "✅ Using interpreter: $(pwd)/venv/bin/python"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt
pip install -r requirements-dev.txt
echo "✅ Dependencies installed (runtime + development)"
echo ""

# Install git hooks
echo "Installing git hooks..."
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
echo "✅ Git hooks configured via core.hooksPath=.githooks"
echo ""

echo "================================="
echo "✅ Setup complete!"
echo "================================="
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "   In VS Code, select: venv/bin/python"
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
