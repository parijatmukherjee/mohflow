#!/usr/bin/env python3
"""
MohFlow CLI module for dynamic configuration and debugging.
Provides CLI for runtime log level control and configuration.
"""

import argparse
import json
import logging
import sys
from typing import Dict, Any, Optional
from mohflow import MohflowLogger


class MohflowCLI:
    """Command-line interface for MohFlow logging configuration"""

    def __init__(self):
        self.parser = self._create_parser()
        self.logger: Optional[MohflowLogger] = None

    def _create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser with all CLI options"""
        parser = argparse.ArgumentParser(
            description="MohFlow - Dynamic Logging Configuration CLI",
            prog="mohflow",
        )

        # Service configuration
        parser.add_argument(
            "--service-name",
            "-s",
            type=str,
            required=True,
            help="Service name for logging identification",
        )

        parser.add_argument(
            "--environment",
            "-e",
            type=str,
            default="development",
            choices=["development", "staging", "production"],
            help="Environment for logging context (default: development)",
        )

        # Log level configuration
        parser.add_argument(
            "--log-level",
            "-l",
            type=str,
            default="INFO",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            help="Set log level (default: INFO)",
        )

        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable debug mode (equivalent to --log-level DEBUG)",
        )

        # Output configuration
        parser.add_argument(
            "--console",
            action="store_true",
            default=True,
            help="Enable console logging (default: true)",
        )

        parser.add_argument(
            "--no-console", action="store_true", help="Disable console logging"
        )

        parser.add_argument(
            "--file-logging", action="store_true", help="Enable file logging"
        )

        parser.add_argument(
            "--log-file",
            "-f",
            type=str,
            help="Log file path (required if --file-logging is used)",
        )

        # Loki configuration
        parser.add_argument(
            "--loki-url",
            type=str,
            help="Loki endpoint URL for centralized logging",
        )

        # Configuration file
        parser.add_argument(
            "--config", "-c", type=str, help="Path to JSON configuration file"
        )

        # Dynamic debugging
        parser.add_argument(
            "--interactive",
            "-i",
            action="store_true",
            help="Start interactive debugging session",
        )

        # Testing and validation
        parser.add_argument(
            "--test-logging",
            action="store_true",
            help="Test logging configuration with sample messages",
        )

        parser.add_argument(
            "--validate-config",
            action="store_true",
            help="Validate configuration without starting logger",
        )

        return parser

    def load_config_from_file(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            print(f"✅ Configuration loaded from {config_path}")
            return config
        except FileNotFoundError:
            print(f"❌ Configuration file not found: {config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in configuration file: {e}")
            sys.exit(1)

    def merge_config(
        self, file_config: Dict[str, Any], cli_args: argparse.Namespace
    ) -> Dict[str, Any]:
        """Merge file config with CLI arguments (CLI precedence)"""
        config = file_config.copy()

        # CLI arguments override file config
        if cli_args.service_name:
            config["service_name"] = cli_args.service_name
        if cli_args.environment != "development":
            config["environment"] = cli_args.environment
        if cli_args.debug:
            config["log_level"] = "DEBUG"
        elif cli_args.log_level != "INFO":
            config["log_level"] = cli_args.log_level
        if cli_args.loki_url:
            config["loki_url"] = cli_args.loki_url
        if cli_args.file_logging:
            config["file_logging"] = True
        if cli_args.log_file:
            config["log_file_path"] = cli_args.log_file
        if cli_args.no_console:
            config["console_logging"] = False

        return config

    def validate_config(self, config_file: str) -> bool:
        """Validate configuration file"""
        try:
            config = self.load_config_from_file(config_file)
            return self.validate_configuration(config)
        except Exception:
            return False

    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """Validate configuration dictionary (alias method)"""
        return self._validate_config_dict(config)

    def _validate_config_dict(self, config: Dict[str, Any]) -> bool:
        """Validate logging configuration"""
        try:
            # Check required fields
            if "service_name" not in config:
                print("❌ Missing required field: service_name")
                return False

            # Validate file logging configuration
            if config.get("file_logging", False) and not config.get(
                "log_file_path"
            ):
                print("❌ File logging enabled but no log_file_path specified")
                return False

            # Validate log level
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            log_level = config.get("log_level", "INFO").upper()
            if log_level not in valid_levels:
                print(
                    f"❌ Invalid log level: {log_level}. "
                    f"Valid options: {valid_levels}"
                )
                return False

            print("✅ Configuration validation passed")
            return True

        except Exception as e:
            print(f"❌ Configuration validation error: {e}")
            return False

    def create_logger(self, args) -> MohflowLogger:
        """Create MohFlow logger (primary method)"""
        return self._create_logger_from_args(args)

    def _create_logger_from_args(self, args) -> MohflowLogger:
        """Create MohFlow logger from args"""
        try:
            # Build logger arguments, excluding None values
            logger_kwargs = {
                "service_name": args.service_name,
                "environment": getattr(args, "environment", "development"),
                "log_level": getattr(args, "log_level", "INFO"),
                "enable_auto_config": getattr(args, "auto_config", False),
            }
            
            # Only add loki_url if it's not None
            loki_url = getattr(args, "loki_url", None)
            if loki_url is not None:
                logger_kwargs["loki_url"] = loki_url
                
            # Only add config_file if it's not None
            config_file = getattr(args, "config_file", None)
            if config_file is not None:
                logger_kwargs["config_file"] = config_file
            
            logger = MohflowLogger(**logger_kwargs)
            print(f"✅ Logger created for service: {args.service_name}")
            return logger

        except Exception as e:
            print(f"❌ Failed to create logger: {e}")
            sys.exit(1)

    def test_logging_functionality(self, args) -> None:
        """Test logging functionality (primary method)"""
        return self._test_logging_impl(args)

    def _test_logging_impl(self, args) -> None:
        """Test logging functionality with sample messages"""
        print("🧪 Testing logging functionality...")

        # Create logger from args
        logger = self.create_logger(args)

        # Test different log levels
        logger.debug("This is a debug message")
        logger.info("This is an info message", test=True, component="cli")
        logger.warning("This is a warning message", warning_type="test")
        logger.error(
            "This is an error message", error_code=500, component="test"
        )

        print("✅ Logging test completed")

    def interactive_session(self, logger: MohflowLogger):
        """Start interactive debugging session"""
        print("🔧 Starting interactive debugging session...")
        print("Commands: debug, info, warning, error, level <LEVEL>, quit")

        while True:
            try:
                command = input("mohflow> ").strip().lower()
                if self._handle_command(command, logger):
                    break
            except (KeyboardInterrupt, EOFError):
                break

        print("\n👋 Interactive session ended")

    def _handle_command(self, command: str, logger: MohflowLogger) -> bool:
        """Handle interactive command. Returns True if should exit."""
        if command in ["quit", "exit"]:
            return True

        if command in ["debug", "info", "warning", "error"]:
            getattr(logger, command)(f"Interactive {command} message")
            return False

        if command.startswith("level "):
            self._handle_level_command(command, logger)
            return False

        print(
            "Unknown command. Available: debug, info, warning, "
            "error, level <LEVEL>, quit"
        )
        return False

    def _handle_level_command(self, command: str, logger: MohflowLogger):
        """Handle log level change command"""
        level = command.split(" ", 1)[1].upper()
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if level in valid_levels:
            logger.logger.setLevel(getattr(logging, level))
            print(f"Log level changed to {level}")
        else:
            print(
                "Invalid log level. Use: DEBUG, INFO, WARNING, "
                "ERROR, CRITICAL"
            )

    def run(self, args: Optional[list] = None) -> int:
        """Main CLI execution"""
        parsed_args = self.parser.parse_args(args)

        # Load configuration
        config = {}
        if parsed_args.config:
            config = self.load_config_from_file(parsed_args.config)

        # Merge with CLI arguments
        final_config = self.merge_config(config, parsed_args)

        # Add CLI-only arguments to config
        if not final_config.get("service_name"):
            final_config["service_name"] = parsed_args.service_name

        # Validate configuration
        if parsed_args.validate_config:
            return 0 if self.validate_configuration(final_config) else 1

        if not self.validate_configuration(final_config):
            return 1

        # Create logger
        self.logger = self.create_logger(final_config)

        # Test logging if requested
        if parsed_args.test_logging:
            self.test_logging(self.logger)

        # Start interactive session if requested
        if parsed_args.interactive:
            self.interactive_session(self.logger)

        return 0


def main():
    """Entry point for CLI"""
    cli = MohflowCLI()
    return cli.run()


if __name__ == "__main__":
    sys.exit(main())
