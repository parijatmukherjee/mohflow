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

.PHONY: all clean install format lint test test-unit test-integration test-ui test-automation test-automation-mock build help venv

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

# Run only unit tests
test-unit:
	@echo "$(BLUE)Running unit tests...$(RESET)"
	$(call activate_venv, pytest tests/unit -v)
	@echo "$(GREEN)Unit tests complete!$(RESET)"

# Run only integration tests
test-integration:
	@echo "$(BLUE)Running integration tests...$(RESET)"
	$(call activate_venv, pytest tests/integration -v)
	@echo "$(GREEN)Integration tests complete!$(RESET)"

# Run only UI tests (including automation)
test-ui:
	@echo "$(BLUE)Running UI tests...$(RESET)"
	$(call activate_venv, pytest tests/ui -v)
	@echo "$(GREEN)UI tests complete!$(RESET)"

# Run automation tests only
test-automation:
	@echo "$(BLUE)Running automation tests...$(RESET)"
	$(call activate_venv, pytest tests/ui/test_automation -v)
	@echo "$(GREEN)Automation tests complete!$(RESET)"

# Run mock automation tests (no external dependencies)
test-automation-mock:
	@echo "$(BLUE)Running mock automation tests...$(RESET)"
	$(call activate_venv, pytest tests/ui/test_automation/test_mock_automation.py -v)
	@echo "$(GREEN)Mock automation tests complete!$(RESET)"

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

# Self-documenting help command
help:
	@printf "Available commands:\n"
	@printf "  make install           - Create virtual environment and install dependencies\n"
	@printf "  make format           - Format code using black\n"
	@printf "  make lint             - Lint code using flake8\n"
	@printf "  make test             - Run all tests with coverage\n"
	@printf "  make test-unit        - Run unit tests only\n"
	@printf "  make test-integration - Run integration tests only\n"
	@printf "  make test-ui          - Run UI tests (including automation)\n"
	@printf "  make test-automation  - Run automation tests only\n"
	@printf "  make test-automation-mock - Run mock automation tests (no deps)\n"
	@printf "  make clean            - Clean up generated files\n"
	@printf "  make build            - Build package\n"
	@printf "  make all              - Run clean, install, format, lint, and test\n"

# Run complete pipeline
all: clean install format lint test
	@printf "$(GREEN)All tasks completed successfully!$(RESET)\n"