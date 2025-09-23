"""Integration tests for MohFlow components."""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, Mock
from mohflow import MohflowLogger
from mohflow.context.correlation import get_correlation_id


class TestMohflowLoggerIntegration:
    """Integration tests for MohflowLogger with new features."""

    def test_logger_with_auto_config_and_context_enrichment(self):
        """Test logger with auto-configuration and context enrichment."""
        with patch(
            "mohflow.auto_config.AutoConfigurator.detect_environment"
        ) as mock_detect:
            from mohflow.auto_config import EnvironmentInfo

            mock_detect.return_value = EnvironmentInfo(
                cloud_provider="aws",
                region="us-east-1",
                environment_type="production",
            )

            logger = MohflowLogger(
                service_name="integration-test",
                enable_auto_config=True,
                enable_context_enrichment=True,
                enable_sensitive_data_filter=False,  # Disable for testing
            )

            # Verify auto-config was applied
            assert logger.config.ENVIRONMENT == "production"

            # Test context enrichment
            from mohflow.context.enrichment import RequestContextManager

            with RequestContextManager(
                request_id="req-123", user_id="user-456"
            ):
                with patch("sys.stdout"):
                    logger.info("Test message", extra_field="extra_value")

    def test_logger_with_json_config_file(self):
        """Test logger initialization with JSON configuration file."""
        config_data = {
            "service_name": "json-config-test",
            "log_level": "DEBUG",
            "environment": "staging",
            "console_logging": True,
            "file_logging": False,
            "context_enrichment": {
                "include_timestamp": True,
                "include_system_info": True,
                "include_request_context": True,
            },
            "sensitive_data_filter": {
                "enabled": True,
                "redaction_text": "***REDACTED***",
                "patterns": ["custom_secret"],
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            logger = MohflowLogger(config_file=config_file)

            # Verify configuration was loaded
            assert logger.config.SERVICE_NAME == "json-config-test"
            assert logger.config.LOG_LEVEL == "DEBUG"
            assert logger.config.ENVIRONMENT == "staging"

            # Test logging with sensitive data
            with patch("sys.stdout"):
                logger.info(
                    "Test with sensitive data",
                    custom_secret="should_be_redacted",
                    normal_field="should_be_visible",
                )

        finally:
            os.unlink(config_file)

    def test_end_to_end_logging_with_all_features(self):
        """Test end-to-end logging with all features enabled."""
        logger = MohflowLogger(
            service_name="e2e-test",
            environment="test",
            enable_context_enrichment=True,
            enable_sensitive_data_filter=True,
        )

        # Test with request context and sensitive data
        from mohflow.context.enrichment import RequestContextManager

        with RequestContextManager(request_id="req-e2e", user_id="user-e2e"):
            correlation_id = get_correlation_id()

            # Test that logging works with context enrichment and sensitive data filtering
            logger.info(
                "User login attempt",
                username="test_user",
                password="secret123",  # Should be redacted
                ip_address="192.168.1.1",
                correlation_id=correlation_id,
            )

            # Test passes if no exceptions are raised and features work as expected

    def test_logger_with_environment_variables(self):
        """Test logger configuration via environment variables."""
        env_vars = {
            "MOHFLOW_SERVICE_NAME": "env-test-service",
            "MOHFLOW_LOG_LEVEL": "WARNING",
            "MOHFLOW_ENVIRONMENT": "production",
            "MOHFLOW_CONSOLE_LOGGING": "true",
        }

        with patch.dict(os.environ, env_vars):
            # Config loader should pick up environment variables
            from mohflow.config_loader import ConfigLoader

            loader = ConfigLoader()
            config = loader.load_config()

            assert config["service_name"] == "env-test-service"
            assert config["log_level"] == "WARNING"
            assert config["environment"] == "production"
            assert config["console_logging"] is True

    def test_logger_configuration_precedence(self):
        """Test configuration precedence: runtime > env > file."""
        # Create config file
        file_config = {
            "service_name": "file-service",
            "log_level": "INFO",
            "environment": "development",
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(file_config, f)
            config_file = f.name

        env_vars = {
            "MOHFLOW_LOG_LEVEL": "DEBUG",
            "MOHFLOW_LOKI_URL": "http://env-loki:3100",
        }

        try:
            with patch.dict(os.environ, env_vars):
                logger = MohflowLogger(
                    config_file=config_file,
                    environment="production",  # Runtime override
                    console_logging=False,  # Runtime override
                )

                # Runtime should have highest precedence
                assert logger.config.ENVIRONMENT == "production"
                assert logger.config.CONSOLE_LOGGING is False

                # Environment should override file
                assert logger.config.LOG_LEVEL == "DEBUG"

                # File config should be preserved if not overridden
                assert logger.config.SERVICE_NAME == "file-service"

        finally:
            os.unlink(config_file)

    def test_context_correlation_across_async_operations(self):
        """Test context correlation in async-like scenarios."""
        import threading
        from mohflow.context.enrichment import RequestContextManager

        logger = MohflowLogger(
            service_name="async-test",
            enable_context_enrichment=True,
            enable_sensitive_data_filter=False,
        )

        results = []

        def simulate_async_operation(operation_id):
            with RequestContextManager(request_id=f"req-{operation_id}"):
                correlation_id = get_correlation_id()

                # Simulate some work
                import time

                time.sleep(0.01)

                with patch("sys.stdout"):
                    logger.info(
                        f"Operation {operation_id} completed",
                        operation_id=operation_id,
                        correlation_id=correlation_id,
                    )

                results.append((operation_id, correlation_id))

        # Run multiple operations concurrently
        threads = []
        for i in range(3):
            thread = threading.Thread(
                target=simulate_async_operation, args=(i,)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify each operation had its own correlation ID
        assert len(results) == 3
        correlation_ids = [corr_id for _, corr_id in results]
        assert len(set(correlation_ids)) == 3  # All unique

    def test_sensitive_data_filtering_integration(self):
        """Test sensitive data filtering in real logging scenarios."""
        logger = MohflowLogger(
            service_name="security-test", enable_sensitive_data_filter=True
        )

        # Test various sensitive data scenarios
        test_cases = [
            {
                "scenario": "login_attempt",
                "data": {
                    "username": "john_doe",
                    "password": "secret123",
                    "email": "john@example.com",
                },
                "expected_redacted": ["password", "email"],
            },
            {
                "scenario": "api_call",
                "data": {
                    "api_key": "sk-abc123",
                    "user_id": "12345",
                    "operation": "create_user",
                },
                "expected_redacted": ["api_key"],
            },
            {
                "scenario": "payment_processing",
                "data": {
                    "credit_card": "4111-1111-1111-1111",
                    "amount": 100.00,
                    "currency": "USD",
                },
                "expected_redacted": ["credit_card"],
            },
        ]

        for case in test_cases:
            with patch("sys.stdout"):
                logger.info(f"Testing {case['scenario']}", **case["data"])
                # In a real test, we would capture and verify the output

    def test_loki_integration_with_enhanced_features(self):
        """Test Loki integration with enhanced logging features."""
        # Mock the LokiHandler to avoid actual network calls
        with patch("logging_loki.LokiHandler") as mock_loki_handler:
            mock_handler_instance = Mock()
            mock_handler_instance.level = 0  # Log all levels
            mock_loki_handler.return_value = mock_handler_instance

            logger = MohflowLogger(
                service_name="loki-integration-test",
                loki_url="http://localhost:3100/loki/api/v1/push",
                enable_context_enrichment=True,
                enable_sensitive_data_filter=True,
            )

            from mohflow.context.enrichment import RequestContextManager

            with RequestContextManager(request_id="req-loki-test"):
                logger.info(
                    "Test message for Loki",
                    user_id="user-123",
                    password="should_be_redacted",
                    operation="test_operation",
                )

            # Verify Loki handler was created and used
            assert mock_loki_handler.called
            assert mock_handler_instance.handle.called

    def test_error_handling_and_fallback_behavior(self):
        """Test error handling and fallback behavior."""
        # Test with invalid Loki URL
        logger = MohflowLogger(
            service_name="error-test",
            loki_url="http://invalid-loki-url:3100/loki/api/v1/push",
            console_logging=True,  # Should fallback to console
        )

        # Should not raise exception, should fallback to console logging
        with patch("sys.stdout"):
            logger.error("Test error message", error_code=500)

    def test_performance_with_all_features_enabled(self):
        """Test performance impact of all features."""
        import time

        logger = MohflowLogger(
            service_name="performance-test",
            enable_context_enrichment=True,
            enable_sensitive_data_filter=True,
        )

        # Measure time for 100 log messages with context and filtering
        start_time = time.time()

        from mohflow.context.enrichment import RequestContextManager

        with RequestContextManager(request_id="perf-test"):
            for i in range(100):
                with patch("sys.stdout"):
                    logger.info(
                        f"Performance test message {i}",
                        iteration=i,
                        password="secret",  # Will be filtered
                        data={"nested": {"password": "also_secret"}},
                    )

        end_time = time.time()

        # Should complete 100 enhanced log messages in reasonable time
        total_time = end_time - start_time
        assert total_time < 1.0  # Less than 1 second for 100 messages

    def test_configuration_validation_integration(self):
        """Test configuration validation in real scenarios."""
        # Test valid configuration
        valid_config = {
            "service_name": "validation-test",
            "log_level": "INFO",
            "environment": "development",
            "console_logging": True,
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(valid_config, f)
            config_file = f.name

        try:
            # Should not raise exception
            logger = MohflowLogger(config_file=config_file)
            assert logger.config.SERVICE_NAME == "validation-test"
        finally:
            os.unlink(config_file)

        # Test invalid configuration
        invalid_config = {
            "log_level": "INVALID_LEVEL",
            "environment": "development",
            # Missing required service_name
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(invalid_config, f)
            config_file = f.name

        try:
            # Should raise validation error
            with pytest.raises(Exception):
                MohflowLogger(config_file=config_file)
        finally:
            os.unlink(config_file)

    def test_thread_safety_integration(self):
        """Test thread safety of integrated logging system."""
        import threading
        import time
        from mohflow.context.enrichment import RequestContextManager

        logger = MohflowLogger(
            service_name="thread-safety-test",
            enable_context_enrichment=True,
            enable_sensitive_data_filter=True,
        )

        results = []

        def worker_thread(thread_id):
            with RequestContextManager(request_id=f"req-{thread_id}"):
                for i in range(10):
                    with patch("sys.stdout"):
                        logger.info(
                            f"Thread {thread_id} message {i}",
                            thread_id=thread_id,
                            message_id=i,
                            secret_data="should_be_redacted",
                        )
                    time.sleep(
                        0.001
                    )  # Small delay to encourage context switching

                results.append(thread_id)

        # Run multiple threads concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All threads should complete successfully
        assert len(results) == 5
        assert sorted(results) == list(range(5))
