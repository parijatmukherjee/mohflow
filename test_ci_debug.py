#!/usr/bin/env python3
"""
Minimal CI debug test to isolate import and basic functionality issues.
"""
import sys
print(f"Python version: {sys.version}")

try:
    # Test basic imports
    import mohflow
    print("✅ mohflow imported successfully")

    from mohflow.context.filters import SensitiveDataFilter
    print("✅ SensitiveDataFilter imported successfully")

    # Test basic functionality
    filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)
    result = filter_obj.classify_field("correlation_id")
    print(f"✅ classify_field works: {result.classification}")

    # Test basic filter functionality
    test_data = {"correlation_id": "test", "api_key": "secret"}
    filtered = filter_obj.filter_data(test_data)
    print(f"✅ filter_data works: {filtered}")

    print("🎉 All basic functionality works!")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)