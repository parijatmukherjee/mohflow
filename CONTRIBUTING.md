# Contributing to MohFlow

Thank you for your interest in contributing to MohFlow! This guide will help you get started with contributing to our structured logging library.

## Getting Started

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
```bash
git clone https://github.com/YOUR_USERNAME/mohflow.git
cd mohflow
```

### Environment Setup

Create and activate a virtual environment:

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install in development mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Verify installation
python -c "from mohflow import MohflowLogger; print('✓ MohFlow development setup complete')"
```

## 📋 Pre-PR Checklist

Before submitting a pull request, ensure all items are completed:

- [ ] **Specification written** under `specs/` for non-trivial changes
- [ ] **TDD workflow followed**: tests added/updated before implementation
- [ ] **Quality gates pass**: All commands must execute without errors:
  - `make format` - Code formatting with black
  - `make lint` - Linting with flake8 (zero violations required)
  - `make test` - All 401 tests pass (some may skip due to optional dependencies)
- [ ] **Documentation updated** (README/docstrings) as needed
- [ ] **Branch follows naming convention** (feat/, fix/, chore/)
- [ ] **PR title describes change clearly**
- [ ] **No breaking changes** without major version bump

## Branch Naming

Use the following prefixes for your branch names:

- **`feat/short-description`** - New features
- **`fix/short-description`** - Bug fixes
- **`chore/short-description`** - Maintenance tasks (docs, tests, refactoring)

**Examples:**
- `feat/add-async-logging`
- `fix/memory-leak-handlers`
- `chore/update-dependencies`

## Development Workflow

### Test-Driven Development (TDD)

MohFlow requires TDD for all new features. Follow this process:

1. **Write failing tests first** → Define expected behavior
2. **Implement minimal code** → Make tests pass
3. **Refactor** → Improve code while keeping tests green

### Quality Gates

All code must pass quality gates locally and in CI:

```bash
# Format code (must pass with zero errors)
make format

# Lint code (must pass with zero errors)
make lint

# Run test suite (must pass all tests)
make test
```

### Spec-Kit Workflow

For non-trivial changes, use the spec-kit development process:

1. **`/specify`** → Create detailed specification in `specs/`
2. **`/plan`** → Generate implementation plan with technical design
3. **`/tasks`** → Break down into actionable tasks

## Review Expectations

### Code Quality
- **Coverage**: Maintain or improve test coverage
- **Performance**: Consider performance implications of changes
- **Backward Compatibility**: Ensure changes don't break existing APIs
- **Documentation**: Update docs for new features or API changes

### Review Process
- All PRs require passing CI checks
- Code review focuses on correctness, maintainability, and alignment with project principles
- Performance-sensitive changes may require benchmarking
- Breaking changes require discussion and version bump planning

## Project Principles

MohFlow follows these core principles (see [constitution.md](.specify/memory/constitution.md)):

- **Structured-First Logging**: JSON output for all log messages
- **Minimal Dependencies**: Keep library lightweight
- **Test-First & TDD**: Non-negotiable requirement for all features
- **Quality Gates**: Zero-tolerance for lint violations
- **Spec-Kit Flow**: Structured development process for features

## Code Style

- **Line length**: 79 characters maximum
- **Formatting**: Use `black` for code formatting
- **Linting**: Pass `flake8` with zero violations
- **Type hints**: Use type hints for all public APIs
- **Docstrings**: Document all public functions and classes

## Testing

### Running Tests

```bash
# Run all tests (401 tests total)
make test

# Run test categories
make test-unit         # 277 unit tests (fast feedback)
make test-integration  # 17 integration tests (scenarios)
make test-ui           # 107 UI tests (includes automation)

# Run automation tests specifically
make test-automation      # Full browser automation (requires Chrome)
make test-automation-mock # Mock tests (no dependencies)

# Run specific test file
pytest tests/test_specific.py

# Run with coverage report
pytest --cov=mohflow --cov-report=html
```

### Test Categories

- **Unit tests** (277): Test individual components in isolation
- **Integration tests** (17): Test complete scenarios with multiple components
- **UI tests** (107): Test Mohnitor UI and browser automation
- **Automation tests**: Browser-based testing with Selenium
- **Contract tests**: API contract validation for hub endpoints
- **Performance tests**: Ensure performance requirements

## Documentation

### What to Update

- **README.md**: For user-facing changes
- **Docstrings**: For new APIs or behavior changes
- **CHANGELOG.md**: For all changes (updated during release)

### Documentation Standards

- Clear, concise explanations
- Working code examples
- Links to related concepts
- Consistent terminology

## Getting Help

- **GitHub Issues**: Report bugs or request features
- **GitHub Discussions**: Ask questions or discuss ideas
- **Code Review**: Use PR comments for specific feedback

## Release Process

Releases are managed by maintainers following semantic versioning:

- **Major** (X.0.0): Breaking changes
- **Minor** (0.X.0): New features, backward compatible
- **Patch** (0.0.X): Bug fixes, backward compatible

## Recognition

All contributors are recognized in release notes. Thank you for helping make MohFlow better!

---

For more details on project governance and technical decisions, see the [constitution](.specify/memory/constitution.md).