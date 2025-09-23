# MohFlow Testing Guide

This document describes the comprehensive testing structure for MohFlow, including unit tests, integration tests, and UI automation tests.

## 🏗️ Test Structure

The tests are organized into a clear hierarchy:

```
tests/
├── conftest.py              # Shared test configuration and fixtures
├── unit/                    # Unit tests for individual components
│   ├── test_context/        # Context and filtering tests
│   ├── test_handlers/       # Log handler tests
│   ├── test_logger/         # Logger core functionality
│   ├── test_*.py           # Other unit tests (CLI, config, etc.)
├── integration/             # Integration tests for full scenarios
│   ├── test_basic_tracing_scenario.py
│   └── test_custom_safe_fields_scenario.py
└── ui/                      # UI and automation tests
    ├── conftest.py          # UI-specific test configuration
    ├── test_automation/     # Browser automation tests
    │   ├── test_app.py      # Test log generator
    │   ├── test_e2e_simple.py      # Simple E2E tests
    │   ├── test_browser_ui.py      # Browser automation
    │   ├── test_ui_automation.py   # Comprehensive automation
    │   └── test_mock_automation.py # Mock tests (no deps)
    ├── test_contracts/      # API contract tests
    ├── test_integration/    # UI integration tests
    └── test_models/         # UI data model tests
```

## 🎯 Test Commands

### Primary Commands

| Command | Description | Tests Included |
|---------|-------------|----------------|
| `make test` | **Run all tests with coverage** | All tests (401 tests) |
| `make test-unit` | Run unit tests only | 277 unit tests |
| `make test-integration` | Run integration tests only | 17 integration tests |
| `make test-ui` | Run UI tests (including automation) | 107 UI tests |

### Specialized Commands

| Command | Description | Use Case |
|---------|-------------|----------|
| `make test-automation` | Run automation tests only | Browser automation testing |
| `make test-automation-mock` | Run mock automation tests | No external dependencies |

### Development Commands

```bash
# Complete development pipeline
make all                    # Clean → Install → Format → Lint → Test

# Quick validation
make test-automation-mock   # Test framework without dependencies
make test-unit             # Fast unit test feedback
```

## 📊 Test Categories

### 1. Unit Tests (277 tests)
**Location**: `tests/unit/`
**Purpose**: Test individual components in isolation

**Categories**:
- **Context Tests** (`test_context/`) - Field classification, filtering, correlation
- **Handler Tests** (`test_handlers/`) - Loki handler integration
- **Logger Tests** (`test_logger/`) - Core logging functionality
- **Configuration Tests** - Config loading, CLI, auto-configuration
- **Template Tests** - Dashboard template management

**Example**:
```bash
make test-unit              # Run all unit tests
pytest tests/unit/test_context/ -v  # Run context tests only
```

### 2. Integration Tests (17 tests)
**Location**: `tests/integration/`
**Purpose**: Test complete scenarios with multiple components

**Scenarios**:
- Basic tracing scenario
- Custom safe fields scenario
- High security mode scenario
- Direct filter usage scenario
- E2E integration tests
- Mohnitor integration tests

**Example**:
```bash
make test-integration       # Run all integration tests
```

### 3. UI Tests (107 tests)
**Location**: `tests/ui/`
**Purpose**: Test Mohnitor UI and automation

#### 3a. Automation Tests (28 tests)
**Location**: `tests/ui/test_automation/`

| Test File | Purpose | Dependencies |
|-----------|---------|--------------|
| `test_mock_automation.py` | Framework validation | None |
| `test_e2e_simple.py` | HTTP API testing | FastAPI |
| `test_browser_ui.py` | Browser automation | Selenium + Chrome |
| `test_ui_automation.py` | Comprehensive testing | FastAPI + Selenium |

#### 3b. Contract Tests (28 tests)
**Location**: `tests/ui/test_contracts/`
**Purpose**: API contract validation for hub endpoints

