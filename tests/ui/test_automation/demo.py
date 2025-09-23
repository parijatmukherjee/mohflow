#!/usr/bin/env python3
"""
Demo script for Mohnitor UI automation.

This script demonstrates the automation testing framework
and runs a quick validation of all components.
"""

import sys
import time
import subprocess
from pathlib import Path


def print_header(title):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_status(message, status="INFO"):
    """Print a status message."""
    symbols = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️"}
    print(f"{symbols.get(status, 'ℹ️')} {message}")


def run_command(cmd, description):
    """Run a command and return success status."""
    print_status(f"Running: {description}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print_status(f"Success: {description}", "SUCCESS")
            return True
        else:
            print_status(
                f"Failed: {description} - {result.stderr[:100]}", "ERROR"
            )
            return False
    except subprocess.TimeoutExpired:
        print_status(f"Timeout: {description}", "WARNING")
        return False
    except Exception as e:
        print_status(f"Error: {description} - {str(e)}", "ERROR")
        return False


def main():
    """Run the demo."""
    print_header("🚀 Mohnitor UI Automation Demo")

    print_status("This demo validates the automation testing framework")
    print_status("Created for MohFlow's Mohnitor log viewer")

    # Change to project root
    project_root = Path(__file__).parent.parent.parent.parent

    print_header("📋 Framework Validation")

    # Test 1: Framework structure validation
    success1 = run_command(
        f"cd {project_root} && source .venv/bin/activate && PYTHONPATH=src python -m pytest tests/test_devui/test_automation/test_mock_automation.py::TestMohnitorMockAutomation::test_automation_test_structure_exists -v",
        "Validating framework structure",
    )

    # Test 2: Log generator validation
    success2 = run_command(
        f"cd {project_root} && source .venv/bin/activate && PYTHONPATH=src python -m pytest tests/test_devui/test_automation/test_mock_automation.py::TestMohnitorMockAutomation::test_log_generator_creates_logs -v",
        "Validating log generator",
    )

    # Test 3: Test class structure validation
    success3 = run_command(
        f"cd {project_root} && source .venv/bin/activate && PYTHONPATH=src python -m pytest tests/test_devui/test_automation/test_mock_automation.py::TestMohnitorMockAutomation::test_browser_test_structure -v",
        "Validating browser test structure",
    )

    print_header("📊 Test Results Summary")

    total_tests = 3
    passed_tests = sum([success1, success2, success3])

    print_status(f"Tests passed: {passed_tests}/{total_tests}")

    if passed_tests == total_tests:
        print_status("All framework validations passed!", "SUCCESS")

        print_header("🎯 Available Test Modes")
        print_status("1. Simple API Tests (no browser required):")
        print("   ./scripts/run_ui_tests.sh --simple")
        print()
        print_status("2. Browser Automation Tests (requires Selenium):")
        print("   ./scripts/run_ui_tests.sh --install-deps --browser")
        print()
        print_status("3. Manual Interactive Mode:")
        print("   ./scripts/run_ui_tests.sh --manual")
        print()

        print_header("📁 Test Files Created")
        test_files = [
            "tests/test_devui/test_automation/test_app.py - Test log generator",
            "tests/test_devui/test_automation/test_e2e_simple.py - Simple E2E tests",
            "tests/test_devui/test_automation/test_browser_ui.py - Browser automation",
            "tests/test_devui/test_automation/test_ui_automation.py - Comprehensive tests",
            "tests/test_devui/test_automation/test_mock_automation.py - Framework validation",
            "scripts/run_ui_tests.sh - Test runner script",
            "tests/test_devui/test_automation/README.md - Documentation",
        ]

        for file_desc in test_files:
            print_status(file_desc)

        print_header("🔍 Quick Test Demo")
        print_status(
            "Running a quick mock test to demonstrate functionality..."
        )

        # Run a quick demo test
        demo_success = run_command(
            f"cd {project_root} && source .venv/bin/activate && PYTHONPATH=src python -m pytest tests/test_devui/test_automation/test_mock_automation.py::TestMohnitorMockAutomation::test_mock_hub_api_calls -v",
            "Running mock API test",
        )

        if demo_success:
            print_status(
                "Demo test successful! Framework is working correctly.",
                "SUCCESS",
            )

        print_header("🎉 Demo Complete")
        print_status("The Mohnitor UI automation testing framework is ready!")
        print_status("You can now test the UI with real browser automation")

        return 0
    else:
        print_status(
            f"Some validations failed ({total_tests - passed_tests} failures)",
            "ERROR",
        )
        print_status("Check the error messages above for details", "WARNING")
        return 1


if __name__ == "__main__":
    sys.exit(main())
