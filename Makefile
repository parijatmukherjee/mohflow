# Check if we're running on Windows
ifeq ($(OS),Windows_NT)
	# Windows doesn't support ANSI color codes by default
	BLUE=
	GREEN=
	RED=
	RESET=
else
	# Use ANSI color codes with printf
	BLUE:=$(shell printf '\033[34m')
	GREEN:=$(shell printf '\033[32m')
	RED:=$(shell printf '\033[31m')
	RESET:=$(shell printf '\033[0m')
endif

# Variables
PYTHON = python3
PIP = $(PYTHON) -m pip
SOURCE_DIR = src/mohflow
TEST_DIR = tests
VENV = .venv
SHELL := /bin/bash

.PHONY: all clean install format lint test build publish-test publish help venv

# Activate virtual environment and run command
define activate_venv
	source $(VENV)/bin/activate && $1
endef

# Install and activate virtual environment
venv:
	@printf "$(BLUE)Creating virtual environment...$(RESET)\n"
	@$(PYTHON) -m venv $(VENV)
	@printf "$(GREEN)Virtual environment created!$(RESET)\n"

# Install dependencies in virtual environment
install: venv
	@printf "$(BLUE)Installing dependencies...$(RESET)\n"
	$(call activate_venv, $(PIP) install -r requirements-dev.txt)
	@printf "$(BLUE)Installing package in development mode...$(RESET)\n"
	$(call activate_venv, $(PIP) install -e .)
	@printf "$(GREEN)Installation complete!$(RESET)\n"

# Format code using black
format:
	@printf "$(BLUE)Formatting code with black...$(RESET)\n"
	$(call activate_venv, black $(SOURCE_DIR) $(TEST_DIR))
	@printf "$(GREEN)Formatting complete!$(RESET)\n"

# Lint code using flake8
lint:
	@printf "$(BLUE)Linting code with flake8...$(RESET)\n"
	$(call activate_venv, flake8 $(SOURCE_DIR) $(TEST_DIR))
	@printf "$(GREEN)Linting complete!$(RESET)\n"

test:
	@echo "$(BLUE)Running tests with coverage...$(RESET)"
	$(call activate_venv, pytest --cov=mohflow --cov-report=term-missing --cov-report=html)
	@echo "$(GREEN)Tests complete! Check htmlcov/index.html for coverage report$(RESET)"

# Clean up generated files
clean:
	@printf "$(BLUE)Cleaning up...$(RESET)\n"
	@rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ $(VENV)/
	@find . -type d -name __pycache__ -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@printf "$(GREEN)Cleanup complete!$(RESET)\n"

# Build package
build: clean
	@printf "$(BLUE)Building package...$(RESET)\n"
	$(call activate_venv, $(PYTHON) -m build)
	@printf "$(GREEN)Build complete!$(RESET)\n"

# Publish to Test PyPI
publish-test: build
	@printf "$(BLUE)Publishing to Test PyPI...$(RESET)\n"
	$(call activate_venv, $(PYTHON) -m twine upload --repository testpypi dist/*)
	@printf "$(GREEN)Test publish complete!$(RESET)\n"

# Publish to PyPI
publish: build
	@printf "$(BLUE)Publishing to PyPI...$(RESET)\n"
	$(call activate_venv, $(PYTHON) -m twine upload dist/*)
	@printf "$(GREEN)Publish complete!$(RESET)\n"

# Self-documenting help command
help:
	@printf "Available commands:\n"
	@printf "  make install      - Create virtual environment and install dependencies\n"
	@printf "  make format      - Format code using black\n"
	@printf "  make lint        - Lint code using flake8\n"
	@printf "  make test        - Run tests using pytest\n"
	@printf "  make clean       - Clean up generated files\n"
	@printf "  make build       - Build package\n"
	@printf "  make publish-test- Publish to Test PyPI\n"
	@printf "  make publish     - Publish to PyPI\n"
	@printf "  make all         - Run clean, install, format, lint, and test\n"