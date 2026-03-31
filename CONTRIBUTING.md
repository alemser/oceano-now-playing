# Contributing Guide

Thank you for contributing to **oceano-now-playing**!

## Quick Start

```bash
git clone https://github.com/alemser/oceano-now-playing.git
cd oceano-now-playing
chmod +x setup.sh
./setup.sh
source venv/bin/activate
make test
```

After a clean setup you should see the full test suite pass with `make test`.

## Before You Start

1. Activate the project environment: `source venv/bin/activate`
2. Confirm `which python3` points into `.../oceano-now-playing/venv/...`
3. Run `make test` — start from a passing suite before editing anything.

This project uses `venv` (not `.venv`). If VS Code picks `.venv` by mistake, select `venv/bin/python` as the workspace interpreter explicitly.

## Available Commands

```bash
make test            # Run all tests (quiet)
make test-verbose    # Run tests with detailed output
make test-renderer   # Renderer tests only
make push            # Push to GitHub (pre-push hook runs tests)
```

## Development Workflow

```bash
git checkout -b feature/your-feature-name

# edit code ...
make test

git add <files>
git commit -m "Clear description of change"
git push origin feature/your-feature-name
```

Open a PR with a clear description and confirmation that `make test` passes.

## Code Organisation

```
src/
├── app/
│   └── main.py              # State machine and main loop
├── media_players/
│   ├── base.py              # MediaPlayer abstract interface
│   └── state_file.py        # Unified state reader (/tmp/oceano-state.json)
├── config.py                # Configuration
├── renderer.py              # Framebuffer renderer
└── oceano-now-playing.py    # Entrypoint

tests/
├── conftest.py              # Shared fixtures
├── test_renderer.py         # Renderer utility tests
├── test_config.py           # Configuration tests
└── test_vu_client.py        # VU ballistics tests
```

## Testing Guidelines

- Write tests before or alongside new code.
- Use fixtures from `conftest.py` (`oceano_state_playing`, `oceano_state_paused`, `mock_renderer`, etc.).
- Tests must pass offline — no network or hardware access in the test suite.
- After changes: `make test` must pass before pushing.

## Code Standards

- Type hints on all public functions.
- Docstrings on all public functions.
- No bare `except:` — always catch a specific exception type.
- Log errors instead of silencing them.

## Fixing Common Issues

**ModuleNotFoundError**: You are not in the project venv.
```bash
source venv/bin/activate
which python3   # must point into venv/
```

**Tests fail after dependency changes**:
```bash
pip install -r requirements.txt -r requirements-dev.txt
```

**Recreate venv from scratch**:
```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```
