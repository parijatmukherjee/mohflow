# Mohflow

Mohflow is a Python logging package that provides structured JSON logging with support for console output, file logging, and Grafana Loki integration. It's designed to be easy to use while providing powerful logging capabilities.

## 🚀 MohFlow Released: **[Now on PyPI!](https://pypi.org/project/mohflow/)**

## Status
[![Build](https://github.com/parijatmukherjee/mohflow/actions/workflows/ci.yml/badge.svg)](https://github.com/parijatmukherjee/mohflow/actions/workflows/ci.yml)

## Features

- 📋 Structured JSON logging for better log parsing
- 🚀 Simple setup with sensible defaults
- 🔄 Built-in Grafana Loki integration
- 📁 File logging support
- 🌍 Environment-based configuration
- 🔍 Rich context logging
- ⚡ Lightweight and performant

## Installation

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

## Configuration

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

## Examples

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
logger.info(
    "User logged in", 
    user_id=123,
    ip_address="127.0.0.1"
)
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
    "ip_address": "127.0.0.1"
}
```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/mohflow.git
cd mohflow

# Install development dependencies
make install
```

### Running Tests

```bash
# Run tests with coverage
make test

# Format code
make format

# Lint code
make lint
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