#### 3c. Integration Tests (14 tests)
**Location**: `tests/ui/test_integration/`
**Purpose**: Multi-service and failover scenarios

#### 3d. Model Tests (28 tests)
**Location**: `tests/ui/test_models/`
**Purpose**: UI data model validation

## 🎪 Automation Testing

### Browser Automation Features
The automation tests verify:
- ✅ **UI Loading** - Mohnitor interface loads correctly
- ✅ **Real-time Logging** - Log messages appear via WebSocket
- ✅ **Log Filtering** - Search and filter functionality
- ✅ **Multi-service Discovery** - Multiple services are discovered
- ✅ **High Volume Handling** - System handles high log volumes
- ✅ **Error Visualization** - Error logs have proper styling
- ✅ **API Endpoints** - All REST endpoints respond correctly

### Dependency Handling
Tests intelligently handle dependencies:

```python
# Automatic skipping when dependencies unavailable
@requires_selenium          # Skips if Selenium not installed
@requires_fastapi          # Skips if FastAPI not installed
@requires_hub_server       # Skips if hub server not running
```

### Usage Examples

```bash
# No dependencies required - always works
make test-automation-mock

# Requires FastAPI for hub server
make test-ui

# Requires Selenium + Chrome for browser automation
./scripts/run_ui_tests.sh --install-deps --browser

# Manual testing with live UI
./scripts/run_ui_tests.sh --manual
```

## 🚀 Getting Started

### 1. Quick Start
```bash
# Run framework validation (no deps)
make test-automation-mock

# Run all unit tests (fast feedback)
make test-unit

# Run full test suite
make test
```

### 2. Development Workflow
```bash
# After making changes
make format                 # Format code
make lint                  # Check code quality
make test-unit             # Quick unit test validation
make test                  # Full validation before commit
```

### 3. CI/CD Pipeline
```bash
make all                   # Complete pipeline
# Runs: clean → install → format → lint → test
```

## 📈 Test Results

### Current Coverage
- **Total Tests**: 401 tests
- **Unit Tests**: 275 tests (273 passing, 2 skipped)
- **Integration Tests**: 28 tests (passing)
- **UI Tests**: 98 tests (28 passing, 70 skipped due to missing deps)

### Expected Behavior
- **Unit/Integration**: Should always pass
- **UI Tests**: Skip gracefully when dependencies unavailable
- **Automation**: Skip when FastAPI/Selenium not installed

## 🔧 Troubleshooting

### Common Issues

**1. "Selenium not available"**
```bash
pip install selenium webdriver-manager
# Or: ./scripts/run_ui_tests.sh --install-deps
```

**2. "FastAPI not available"**
```bash
pip install fastapi uvicorn websockets
```

**3. "Hub server not available"**
- Install FastAPI dependencies
- Verify port 17361 is not in use
- Check firewall settings

### Debug Mode
```bash
export MOHFLOW_LOG_LEVEL=DEBUG
make test-automation-mock    # Debug framework
make test -v                # Verbose test output
```

## 📋 Best Practices

### For Developers
1. **Always run unit tests** before committing
2. **Use mock tests** for rapid development feedback
3. **Test automation locally** before pushing UI changes
4. **Follow TDD** - write failing tests first

### For CI/CD
1. **Use `make test`** for complete validation
2. **Cache dependencies** for faster builds
3. **Run automation in headless mode**
4. **Set appropriate timeouts** for browser tests

### For Contributors
1. **Add tests** for new features
2. **Update automation** for UI changes
3. **Use proper test categories** (unit vs integration vs UI)
4. **Handle dependencies gracefully** with skip decorators

## 🎯 Future Enhancements

- [ ] Parallel test execution
- [ ] Visual regression testing
- [ ] Performance benchmarking
- [ ] Mobile browser testing
- [ ] Docker-based test environment
- [ ] Load testing scenarios

---

The testing framework is designed to be **comprehensive yet flexible**, ensuring robust validation while handling optional dependencies gracefully. This enables both local development and CI/CD environments to run appropriate test suites based on available dependencies.