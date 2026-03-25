# Testing & CI/CD Setup

This document explains the automated testing and pre-push verification system.

## Quick Start

### First Time Setup
```bash
chmod +x setup.sh
./setup.sh
source venv/bin/activate
make test
```

This will:
- Create the project Python virtual environment at `venv`
- Install all dependencies (including pytest)
- Configure git pre-push hook

Before running any test command, make sure you are using the project environment:

```bash
source venv/bin/activate
which python3
```

The `python3` path should point into `.../spi-now-playing/venv/...`.

Do not use `.venv` for this repository unless you also install the full project dependencies there. The default project workflow and scripts use `venv`.

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

1. Selects the repository Python environment, preferring `venv`, then `.venv`
2. Checks if pytest is installed for that interpreter
3. Runs all tests
4. **Blocks the push if any test fails**
5. Shows you which tests failed so you can fix them

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
pip install -r requirements.txt -r requirements-dev.txt

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
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

Or run setup.sh:
```bash
./setup.sh
```

If that still fails, verify you did not activate `.venv` by mistake.

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

The repository-managed hook source lives at `.githooks/pre-push` and is copied into `.git/hooks/pre-push` by `./setup.sh` and `make install-hooks`.

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
- ✅ **Current test suite** covers critical functionality
- ✅ **One-change-at-a-time** workflow prevents regressions
- ✅ **setup.sh** automates initial setup

This gives you confidence when refactoring Code Quality Fixes! 🧪
