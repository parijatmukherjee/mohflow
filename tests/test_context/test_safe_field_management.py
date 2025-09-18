"""
T010: Test SensitiveDataFilter.add_safe_field() and remove_safe_field() methods
These tests MUST FAIL initially (TDD approach)
"""

import pytest
from mohflow.context.filters import SensitiveDataFilter


class TestSafeFieldManagement:
    """Test SensitiveDataFilter safe field management methods from contract"""

    def test_add_safe_field_basic(self):
        """Test add_safe_field adds field to exemption processing"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        # Initially not a safe field
        assert filter_obj.is_tracing_field("new_safe_field") is False

        # Add as safe field
        filter_obj.add_safe_field("new_safe_field")

        # Should now be considered a tracing field
        assert filter_obj.is_tracing_field("new_safe_field") is True

        # Should be exempted from filtering
        classification = filter_obj.classify_field("new_safe_field")
        assert classification.exempted is True

    def test_add_safe_field_validation_field_name_format(self):
        """Test add_safe_field validates field name format"""
        filter_obj = SensitiveDataFilter()

        # Valid field names should work
        valid_names = [
            "valid_field",
            "trace_123",
            "span-id",
            "correlation.id",
            "request_id_v2",
        ]

        for name in valid_names:
            filter_obj.add_safe_field(name)  # Should not raise

        # Invalid field names should fail
        invalid_names = [
            "",  # empty
            None,  # None
            "   ",  # whitespace only
            "field with spaces",  # spaces
            "field@invalid",  # invalid characters
            "field\nwith\nnewlines",  # newlines
        ]

        for name in invalid_names:
            with pytest.raises(ValueError, match="invalid.*field.*name"):
                filter_obj.add_safe_field(name)

    def test_add_safe_field_prevent_conflicts_with_sensitive(self):
        """Test add_safe_field prevents conflicts with sensitive patterns"""
        filter_obj = SensitiveDataFilter()

        # Should allow adding fields that don't conflict
        filter_obj.add_safe_field("custom_trace_id")  # Should work

        # Should prevent adding obvious sensitive fields
        sensitive_conflicts = [
            "password",
            "api_key",
            "secret_key",
            "access_token",
        ]

        for field in sensitive_conflicts:
            with pytest.raises(ValueError, match="conflict.*sensitive"):
                filter_obj.add_safe_field(field)

    def test_add_safe_field_duplicate_handling(self):
        """Test add_safe_field handles duplicate additions gracefully"""
        filter_obj = SensitiveDataFilter()

        field_name = "duplicate_field"

        # First addition should work
        filter_obj.add_safe_field(field_name)
        assert filter_obj.is_tracing_field(field_name) is True

        # Second addition should not raise error
        filter_obj.add_safe_field(field_name)  # Should not raise
        assert filter_obj.is_tracing_field(field_name) is True

        # Should not create duplicates in internal storage
        config = filter_obj.get_configuration()
        field_count = sum(
            1 for f in config.custom_safe_fields if f == field_name
        )
        assert field_count == 1

    def test_add_safe_field_case_sensitivity_handling(self):
        """Test add_safe_field respects case sensitivity settings"""
        # Case insensitive filter
        filter_insensitive = SensitiveDataFilter(case_sensitive=False)
        filter_insensitive.add_safe_field("Test_Field")

        assert filter_insensitive.is_tracing_field("test_field") is True
        assert filter_insensitive.is_tracing_field("TEST_FIELD") is True
        assert filter_insensitive.is_tracing_field("Test_Field") is True

        # Case sensitive filter
        filter_sensitive = SensitiveDataFilter(case_sensitive=True)
        filter_sensitive.add_safe_field("Test_Field")

        assert filter_sensitive.is_tracing_field("Test_Field") is True
        assert filter_sensitive.is_tracing_field("test_field") is False
        assert filter_sensitive.is_tracing_field("TEST_FIELD") is False

    def test_remove_safe_field_basic(self):
        """Test remove_safe_field removes field from exemption processing"""
        filter_obj = SensitiveDataFilter()

        field_name = "removable_field"

        # Add field first
        filter_obj.add_safe_field(field_name)
        assert filter_obj.is_tracing_field(field_name) is True

        # Remove field
        filter_obj.remove_safe_field(field_name)
        assert filter_obj.is_tracing_field(field_name) is False

        # Should restore default filtering behavior
        classification = filter_obj.classify_field(field_name)
        assert classification.exempted is False

    def test_remove_safe_field_not_affect_builtin(self):
        """Test remove_safe_field does not affect built-in tracing fields"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        builtin_fields = ["correlation_id", "trace_id", "span_id"]

        for field in builtin_fields:
            # Should not be able to remove built-in fields
            with pytest.raises(ValueError, match="cannot remove.*built-in"):
                filter_obj.remove_safe_field(field)

            # Built-in field should still be tracing field
            assert filter_obj.is_tracing_field(field) is True

    def test_remove_safe_field_nonexistent_graceful(self):
        """Test remove_safe_field handles non-existent field gracefully"""
        filter_obj = SensitiveDataFilter()

        # Should not raise error for non-existent field
        filter_obj.remove_safe_field("nonexistent_field")  # Should not raise

        # Should handle None gracefully
        filter_obj.remove_safe_field(None)  # Should not raise

        # Should handle empty string gracefully
        filter_obj.remove_safe_field("")  # Should not raise

    def test_safe_field_persistence_across_operations(self):
        """Test safe field additions persist across filter operations"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        # Add safe field
        filter_obj.add_safe_field("persistent_field")

        # Perform filtering operations
        test_data = {
            "persistent_field": "should_be_preserved",
            "api_key": "should_be_redacted",
            "correlation_id": "built_in_preserved",
        }

        result = filter_obj.filter_data(test_data)

        # Safe field should remain preserved after filtering
        assert "persistent_field" in result.preserved_fields
        assert (
            result.filtered_data["persistent_field"] == "should_be_preserved"
        )

    def test_safe_field_thread_safety(self):
        """Test safe field operations are thread-safe"""
        import threading
        import time

        filter_obj = SensitiveDataFilter()
        errors = []

        def add_fields(thread_id):
            try:
                for i in range(10):
                    filter_obj.add_safe_field(f"thread_{thread_id}_field_{i}")
                    time.sleep(
                        0.001
                    )  # Small delay to encourage race conditions
            except Exception as e:
                errors.append(e)

        def remove_fields(thread_id):
            try:
                time.sleep(0.005)  # Let add operations start first
                for i in range(10):
                    filter_obj.remove_safe_field(
                        f"thread_{thread_id}_field_{i}"
                    )
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Start multiple threads
        threads = []
        for i in range(3):
            t1 = threading.Thread(target=add_fields, args=(i,))
            t2 = threading.Thread(target=remove_fields, args=(i,))
            threads.extend([t1, t2])

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should not have any thread safety errors
        assert len(errors) == 0

    def test_safe_field_configuration_integration(self):
        """Test safe field management integrates with configuration"""
        custom_fields = {"initial_field_1", "initial_field_2"}
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True, custom_safe_fields=custom_fields
        )

        # Initial custom fields should be present
        config = filter_obj.get_configuration()
        assert "initial_field_1" in config.custom_safe_fields
        assert "initial_field_2" in config.custom_safe_fields

        # Add new field
        filter_obj.add_safe_field("new_runtime_field")

        # Updated configuration should include new field
        updated_config = filter_obj.get_configuration()
        assert "new_runtime_field" in updated_config.custom_safe_fields
        assert (
            "initial_field_1" in updated_config.custom_safe_fields
        )  # Still there

        # Remove initial field
        filter_obj.remove_safe_field("initial_field_1")

        # Configuration should reflect removal
        final_config = filter_obj.get_configuration()
        assert "initial_field_1" not in final_config.custom_safe_fields
        assert (
            "initial_field_2" in final_config.custom_safe_fields
        )  # Still there
        assert (
            "new_runtime_field" in final_config.custom_safe_fields
        )  # Still there
