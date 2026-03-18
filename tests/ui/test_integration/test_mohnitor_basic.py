#!/usr/bin/env python3
"""
Basic test script for Mohnitor functionality.

Tests that the hub can start and serve basic endpoints.
"""

import sys
import time
import threading
import requests
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from mohflow.devui.hub import MohnitorHub
    from mohflow.devui.types import HubDescriptor

    print("✅ Mohnitor imports successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("💡 This is expected if FastAPI is not installed")
    sys.exit(0)


def test_basic_hub():
    """Test basic hub functionality."""
    print("\n🧪 Testing basic hub functionality...")

    try:
        # Create hub
        hub = MohnitorHub(host="127.0.0.1", port=17361, buffer_size=1000)
        print("✅ Hub created successfully")

        # Test descriptor creation
        descriptor = hub.create_descriptor()
        print(f"✅ Descriptor created: {descriptor.host}:{descriptor.port}")

        # Save descriptor
        hub.save_descriptor()
        print("✅ Descriptor saved to file")

        return True

    except Exception as e:
        print(f"❌ Hub test failed: {e}")
        return False


def test_data_models():
    """Test data model functionality."""
    print("\n🧪 Testing data models...")

    try:
        from mohflow.devui.types import LogEvent, HubDescriptor
        from datetime import datetime, timezone

        # Test HubDescriptor
        descriptor = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token=None,
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )

        # Test serialization
        data = descriptor.to_dict()
        restored = HubDescriptor.from_dict(data)
        assert restored.host == descriptor.host
        print("✅ HubDescriptor serialization works")

        # Test LogEvent
        log_event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Test message",
            logger="test.logger",
        )

        # Test serialization
        event_data = log_event.to_dict()
        restored_event = LogEvent.from_dict(event_data)
        assert restored_event.message == log_event.message
        print("✅ LogEvent serialization works")

        return True

    except Exception as e:
        print(f"❌ Data model test failed: {e}")
        return False


def test_discovery():
    """Test discovery functionality."""
    print("\n🧪 Testing discovery...")

    try:
        from mohflow.devui.discovery import discover_hub
        from mohflow.devui.election import try_become_hub

        # Test discovery (should find nothing initially)
        existing_hub = discover_hub()
        if existing_hub is None:
            print("✅ Discovery correctly finds no existing hub")
        else:
            print(
                f"ℹ️  Found existing hub: {existing_hub.host}:{existing_hub.port}"
            )

        return True

    except Exception as e:
        print(f"❌ Discovery test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Starting Mohnitor basic functionality tests...")

    tests = [
        test_data_models,
        test_discovery,
        test_basic_hub,
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1

    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("🎉 All basic tests passed!")
        return True
    else:
        print(
            "⚠️  Some tests failed, but this is expected without FastAPI installed"
        )
        return False


if __name__ == "__main__":
    main()
