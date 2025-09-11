"""Tests for CLI interface module."""

import pytest
import io
import sys
from unittest.mock import Mock, patch, MagicMock
from mohflow.cli import MohflowCLI, main
from mohflow import MohflowLogger


class TestMohflowCLI:
    """Test cases for MohflowCLI class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cli = MohflowCLI()

    def test_cli_initialization(self):
        """Test CLI initialization."""
        assert self.cli is not None
        assert hasattr(self.cli, 'create_logger')
        assert hasattr(self.cli, 'validate_config')

    @patch('mohflow.cli.MohflowLogger')
    def test_create_logger_basic(self, mock_logger_class):
        """Test basic logger creation."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        args = Mock()
        args.service_name = "test-service"
        args.log_level = "INFO"
        args.environment = "development"
        args.config_file = None
        args.loki_url = None
        args.auto_config = False

        logger = self.cli.create_logger(args)

        mock_logger_class.assert_called_once_with(
            service_name="test-service",
            log_level="INFO",
            environment="development",
            enable_auto_config=False
        )
        assert logger == mock_logger

    @patch('mohflow.cli.MohflowLogger')
    def test_create_logger_with_config_file(self, mock_logger_class):
        """Test logger creation with config file."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        args = Mock()
        args.service_name = "test-service"
        args.log_level = "DEBUG"
        args.environment = "production"
        args.config_file = "config.json"
        args.loki_url = "http://localhost:3100"
        args.auto_config = True

        logger = self.cli.create_logger(args)

        mock_logger_class.assert_called_once_with(
            service_name="test-service",
            log_level="DEBUG",
            environment="production",
            config_file="config.json",
            loki_url="http://localhost:3100",
            enable_auto_config=True
        )

    @patch('builtins.open')
    @patch('json.load')
    def test_validate_config_valid_file(self, mock_json_load, mock_open):
        """Test validation of valid config file."""
        mock_json_load.return_value = {
            "service_name": "test-service",
            "log_level": "INFO"
        }

        result = self.cli.validate_config("valid_config.json")

        assert result is True
        mock_open.assert_called_once_with("valid_config.json", 'r')

    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_validate_config_file_not_found(self, mock_open):
        """Test validation with missing config file."""
        result = self.cli.validate_config("missing_config.json")

        assert result is False

    @patch('builtins.open')
    @patch('json.load', side_effect=ValueError("Invalid JSON"))
    def test_validate_config_invalid_json(self, mock_json_load, mock_open):
        """Test validation with invalid JSON."""
        result = self.cli.validate_config("invalid_config.json")

        assert result is False

    @patch('mohflow.cli.MohflowLogger')
    def test_test_logging_functionality(self, mock_logger_class):
        """Test logging functionality testing."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger

        args = Mock()
        args.service_name = "test-service"
        args.log_level = "INFO"
        args.environment = "development"
        args.config_file = None
        args.loki_url = None
        args.auto_config = False

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            self.cli.test_logging_functionality(args)

            # Verify logger was created and test messages were logged
            mock_logger_class.assert_called_once()
            mock_logger.info.assert_called()
            mock_logger.warning.assert_called()
            mock_logger.error.assert_called()

            output = mock_stdout.getvalue()
            assert "Testing logging functionality" in output
            assert "Logging test completed" in output

    @patch('builtins.input')
    @patch('mohflow.cli.MohflowLogger')
    def test_interactive_session_help(self, mock_logger_class, mock_input):
        """Test interactive session help command."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        
        # Simulate user input: help, then quit
        mock_input.side_effect = ['help', 'quit']

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            self.cli.interactive_session(mock_logger)

            output = mock_stdout.getvalue()
            assert "Available commands:" in output
            assert "help" in output
            assert "quit" in output

    @patch('builtins.input')
    @patch('mohflow.cli.MohflowLogger')
    def test_interactive_session_log_commands(self, mock_logger_class, mock_input):
        """Test interactive session log commands."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        
        # Simulate user input: log commands, then quit
        mock_input.side_effect = [
            'log info "Test message"',
            'log error "Error message"',
            'quit'
        ]

        self.cli.interactive_session(mock_logger)

        # Verify log methods were called
        mock_logger.info.assert_called_with("Test message")
        mock_logger.error.assert_called_with("Error message")

    @patch('builtins.input')
    @patch('mohflow.cli.MohflowLogger')
    def test_interactive_session_level_command(self, mock_logger_class, mock_input):
        """Test interactive session level change command."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        
        # Simulate user input: change level, then quit
        mock_input.side_effect = ['level DEBUG', 'quit']

        with patch('sys.stdout', new_callable=io.StringIO):
            self.cli.interactive_session(mock_logger)

    @patch('builtins.input')
    @patch('mohflow.cli.MohflowLogger')
    def test_interactive_session_status_command(self, mock_logger_class, mock_input):
        """Test interactive session status command."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        mock_logger.config = Mock()
        mock_logger.config.service_name = "test-service"
        mock_logger.config.log_level = "INFO"
        
        # Simulate user input: status, then quit
        mock_input.side_effect = ['status', 'quit']

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            self.cli.interactive_session(mock_logger)

            output = mock_stdout.getvalue()
            assert "Service Name: test-service" in output
            assert "Log Level: INFO" in output

    @patch('builtins.input')
    @patch('mohflow.cli.MohflowLogger')
    def test_interactive_session_invalid_command(self, mock_logger_class, mock_input):
        """Test interactive session with invalid command."""
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        
        # Simulate user input: invalid command, then quit
        mock_input.side_effect = ['invalid_command', 'quit']

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            self.cli.interactive_session(mock_logger)

            output = mock_stdout.getvalue()
            assert "Unknown command" in output

    @patch('argparse.ArgumentParser.parse_args')
    @patch('mohflow.cli.MohflowCLI')
    def test_main_validate_config(self, mock_cli_class, mock_parse_args):
        """Test main function with validate config option."""
        mock_cli = Mock()
        mock_cli_class.return_value = mock_cli
        mock_cli.validate_config.return_value = True

        args = Mock()
        args.validate_config = True
        args.config_file = "config.json"
        args.interactive = False
        args.test = False
        mock_parse_args.return_value = args

        with patch('sys.stdout', new_callable=io.StringIO):
            main()

        mock_cli.validate_config.assert_called_once_with("config.json")

    @patch('argparse.ArgumentParser.parse_args')
    @patch('mohflow.cli.MohflowCLI')
    def test_main_interactive_mode(self, mock_cli_class, mock_parse_args):
        """Test main function with interactive mode."""
        mock_cli = Mock()
        mock_cli_class.return_value = mock_cli
        mock_logger = Mock()
        mock_cli.create_logger.return_value = mock_logger

        args = Mock()
        args.validate_config = False
        args.interactive = True
        args.test = False
        args.service_name = "test-service"
        mock_parse_args.return_value = args

        main()

        mock_cli.create_logger.assert_called_once_with(args)
        mock_cli.interactive_session.assert_called_once_with(mock_logger)

    @patch('argparse.ArgumentParser.parse_args')
    @patch('mohflow.cli.MohflowCLI')
    def test_main_test_mode(self, mock_cli_class, mock_parse_args):
        """Test main function with test mode."""
        mock_cli = Mock()
        mock_cli_class.return_value = mock_cli

        args = Mock()
        args.validate_config = False
        args.interactive = False
        args.test = True
        args.service_name = "test-service"
        mock_parse_args.return_value = args

        main()

        mock_cli.test_logging_functionality.assert_called_once_with(args)

    @patch('argparse.ArgumentParser.parse_args')
    def test_main_missing_service_name(self, mock_parse_args):
        """Test main function with missing service name."""
        args = Mock()
        args.validate_config = False
        args.interactive = True
        args.test = False
        args.service_name = None
        mock_parse_args.return_value = args

        with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
            with pytest.raises(SystemExit):
                main()

            output = mock_stderr.getvalue()
            assert "service-name is required" in output

    def test_cli_argument_parsing(self):
        """Test CLI argument parsing."""
        # This would test the actual argument parser setup
        # but requires mocking sys.argv or using subprocess
        pass