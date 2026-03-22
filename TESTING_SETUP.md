# Testing & CI/CD Setup

This document explains the automated testing and pre-push verification system.

## Quick Start

### First Time Setup
```bash
./setup.sh
```

This will:
- Create a Python virtual environment
- Install all dependencies (including pytest)
- Configure git pre-push hook

### Running Tests

```bash
# Run all tests
make test

# Run tests with verbose output
make test-verbose

# Run only Volumio API tests
make test-volumio

# Run only state machine tests
make test-state

# Run only renderer tests
make test-renderer
```

### Pushing to GitHub

**Option 1: Automatic Testing (Recommended)**
```bash
git push origin main
```
Tests run automatically via pre-push hook. If tests fail, push is blocked.

**Option 2: Manual Test Before Push**
```bash
make test-push
```
Runs tests first. If all pass, pushes to GitHub.

## How It Works

### Pre-Push Hook

Located at `.git/hooks/pre-push`, this script runs automatically before any push to GitHub:

1. Checks if pytest is installed
2. Runs all tests
3. **Blocks the push if any test fails**
4. Shows you which tests failed so you can fix them

**This prevents broken code from reaching GitHub!**

### Makefile Commands

The `Makefile` provides convenient shortcuts:

| Command | What It Does |
|---------|-------------|
| `make test` | Quick test run (quiet mode) |
| `make test-verbose` | Tests with full output |
| `make test-volumio` | Only test Volumio API |
| `make test-state` | Only test state machine |
| `make test-renderer` | Only test utilities |
| `make test-push` | Test, then push if pass |
| `make push` | Direct push (hook still runs) |
| `make install-hooks` | Manually install git hook |

## Typical Workflow

### Making a Change

1. Make your code change
2. Test it locally:
   ```bash
   make test
   ```
3. If tests pass, commit:
   ```bash
   git add .
   git commit -m "Your change description"
   ```
4. Push:
   ```bash
   make push
   ```
   or just:
   ```bash
   git push origin main
   ```

### If Tests Fail

```
❌ Tests failed! Push blocked.

Fix the errors and try again:
  pytest tests/ -v
```

Read the test output to understand what broke, fix your code, and run tests again:

```bash
# Run tests to see what failed
make test-verbose

# Fix your code based on the errors

# Test again
make test
```

## Requirement: Install pytest on Raspberry Pi

For the pre-push hook to work on the Raspberry Pi, you need pytest installed:

```bash
# Option 1: Virtual environment (Recommended)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Option 2: System-wide (not recommended)
pip3 install pytest pytest-mock

# Option 3: Using the setup script
./setup.sh
```

## Skipping the Hook (Not Recommended)

If you absolutely must push without running tests:

```bash
git push origin main --no-verify
```

⚠️ **Only use this if you have a very good reason. The pre-push hook exists to catch bugs before they reach GitHub!**

## GitHub Actions (Optional - For Future)

You can also add GitHub Actions CI/CD that runs tests on every push to GitHub. This provides:
- Tests run in the cloud (consistent environment)
- Public record of test results
- Automatic checks before merging PRs

This would be a Priority 2+ enhancement.

## Troubleshooting

### "pytest not found" during push

The hook doesn't have pytest installed. Fix with:
```bash
pip install pytest pytest-mock
```

Or run setup.sh:
```bash
./setup.sh
```

### Pre-push hook isn't running

Check if it's executable:
```bash
ls -la .git/hooks/pre-push
# Should show: -rwxr-xr-x
```

If not executable:
```bash
chmod +x .git/hooks/pre-push
```

Or reinstall hooks:
```bash
make install-hooks
```

### My test environment is different than the Pi

This is a known issue. The pre-push hook will run with your local environment. To test on the actual Pi:

```bash
# SSH to Pi
ssh pi@raspberrypi.local

# Navigate to project
cd spi-now-playing

# Activate environment
source venv/bin/activate

# Run tests
pytest tests/ -v
```

## Summary

- ✅ **Pre-push hook** blocks bad code from reaching GitHub
- ✅ **Makefile** provides convenient test commands
- ✅ **40+ tests** cover critical functionality
- ✅ **One-change-at-a-time** workflow prevents regressions
- ✅ **setup.sh** automates initial setup

This gives you confidence when refactoring Code Quality Fixes! 🧪
