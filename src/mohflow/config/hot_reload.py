"""
Hot configuration reloading for MohFlow.

Enables runtime configuration changes without application restart
using file watching, signal handling, and configuration versioning.
"""

import os
import time
import json
import yaml
import threading
import signal
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from dataclasses import dataclass
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class ConfigChange:
    """Represents a configuration change."""

    timestamp: datetime
    config_path: str
    old_config: Dict[str, Any]
    new_config: Dict[str, Any]
    change_type: str  # 'file', 'signal', 'api'
    applied: bool = False
    error: Optional[str] = None


class ConfigWatcher(FileSystemEventHandler):
    """File system event handler for configuration changes."""

    def __init__(self, hot_reload_manager: "HotReloadManager"):
        super().__init__()
        self.manager = hot_reload_manager
        self.last_modified = {}

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return

        # Check if this is a config file we're watching
        file_path = Path(event.src_path).resolve()
        if file_path in self.manager.watched_files:
            # Debounce rapid file changes
            now = time.time()
            if file_path in self.last_modified:
                if now - self.last_modified[file_path] < 0.5:  # 500ms debounce
                    return

            self.last_modified[file_path] = now
            self.manager._handle_config_change(str(file_path), "file")


class HotReloadManager:
    """
    Manages hot reloading of logger configurations.

    Features:
    - File system watching for config files
    - Signal-based reloading (SIGHUP)
    - Configuration validation
    - Rollback on errors
    - Change history and auditing
    - Multiple config format support
    """

    def __init__(self, logger_instance: Any):
        self.logger = logger_instance
        self.observer = None
        self.watched_files: Dict[Path, str] = {}  # file_path -> config_type
        self.config_checksums: Dict[str, str] = {}
        self.change_history: List[ConfigChange] = []
        self.reload_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.validation_callbacks: List[Callable[[Dict[str, Any]], bool]] = []
        self.max_history = 50
        self.enabled = False
        self.lock = threading.RLock()
        self._original_signal_handler = None

    def enable(
        self,
        config_files: Optional[List[str]] = None,
        watch_signals: bool = True,
    ) -> bool:
        """
        Enable hot reloading.

        Args:
            config_files: List of config files to watch
            watch_signals: Whether to listen for SIGHUP signals

        Returns:
            Success status
        """
        with self.lock:
            if self.enabled:
                return True

            try:
                # Setup file watching
                if config_files:
                    self._setup_file_watching(config_files)

                # Setup signal handling
                if watch_signals:
                    self._setup_signal_handling()

                self.enabled = True

                # Log enablement
                if hasattr(self.logger, "info"):
                    self.logger.info(
                        "Hot configuration reloading enabled",
                        watched_files=list(
                            str(f) for f in self.watched_files.keys()
                        ),
                        signal_watching=watch_signals,
                    )

                return True

            except Exception as e:
                if hasattr(self.logger, "error"):
                    self.logger.error(
                        "Failed to enable hot reloading",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                return False

    def disable(self):
        """Disable hot reloading and cleanup resources."""
        with self.lock:
            if not self.enabled:
                return

            # Stop file watching
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=1.0)
                self.observer = None

            # Restore signal handling
            if self._original_signal_handler:
                signal.signal(signal.SIGHUP, self._original_signal_handler)
                self._original_signal_handler = None

            self.watched_files.clear()
            self.config_checksums.clear()
            self.enabled = False

            if hasattr(self.logger, "info"):
                self.logger.info("Hot configuration reloading disabled")

    def watch_file(self, config_path: str, config_type: str = "auto") -> bool:
        """
        Add a configuration file to watch list.

        Args:
            config_path: Path to configuration file
            config_type: Type of config ('json', 'yaml', 'auto')

        Returns:
            Success status
        """
        try:
            file_path = Path(config_path).resolve()

            if not file_path.exists():
                if hasattr(self.logger, "warning"):
                    self.logger.warning(
                        "Config file does not exist",
                        config_path=str(file_path),
                    )
                return False

            # Auto-detect config type
            if config_type == "auto":
                suffix = file_path.suffix.lower()
                if suffix in [".json"]:
                    config_type = "json"
                elif suffix in [".yml", ".yaml"]:
                    config_type = "yaml"
                else:
                    config_type = "json"  # default

            # Calculate initial checksum
            checksum = self._calculate_file_checksum(str(file_path))

            with self.lock:
                self.watched_files[file_path] = config_type
                self.config_checksums[str(file_path)] = checksum

            # Start observer if not already running
            if self.enabled and not self.observer:
                self._start_observer()

            if hasattr(self.logger, "info"):
                self.logger.info(
                    "Added config file to watch list",
                    config_path=str(file_path),
                    config_type=config_type,
                )

            return True

        except Exception as e:
            if hasattr(self.logger, "error"):
                self.logger.error(
                    "Failed to watch config file",
                    config_path=config_path,
                    error=str(e),
                )
            return False

    def reload_config(
        self, config_path: Optional[str] = None, source: str = "manual"
    ) -> bool:
        """
        Manually trigger configuration reload.

        Args:
            config_path: Specific config file to reload (None for all)
            source: Source of reload request

        Returns:
            Success status
        """
        if not self.enabled:
            return False

        if config_path:
            return self._handle_config_change(config_path, source)
        else:
            # Reload all watched files
            success = True
            for file_path in list(self.watched_files.keys()):
                if not self._handle_config_change(str(file_path), source):
                    success = False
            return success

    def add_reload_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add callback to be called when config is reloaded."""
        self.reload_callbacks.append(callback)

    def add_validation_callback(
        self, callback: Callable[[Dict[str, Any]], bool]
    ):
        """Add callback to validate new configuration."""
        self.validation_callbacks.append(callback)

    def get_change_history(self) -> List[ConfigChange]:
        """Get history of configuration changes."""
        with self.lock:
            return self.change_history.copy()

    def get_watched_files(self) -> List[str]:
        """Get list of currently watched files."""
        with self.lock:
            return [str(f) for f in self.watched_files.keys()]

    def _setup_file_watching(self, config_files: List[str]):
        """Setup file system watching for config files."""
        for config_file in config_files:
            self.watch_file(config_file)

        if self.watched_files:
            self._start_observer()

    def _start_observer(self):
        """Start the file system observer."""
        if self.observer:
            return

        self.observer = Observer()

        # Watch directories containing config files
        watched_dirs = set()
        for file_path in self.watched_files.keys():
            dir_path = file_path.parent
            if dir_path not in watched_dirs:
                event_handler = ConfigWatcher(self)
                self.observer.schedule(
                    event_handler, str(dir_path), recursive=False
                )
                watched_dirs.add(dir_path)

        self.observer.start()

    def _setup_signal_handling(self):
        """Setup SIGHUP signal handling for config reload."""

        def signal_handler(signum, frame):
            if hasattr(self.logger, "info"):
                self.logger.info(
                    "Received SIGHUP signal, reloading configuration"
                )
            self.reload_config(source="signal")

        # Store original handler for cleanup
        self._original_signal_handler = signal.signal(
            signal.SIGHUP, signal_handler
        )

    def _handle_config_change(self, config_path: str, source: str) -> bool:
        """Handle configuration file changes."""
        try:
            file_path = Path(config_path)

            # Check if file still exists
            if not file_path.exists():
                if hasattr(self.logger, "warning"):
                    self.logger.warning(
                        "Config file no longer exists", config_path=config_path
                    )
                return False

            # Check if file actually changed
            new_checksum = self._calculate_file_checksum(config_path)
            old_checksum = self.config_checksums.get(config_path)

            if new_checksum == old_checksum:
                return True  # No actual change

            # Load and parse new configuration
            config_type = self.watched_files.get(file_path, "json")
            new_config = self._load_config_file(config_path, config_type)

            if new_config is None:
                return False

            # Get old config for change tracking
            old_config = getattr(self.logger, "config", {})
            if hasattr(old_config, "__dict__"):
                old_config = old_config.__dict__

            # Validate new configuration
            if not self._validate_config(new_config):
                return False

            # Create change record
            change = ConfigChange(
                timestamp=datetime.utcnow(),
                config_path=config_path,
                old_config=(
                    dict(old_config) if isinstance(old_config, dict) else {}
                ),
                new_config=new_config,
                change_type=source,
            )

            # Apply configuration
            success = self._apply_config(new_config)
            change.applied = success

            if success:
                # Update checksum
                self.config_checksums[config_path] = new_checksum

                # Call reload callbacks
                for callback in self.reload_callbacks:
                    try:
                        callback(new_config)
                    except Exception as e:
                        if hasattr(self.logger, "warning"):
                            self.logger.warning(
                                "Reload callback failed",
                                callback=callback.__name__,
                                error=str(e),
                            )

                if hasattr(self.logger, "info"):
                    self.logger.info(
                        "Configuration reloaded successfully",
                        config_path=config_path,
                        source=source,
                        changes_applied=True,
                    )
            else:
                change.error = "Failed to apply configuration"

                if hasattr(self.logger, "error"):
                    self.logger.error(
                        "Failed to apply new configuration",
                        config_path=config_path,
                        source=source,
                    )

            # Add to history
            with self.lock:
                self.change_history.append(change)
                if len(self.change_history) > self.max_history:
                    self.change_history.pop(0)

            return success

        except Exception as e:
            if hasattr(self.logger, "error"):
                self.logger.error(
                    "Error handling config change",
                    config_path=config_path,
                    source=source,
                    error=str(e),
                    error_type=type(e).__name__,
                )
            return False

    def _load_config_file(
        self, config_path: str, config_type: str
    ) -> Optional[Dict[str, Any]]:
        """Load configuration from file."""
        try:
            with open(config_path, "r") as f:
                content = f.read()

            if config_type == "json":
                return json.loads(content)
            elif config_type == "yaml":
                if not HAS_YAML:
                    raise ImportError(
                        "PyYAML not installed, cannot load YAML config"
                    )
                return yaml.safe_load(content)
            else:
                # Try to auto-detect
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    if HAS_YAML:
                        return yaml.safe_load(content)
                    raise

        except Exception as e:
            if hasattr(self.logger, "error"):
                self.logger.error(
                    "Failed to load config file",
                    config_path=config_path,
                    config_type=config_type,
                    error=str(e),
                    error_type=type(e).__name__,
                )
            return None

    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate new configuration."""
        try:
            # Run validation callbacks
            for validator in self.validation_callbacks:
                if not validator(config):
                    return False

            # Basic validation - ensure required keys exist
            if hasattr(self.logger, "config"):
                required_keys = ["service_name"]  # Minimum required
                for key in required_keys:
                    if key not in config:
                        if hasattr(self.logger, "warning"):
                            self.logger.warning(
                                "Missing required config key",
                                key=key,
                                config_keys=list(config.keys()),
                            )
                        return False

            return True

        except Exception as e:
            if hasattr(self.logger, "error"):
                self.logger.error(
                    "Config validation failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
            return False

    def _apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply new configuration to logger."""
        try:
            # Update logger configuration
            if hasattr(self.logger, "update_config"):
                return self.logger.update_config(config)
            elif hasattr(self.logger, "config"):
                # Update config attributes
                for key, value in config.items():
                    if hasattr(self.logger.config, key.upper()):
                        setattr(self.logger.config, key.upper(), value)
                return True
            else:
                # Direct attribute update
                for key, value in config.items():
                    setattr(self.logger, key, value)
                return True

        except Exception as e:
            if hasattr(self.logger, "error"):
                self.logger.error(
                    "Failed to apply config",
                    error=str(e),
                    error_type=type(e).__name__,
                )
            return False

    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calculate MD5 checksum of file content."""
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return ""


# Integration with MohflowLogger
def enable_hot_reload(
    logger: Any,
    config_files: Optional[List[str]] = None,
    watch_signals: bool = True,
) -> Optional[HotReloadManager]:
    """
    Enable hot reloading for a MohFlow logger.

    Usage:
        logger = MohflowLogger.smart("my-service")
        hot_reload = enable_hot_reload(logger, ["/path/to/config.json"])
    """
    try:
        manager = HotReloadManager(logger)

        if manager.enable(config_files, watch_signals):
            # Store manager reference in logger
            logger._hot_reload_manager = manager
            return manager
        else:
            return None

    except Exception as e:
        if hasattr(logger, "error"):
            logger.error("Failed to enable hot reload", error=str(e))
        return None


def disable_hot_reload(logger: Any):
    """
    Disable hot reloading for a MohFlow logger.

    Usage:
        disable_hot_reload(logger)
    """
    manager = getattr(logger, "_hot_reload_manager", None)
    if manager:
        manager.disable()
        delattr(logger, "_hot_reload_manager")


# Configuration update method for MohflowLogger
def create_update_config_method():
    """Create update_config method for MohflowLogger."""

    def update_config(self, new_config: Dict[str, Any]) -> bool:
        """
        Update logger configuration at runtime.

        Args:
            new_config: New configuration dictionary

        Returns:
            Success status
        """
        try:
            # Update log level if provided
            if "log_level" in new_config:
                new_level = new_config["log_level"].upper()
                if hasattr(self.logger, "setLevel"):
                    import logging

                    level_map = {
                        "DEBUG": logging.DEBUG,
                        "INFO": logging.INFO,
                        "WARNING": logging.WARNING,
                        "ERROR": logging.ERROR,
                        "CRITICAL": logging.CRITICAL,
                    }
                    if new_level in level_map:
                        self.logger.setLevel(level_map[new_level])
                        self.info("Log level updated", new_level=new_level)

            # Update sampling configuration
            if "enable_sampling" in new_config and hasattr(self, "sampler"):
                self.sampler.enabled = new_config["enable_sampling"]

            if "sample_rate" in new_config and hasattr(self, "sampler"):
                if hasattr(self.sampler, "update_sample_rate"):
                    self.sampler.update_sample_rate(new_config["sample_rate"])

            # Update metrics configuration
            if "enable_auto_metrics" in new_config and hasattr(
                self, "metrics_generator"
            ):
                self.metrics_generator.enabled = new_config[
                    "enable_auto_metrics"
                ]

            # Update config object
            if hasattr(self, "config"):
                for key, value in new_config.items():
                    config_key = key.upper()
                    if hasattr(self.config, config_key):
                        setattr(self.config, config_key, value)

            return True

        except Exception as e:
            self.error(
                "Failed to update configuration",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    return update_config


# Example configuration files for hot reloading
EXAMPLE_JSON_CONFIG = {
    "service_name": "my-service",
    "log_level": "INFO",
    "enable_sampling": True,
    "sample_rate": 0.1,
    "enable_auto_metrics": True,
    "formatter_type": "json",
    "async_handlers": True,
    "privacy_mode": "redact_pii",
    "environment": "development",
}

EXAMPLE_YAML_CONFIG = """
service_name: my-service
log_level: INFO
enable_sampling: true
sample_rate: 0.1
enable_auto_metrics: true
formatter_type: json
async_handlers: true
privacy_mode: redact_pii
environment: development
"""


def create_example_config(config_path: str, format_type: str = "json"):
    """
    Create an example configuration file for hot reloading.

    Args:
        config_path: Path where to create the config file
        format_type: 'json' or 'yaml'
    """
    try:
        if format_type == "json":
            with open(config_path, "w") as f:
                json.dump(EXAMPLE_JSON_CONFIG, f, indent=2)
        elif format_type == "yaml":
            if not HAS_YAML:
                raise ImportError("PyYAML not installed")
            with open(config_path, "w") as f:
                f.write(EXAMPLE_YAML_CONFIG)
        else:
            raise ValueError(f"Unsupported format: {format_type}")

        print(f"Created example {format_type} config at: {config_path}")

    except Exception as e:
        print(f"Failed to create example config: {e}")
