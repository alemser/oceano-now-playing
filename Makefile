.PHONY: test push install-hooks help

help:
	@echo "Available commands:"
	@echo "  make test          Run all tests"
	@echo "  make test-verbose  Run tests with verbose output"
	@echo "  make test-renderer Run renderer tests only"
	@echo "  make push          Push to GitHub (tests run automatically via pre-push hook)"
	@echo "  make install-hooks Install git hooks (one-time setup)"

test:
	python3 -m pytest tests/ -q

test-verbose:
	python3 -m pytest tests/ -v

test-renderer:
	python3 -m pytest tests/test_renderer.py -v

push:
	git push origin main

install-hooks:
	@echo "Setting up git hooks..."
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-push
	@echo "✅ Git hooks installed!"
	@echo "Tests will now run automatically before each push."
