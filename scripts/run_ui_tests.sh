#!/bin/bash

# Script to run Mohnitor UI automation tests
# This script can install dependencies and run tests in different modes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="$PROJECT_ROOT/.venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --install-deps    Install selenium and browser dependencies"
    echo "  --simple         Run simple HTTP API tests only"
    echo "  --browser        Run full browser automation tests"
    echo "  --visible        Run browser tests in visible mode (not headless)"
    echo "  --manual         Run manual test with live UI"
    echo "  --help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --simple                    # Quick API tests"
    echo "  $0 --browser                   # Full browser automation"
    echo "  $0 --install-deps --browser    # Install deps and run browser tests"
    echo "  $0 --manual                    # Start app and keep UI running"
}

install_selenium_deps() {
    print_status "Installing Selenium dependencies..."

    # Activate virtual environment
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
    else
        print_error "Virtual environment not found at $VENV_PATH"
        exit 1
    fi

    # Try to install selenium with timeout and fallback
    print_status "Attempting to install selenium..."
    timeout 120 pip install --no-cache-dir selenium==4.15.0 2>/dev/null
    if [ $? -ne 0 ]; then
        print_warning "Selenium installation failed or timed out"
        print_status "Trying alternative installation..."
        timeout 60 pip install --no-deps --no-cache-dir selenium 2>/dev/null
        if [ $? -ne 0 ]; then
            print_error "Failed to install Selenium. Browser tests will be skipped."
            print_status "You can run simple tests with: $0 --simple"
            return 1
        fi
    fi

    # Try to install webdriver-manager
    print_status "Installing webdriver-manager..."
    timeout 60 pip install --no-cache-dir webdriver-manager 2>/dev/null
    if [ $? -ne 0 ]; then
        print_warning "webdriver-manager installation failed"
    fi

    # Check if Chrome/Chromium is available
    if command -v google-chrome &> /dev/null; then
        print_success "Google Chrome found"
    elif command -v chromium-browser &> /dev/null; then
        print_success "Chromium browser found"
    elif command -v chromium &> /dev/null; then
        print_success "Chromium found"
    else
        print_warning "Chrome/Chromium not found. Browser tests may fail."
        print_status "To install Chrome on macOS: brew install --cask google-chrome"
        print_status "To install Chrome on Ubuntu: sudo apt-get install google-chrome-stable"
    fi

    # Check if selenium was successfully installed
    if python -c "import selenium" 2>/dev/null; then
        print_success "Selenium dependencies installed successfully"
        return 0
    else
        print_error "Selenium installation verification failed"
        return 1
    fi
}

run_simple_tests() {
    print_status "Running simple HTTP API tests..."

    cd "$PROJECT_ROOT"

    # Activate virtual environment
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
    fi

    # Run simple E2E tests
    PYTHONPATH=src python -m pytest tests/test_devui/test_automation/test_e2e_simple.py -v

    print_success "Simple tests completed"
}

run_browser_tests() {
    local visible_mode=${1:-false}

    print_status "Running browser automation tests..."

    cd "$PROJECT_ROOT"

    # Activate virtual environment
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
    fi

    # Check if selenium is available
    if ! python -c "import selenium" &> /dev/null; then
        print_warning "Selenium not available. Falling back to simple tests."
        print_status "To install Selenium: $0 --install-deps"
        run_simple_tests
        return $?
    fi

    # Run browser tests
    if [ "$visible_mode" = "true" ]; then
        print_status "Running tests in visible browser mode..."
        PYTHONPATH=src python tests/test_devui/test_automation/test_ui_automation.py --browser --visible
    else
        print_status "Running tests in headless browser mode..."
        PYTHONPATH=src python tests/test_devui/test_automation/test_ui_automation.py --browser
    fi

    if [ $? -eq 0 ]; then
        print_success "Browser tests completed"
    else
        print_warning "Browser tests had issues, falling back to simple tests"
        run_simple_tests
    fi
}

run_pytest_tests() {
    local test_mode=${1:-"simple"}

    print_status "Running pytest automation tests..."

    cd "$PROJECT_ROOT"

    # Activate virtual environment
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
    fi

    if [ "$test_mode" = "browser" ]; then
        # Run all automation tests including browser
        PYTHONPATH=src python -m pytest tests/test_devui/test_automation/ -v
    else
        # Run only simple tests
        PYTHONPATH=src python -m pytest tests/test_devui/test_automation/test_e2e_simple.py -v
    fi

    print_success "Pytest tests completed"
}

run_manual_test() {
    print_status "Starting manual test mode..."

    cd "$PROJECT_ROOT"

    # Activate virtual environment
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
    fi

    print_status "Starting test application..."
    print_status "Mohnitor UI will be available at: http://127.0.0.1:17361"
    print_status "Press Ctrl+C to stop..."

    # Run the test app directly
    PYTHONPATH=src python tests/test_devui/test_automation/test_app.py
}

# Parse command line arguments
INSTALL_DEPS=false
RUN_SIMPLE=false
RUN_BROWSER=false
VISIBLE_MODE=false
RUN_MANUAL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --install-deps)
            INSTALL_DEPS=true
            shift
            ;;
        --simple)
            RUN_SIMPLE=true
            shift
            ;;
        --browser)
            RUN_BROWSER=true
            shift
            ;;
        --visible)
            VISIBLE_MODE=true
            shift
            ;;
        --manual)
            RUN_MANUAL=true
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Main execution
print_status "Mohnitor UI Test Runner"
print_status "======================"

# Install dependencies if requested
if [ "$INSTALL_DEPS" = true ]; then
    install_selenium_deps
fi

# Run manual test if requested
if [ "$RUN_MANUAL" = true ]; then
    run_manual_test
    exit 0
fi

# Run tests based on options
if [ "$RUN_BROWSER" = true ]; then
    run_browser_tests "$VISIBLE_MODE"
elif [ "$RUN_SIMPLE" = true ]; then
    run_simple_tests
else
    # Default: run simple tests
    print_status "No test mode specified, running simple tests..."
    print_status "Use --browser for full browser automation"
    run_simple_tests
fi

print_success "All tests completed successfully!"