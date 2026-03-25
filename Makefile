.PHONY: test push test-push install-hooks help

help:
	@echo "Available commands:"
	@echo "  make test          Run all tests"
	@echo "  make test-verbose  Run tests with verbose output"
	@echo "  make test-volumio  Run Volumio API tests only"
	@echo "  make test-state    Run state machine tests only"
	@echo "  make test-renderer Run renderer tests only"
	@echo "  make push          Push to GitHub (tests run automatically via pre-push hook)"
	@echo "  make test-push     Run tests, then push if all pass"
	@echo "  make install-hooks Install git hooks (one-time setup)"

test:
	python3 -m pytest tests/ -q

test-verbose:
	python3 -m pytest tests/ -v

test-volumio:
	python3 -m pytest tests/test_volumio.py -v

test-state:
	python3 -m pytest tests/test_state_machine.py -v

test-renderer:
	python3 -m pytest tests/test_renderer.py -v

test-push: test
	@echo "✅ Tests passed. Pushing to GitHub..."
	git push origin main

push:
	git push origin main

install-hooks:
	@echo "Setting up git hooks..."
	cp .githooks/pre-push .git/hooks/pre-push
	chmod +x .git/hooks/pre-push
	@echo "✅ Git hooks installed!"
	@echo "Tests will now run automatically before each push."
