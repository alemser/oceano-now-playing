# Contributing Guide

Thank you for your interest in contributing to **spi-now-playing**! This guide walks you through the development setup and workflow.

## Quick Start (2 minutes)

```bash
# Clone and enter the project
git clone https://github.com/alemser/spi-now-playing.git
cd spi-now-playing

# Run setup script (creates venv, installs deps, configures git hooks)
chmod +x setup.sh
./setup.sh

# Activate virtual environment
source venv/bin/activate

# Run tests to verify setup
make test
```

## Development Environment Setup

### Prerequisites
- Python 3.8 or higher
- Git

### Step-by-Step Setup

1. **Clone the Repository**
   ```bash
   git clone https://github.com/alemser/spi-now-playing.git
   cd spi-now-playing
   ```

2. **Create Virtual Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   # Install runtime + development dependencies
   pip install -r requirements.txt -r requirements-dev.txt
   
   # Or use the setup script
   chmod +x setup.sh
   ./setup.sh
   ```

4. **Verify Setup**
   ```bash
   make test
   ```
   You should see: **55 passed**

## Available Commands

```bash
make help          # Show all available commands
make test          # Run all tests (quick)
make test-verbose  # Run tests with detailed output
make test-volumio  # Test WebSocket API only
make test-state    # Test state machine only
make test-renderer # Test renderer utilities only
make push          # Push to GitHub (pre-hook runs tests)
```

## Development Workflow

### 1. **Create a Feature Branch**
```bash
git checkout -b feature/your-feature-name
```

### 2. **Make Changes & Run Tests**
```bash
# After editing code
make test

# If tests fail, review output and fix issues
make test-verbose
```

### 3. **Commit & Push**
```bash
git add <files>
git commit -m "Clear description of changes"

# Pre-push hook will run tests automatically
git push origin feature/your-feature-name
```

### 4. **Create Pull Request**
Push to GitHub and submit a PR with:
- Clear description of changes
- Reference to any related issues
- Test results confirmation

## Code Organization

```
spi-now-playing/
├── src/
│   ├── app/
│   │   └── main.py             # Main application loop and state machine
│   ├── artwork/
│   │   └── providers.py        # Artwork fallback providers
│   ├── media_players/
│   │   ├── base.py             # MediaPlayer abstract interface
│   │   ├── volumio.py          # Volumio WebSocket client
│   │   ├── moode.py            # MoOde client stub
│   │   └── picore.py           # piCorePlayer client stub
│   ├── renderer.py             # Display rendering logic
│   ├── config.py               # Configuration handling
│   └── spi-now-playing.py      # Compatibility entrypoint
├── tests/
│   ├── conftest.py             # Shared fixtures & mocks
│   ├── test_volumio.py         # WebSocket API tests
│   ├── test_state_machine.py   # State management tests
│   └── test_renderer.py        # Utility function tests
├── install.sh                  # Production deployment
├── setup.sh                    # Development environment
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # Development dependencies
└── pyproject.toml              # Python project metadata
```

## Testing Guidelines

### Run Tests Before Pushing
The pre-push hook automatically runs all tests. To run manually:
```bash
# Quick check
make test

# Before submitting PR
make test-verbose
```

### Test Coverage Areas
- **test_volumio.py**: WebSocket API, connection handling, message parsing
- **test_state_machine.py**: State transitions, pause/resume logic, mode alternation
- **test_renderer.py**: Image processing, color extraction, time formatting

### Writing New Tests
1. Add test file in `tests/` directory: `test_*.py`
2. Use fixtures from `conftest.py`
3. Follow existing test patterns
4. Run: `pytest tests/test_yourfile.py -v`

## Fixing Common Issues

### Virtual Environment Not Activating
```bash
# Recreate it
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### Module Not Found Errors
```bash
# Ensure pytest can find src/
python3 -m pytest tests/ -v
```

### Import Errors When Running Directly
Always use the venv:
```bash
source venv/bin/activate
python3 src/spi-now-playing.py
```

## Code Style (Future)

Currently no strict linting, but follow these conventions:
- Use descriptive variable names
- Add docstrings to functions
- Keep functions focused and under 50 lines
- Add type hints when possible (Python 3.8+)

## Deployment

For production deployment on Raspberry Pi:
```bash
chmod +x install.sh
./install.sh
```

This will:
1. Install system dependencies
2. Create virtual environment
3. Install Python packages
4. Setup systemd service for auto-start

## Questions?

- Check [README.md](README.md) for project overview
- Review [TESTING_SETUP.md](TESTING_SETUP.md) for test infrastructure details
- Open an issue on GitHub for bugs or feature requests

Happy coding! 🎵
