# Mohnitor UI Automation Tests

This directory contains comprehensive automation tests for the Mohnitor UI, verifying that the logging viewer works correctly with browser automation and API testing.

## Overview

The automation test suite validates:
- ✅ **UI Loading**: Mohnitor interface loads correctly in browsers
- ✅ **Real-time Logging**: Log messages appear in real-time via WebSocket
- ✅ **Log Filtering**: Search and filter functionality works
- ✅ **Multi-service Discovery**: Multiple services are discovered and displayed
- ✅ **High Volume Handling**: System handles high log volumes gracefully
- ✅ **Error Visualization**: Error logs are properly styled and displayed
- ✅ **API Endpoints**: All REST endpoints respond correctly

## Test Files

### Core Test Files

- **`test_app.py`** - Test application that generates various log scenarios
- **`test_e2e_simple.py`** - Simple end-to-end tests using HTTP API only
- **`test_browser_ui.py`** - Full browser automation tests using Selenium
- **`test_ui_automation.py`** - Comprehensive test suite combining all approaches
- **`test_mock_automation.py`** - Mock tests to validate framework structure

### Test Runner

- **`scripts/run_ui_tests.sh`** - Shell script to run tests in different modes

## Test Modes

### 1. Simple Mode (HTTP API Only)
Tests the Mohnitor API endpoints without browser automation:

```bash
# Using pytest
pytest tests/test_devui/test_automation/test_e2e_simple.py -v

# Using test runner
./scripts/run_ui_tests.sh --simple
```

**What it tests:**
- Hub startup and health checks
- Log generation and capture
- API endpoint responses
- Multi-service scenarios
- Trace correlation

### 2. Browser Automation Mode
Full browser automation using Selenium WebDriver:

```bash
# Install dependencies first
./scripts/run_ui_tests.sh --install-deps

# Run browser tests (headless)
./scripts/run_ui_tests.sh --browser

# Run browser tests (visible)
./scripts/run_ui_tests.sh --browser --visible
```

**What it tests:**
- UI loads correctly in browser
- Log entries appear in real-time
- WebSocket connection established
- Filtering and search functionality
- Error log styling and visualization
- High volume performance

### 3. Manual Mode
Interactive mode for manual testing and development:

```bash
./scripts/run_ui_tests.sh --manual
```

This starts a test application with continuous log generation and keeps the Mohnitor UI running at `http://127.0.0.1:17361` for manual inspection.

## Dependencies

### Required (Always)
- `mohflow` - Core logging library
- `requests` - HTTP client for API testing
- `pytest` - Test framework

### Optional (Browser Tests)
- `selenium` - Browser automation
- `webdriver-manager` - Chrome driver management
- Chrome/Chromium browser

### Optional (Mohnitor Hub)
- `fastapi` - Web framework for hub
- `uvicorn` - ASGI server
- `websockets` - WebSocket support

## Test Scenarios

### Log Generation Scenarios
The test app generates diverse log scenarios:

```python
# Authentication flow
logger.info("User authentication started", user_id="testuser", trace_id="auth-001")
logger.info("Password validated", user_id="testuser", trace_id="auth-001")
logger.info("Session created", session_id="sess-123", trace_id="auth-001")

# Error scenarios
logger.error("Payment processing failed",
             payment_id="pay-456",
             error="Card declined",
             trace_id="payment-001")

# Performance scenarios
logger.warning("Slow query detected",
               query_time="2.5s",
               query="SELECT * FROM users",
               trace_id="perf-001")
```

### Browser Test Scenarios
Browser tests verify:

1. **UI Structure**: Main container, header, logs container exist
2. **Log Display**: Log entries appear with proper formatting
3. **Real-time Updates**: New logs appear automatically
4. **WebSocket Connection**: Connection status indicators work
5. **Filtering**: Search and level filtering function correctly
6. **Error Styling**: Error/warning logs have proper CSS classes
7. **Performance**: UI remains responsive under high log volume

## Usage Examples

### Quick Validation
```bash
# Run framework validation
pytest tests/test_devui/test_automation/test_mock_automation.py -v
```

### Development Testing
```bash
# Start manual test mode during development
./scripts/run_ui_tests.sh --manual

# In another terminal, run API tests
pytest tests/test_devui/test_automation/test_e2e_simple.py -v
```

### CI/CD Pipeline
```bash
# Simple tests (no browser required)
./scripts/run_ui_tests.sh --simple

# Full automation (requires browser setup)
./scripts/run_ui_tests.sh --install-deps --browser
```

### Custom Test Scenarios
```python
from tests.test_devui.test_automation.test_app import TestLogGenerator

# Create custom log generator
generator = TestLogGenerator("my-service")
generator.start()

# Generate specific scenarios
generator.logger.info("Custom test scenario", component="auth")
generator.generate_test_scenarios()

# UI available at http://127.0.0.1:17361
input("Press Enter to stop...")
generator.stop()
```

## Troubleshooting

### Common Issues

**1. "FastAPI not available"**
```bash
pip install fastapi uvicorn websockets
```

**2. "Chrome driver not available"**
```bash
./scripts/run_ui_tests.sh --install-deps
# Or manually: brew install --cask google-chrome
```

**3. "Connection refused"**
- Ensure no other service is using port 17361
- Check firewall settings
- Verify Mohnitor dependencies are installed

**4. "Selenium not available"**
```bash
pip install selenium webdriver-manager
```

### Debug Mode
Set environment variables for detailed debugging:

```bash
export MOHFLOW_LOG_LEVEL=DEBUG
export MOHNITOR_DEBUG=true
./scripts/run_ui_tests.sh --manual
```

## Architecture

### Test Flow
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Test App      │───▶│  Mohnitor Hub    │───▶│   Browser UI    │
│                 │    │                  │    │                 │
│ • Generates     │    │ • Collects logs  │    │ • Displays logs │
│   diverse logs  │    │ • WebSocket API  │    │ • Real-time     │
│ • Multiple      │    │ • REST API       │    │   updates       │
│   scenarios     │    │ • Static UI      │    │ • Filtering     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Test Layers
1. **Unit Tests**: Individual component validation
2. **API Tests**: HTTP endpoint verification
3. **Integration Tests**: Multi-service scenarios
4. **Browser Tests**: Full UI automation
5. **Performance Tests**: High volume handling

## Contributing

When adding new automation tests:

1. **Add test scenarios** to `test_app.py` for new log types
2. **Create API tests** in `test_e2e_simple.py` for backend validation
3. **Add browser tests** in `test_browser_ui.py` for UI verification
4. **Update comprehensive tests** in `test_ui_automation.py`
5. **Add mock validation** in `test_mock_automation.py` for structure

### Test Naming Convention
- `test_*_loads_*` - UI loading tests
- `test_*_appears_*` - Content display tests
- `test_*_updates_*` - Real-time functionality tests
- `test_*_handles_*` - Performance/volume tests
- `test_*_e2e_*` - End-to-end scenario tests

## Future Enhancements

- [ ] Add mobile browser testing
- [ ] Implement visual regression testing
- [ ] Add performance benchmarking
- [ ] Create Docker-based test environment
- [ ] Add accessibility testing
- [ ] Implement load testing scenarios