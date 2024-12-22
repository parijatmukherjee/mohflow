# Mohflow

Mohflow is a Python logging package that provides structured logging with minimal configuration. It supports console output, file logging, and Loki integration out of the box.

## Features

- 📋 Structured JSON logging
- 🚀 Simple setup with sensible defaults
- 🔄 Grafana Loki integration
- 📁 File logging support
- 🎯 Context-rich logging with extra fields
- 🌍 Environment-based configuration
- ⚡ Fast and lightweight

## Installation

Install using pip:

```bash
pip install mohflow
```

## Quick Start

Basic usage with console logging:

```python
from mohflow import MohflowLogger

# Initialize logger with minimal configuration
logger = MohflowLogger(service_name="my-app")

# Log messages
logger.info("Application started")
logger.error("An error occurred", error_code=500)
```

## Configuration Options

Mohflow can be configured in multiple ways:

```python
logger = MohflowLogger(
    service_name="my-app",                                    # Required
    environment="production",                                 # Optional (default: "development")
    loki_url="http://localhost:3100/loki/api/v1/push",       # Optional (default: None)
    log_level="INFO",                                        # Optional (default: "INFO")
    console_logging=True,                                    # Optional (default: True)
    file_logging=False,                                      # Optional (default: False)
    log_file_path="logs/app.log"                            # Required if file_logging=True
)
```

## Environment Variables

You can also configure Mohflow using environment variables:

```bash
MOHFLOW_SERVICE_NAME="my-app"
MOHFLOW_ENVIRONMENT="production"
MOHFLOW_LOKI_URL="http://localhost:3100/loki/api/v1/push"
MOHFLOW_LOG_LEVEL="INFO"
MOHFLOW_CONSOLE_LOGGING="true"
MOHFLOW_FILE_LOGGING="false"
MOHFLOW_LOG_FILE_PATH="logs/app.log"
```

## Usage Examples

### Basic Logging

```python
# Initialize logger
logger = MohflowLogger(service_name="my-app")

# Different log levels
logger.info("Information message")
logger.error("Error message")
logger.warning("Warning message")
logger.debug("Debug message")
```

### Logging with Context

```python
# Add extra fields to your logs
logger.info(
    "User logged in",
    user_id=123,
    ip_address="127.0.0.1",
    login_type="oauth"
)

# Log errors with stack trace
try:
    # Some code that might raise an exception
    raise ValueError("Invalid input")
except Exception as e:
    logger.error(
        "Operation failed",
        error=str(e),
        operation="user_login"
    )
```

### FastAPI Integration

```python
from fastapi import FastAPI
from mohflow import MohflowLogger

app = FastAPI()
logger = MohflowLogger(
    service_name="fastapi-app",
    environment="production",
    loki_url="http://localhost:3100/loki/api/v1/push"
)

@app.get("/")
async def root():
    logger.info(
        "Processing request",
        path="/",
        method="GET"
    )
    return {"message": "Hello World"}
```

### Loki Integration

```python
# Initialize with Loki support
logger = MohflowLogger(
    service_name="my-app",
    environment="production",
    loki_url="http://localhost:3100/loki/api/v1/push"
)

# Logs will be sent to both console and Loki
logger.info("This message goes to Loki!", task_id=123)
```

### File Logging

```python
# Initialize with file logging
logger = MohflowLogger(
    service_name="my-app",
    file_logging=True,
    log_file_path="logs/app.log"
)

logger.info("This message goes to the log file!")
```

## Log Output Format

Logs are output in JSON format for easy parsing:

```json
{
    "timestamp": "2024-12-22T10:30:00.123Z",
    "level": "INFO",
    "message": "User logged in",
    "service": "my-app",
    "environment": "production",
    "user_id": 123,
    "ip_address": "127.0.0.1",
    "login_type": "oauth"
}
```

## Error Handling

Mohflow provides custom exceptions for better error handling:

```python
from mohflow import MohflowError, ConfigurationError

try:
    logger = MohflowLogger(
        service_name="my-app",
        file_logging=True,
        # Missing log_file_path will raise ConfigurationError
    )
except ConfigurationError as e:
    print(f"Configuration error: {e}")
except MohflowError as e:
    print(f"General mohflow error: {e}")
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.