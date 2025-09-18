"""
T012: Test SensitiveDataFilter.get_configuration() method
These tests MUST FAIL initially (TDD approach)
"""

from mohflow.context.filters import SensitiveDataFilter, FilterConfiguration


class TestGetConfiguration:
    """Test SensitiveDataFilter.get_configuration() method from contract"""

    def test_get_configuration_returns_accurate_current_state(self):
        """Test get_configuration returns accurate current configuration"""
        custom_safe_fields = {"custom_field_1", "custom_field_2"}
        custom_patterns = ["custom_.*", ".*_custom$"]

        filter_obj = SensitiveDataFilter(
            enabled=True,
            exclude_tracing_fields=True,
            custom_safe_fields=custom_safe_fields,
            tracing_field_patterns=custom_patterns,
            case_sensitive=True,
        )

        config = filter_obj.get_configuration()

        assert isinstance(config, FilterConfiguration)
        assert config.enabled is True
        assert config.exclude_tracing_fields is True
        assert config.custom_safe_fields == custom_safe_fields
        assert config.tracing_field_patterns == custom_patterns
        assert config.case_sensitive is True

    def test_get_configuration_includes_runtime_modifications(self):
        """Test get_configuration includes fields added/removed at runtime"""
        filter_obj = SensitiveDataFilter()

        # Get initial configuration
        initial_config = filter_obj.get_configuration()
        initial_fields = initial_config.custom_safe_fields.copy()

        # Add field at runtime
        filter_obj.add_safe_field("runtime_field")

        # Get updated configuration
        updated_config = filter_obj.get_configuration()

        assert "runtime_field" in updated_config.custom_safe_fields
        assert (
            len(updated_config.custom_safe_fields) == len(initial_fields) + 1
        )

        # Remove field at runtime
        filter_obj.remove_safe_field("runtime_field")

        # Get final configuration
        final_config = filter_obj.get_configuration()

        assert "runtime_field" not in final_config.custom_safe_fields
        assert final_config.custom_safe_fields == initial_fields

    def test_get_configuration_immutable_return(self):
        """Test configuration must be immutable/copy to prevent external modification"""
        filter_obj = SensitiveDataFilter(custom_safe_fields={"original_field"})

        config = filter_obj.get_configuration()

        # Try to modify returned configuration
        config.custom_safe_fields.add("malicious_field")

        # Get fresh configuration - should not include malicious modification
        fresh_config = filter_obj.get_configuration()
        assert "malicious_field" not in fresh_config.custom_safe_fields
        assert "original_field" in fresh_config.custom_safe_fields

    def test_get_configuration_reflects_enabled_disabled_state(self):
        """Test get_configuration reflects current enabled/disabled state"""
        # Start enabled
        filter_obj = SensitiveDataFilter(enabled=True)
        config = filter_obj.get_configuration()
        assert config.enabled is True

        # Disable filter
        filter_obj.enabled = False
        config_disabled = filter_obj.get_configuration()
        assert config_disabled.enabled is False

        # Re-enable filter
        filter_obj.enabled = True
        config_enabled = filter_obj.get_configuration()
        assert config_enabled.enabled is True

    def test_get_configuration_includes_all_custom_patterns(self):
        """Test get_configuration includes all custom patterns"""
        initial_patterns = ["pattern1_.*", ".*_pattern2"]
        filter_obj = SensitiveDataFilter(
            tracing_field_patterns=initial_patterns
        )

        config = filter_obj.get_configuration()
        assert config.tracing_field_patterns == initial_patterns

        # Add pattern at runtime
        filter_obj.add_tracing_pattern("runtime_pattern_.*")

        updated_config = filter_obj.get_configuration()
        assert "runtime_pattern_.*" in updated_config.tracing_field_patterns
        assert "pattern1_.*" in updated_config.tracing_field_patterns
        assert ".*_pattern2" in updated_config.tracing_field_patterns

    def test_get_configuration_default_values(self):
        """Test get_configuration returns correct default values"""
        filter_obj = SensitiveDataFilter()  # All defaults

        config = filter_obj.get_configuration()

        assert config.enabled is True
        assert config.exclude_tracing_fields is True  # New default
        assert config.custom_safe_fields == set()
        assert config.tracing_field_patterns == []
        assert config.case_sensitive is False
        assert config.sensitive_fields is not None
        assert config.sensitive_patterns is not None

    def test_get_configuration_sensitive_fields_included(self):
        """Test get_configuration includes sensitive field configuration"""
        custom_sensitive = {"custom_secret", "custom_key"}
        filter_obj = SensitiveDataFilter(sensitive_fields=custom_sensitive)

        config = filter_obj.get_configuration()

        # Should include both built-in and custom sensitive fields
        assert len(config.sensitive_fields) > len(custom_sensitive)
        for field in custom_sensitive:
            assert field in config.sensitive_fields

    def test_get_configuration_performance(self):
        """Test get_configuration is performant"""
        filter_obj = SensitiveDataFilter(
            custom_safe_fields=set(f"field_{i}" for i in range(100))
        )

        import time

        # Should be fast even with many custom fields
        start_time = time.perf_counter()
        for _ in range(100):
            filter_obj.get_configuration()
        end_time = time.perf_counter()

        # Allow more time for CI environment variability
        assert (end_time - start_time) < 0.05  # Less than 50ms for 100 calls

    def test_get_configuration_thread_safety(self):
        """Test get_configuration is thread-safe"""
        import threading
        import time

        filter_obj = SensitiveDataFilter()
        configs = []
        errors = []

        def get_config_repeatedly():
            try:
                for _ in range(50):
                    config = filter_obj.get_configuration()
                    configs.append(config)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def modify_filter():
            try:
                for i in range(25):
                    filter_obj.add_safe_field(f"thread_field_{i}")
                    time.sleep(0.002)
            except Exception as e:
                errors.append(e)

        # Start threads
        threads = [
            threading.Thread(target=get_config_repeatedly),
            threading.Thread(target=get_config_repeatedly),
            threading.Thread(target=modify_filter),
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should not have any errors
        assert len(errors) == 0
        assert len(configs) == 100  # 2 threads * 50 calls each

    def test_get_configuration_state_consistency(self):
        """Test get_configuration always returns consistent state"""
        filter_obj = SensitiveDataFilter()

        # Add several fields in sequence
        fields_to_add = ["field_1", "field_2", "field_3"]
        for field in fields_to_add:
            filter_obj.add_safe_field(field)

        config = filter_obj.get_configuration()

        # All added fields should be present
        for field in fields_to_add:
            assert field in config.custom_safe_fields

        # Configuration should be internally consistent
        assert len(config.custom_safe_fields) >= len(fields_to_add)
        assert config.enabled in [True, False]  # Boolean value
        assert isinstance(config.tracing_field_patterns, list)
        assert isinstance(config.sensitive_fields, set)
        assert isinstance(config.sensitive_patterns, list)
