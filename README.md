![Mohflow_scocial](https://drive.google.com/uc?id=1Pv5-WQszaB76FS4lKoU8Ptq25JmX8365)

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
- 🤖 **Auto-configuration** based on environment detection
- 📊 **Pre-built dashboard templates** for Grafana and Kibana
- 🔒 **Enhanced context awareness** with request correlation
- 🛡️ **Built-in security** with sensitive data filtering
- ⚙️ **JSON configuration** support with schema validation
- 🖥️ **CLI interface** for dynamic debugging and management
- 🔗 **Request correlation** for distributed tracing

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

### Basic Configuration

```python
logger = MohflowLogger(
    service_name="my-app",                                    # Required
    environment="production",                                 # Optional (default: "development")
    loki_url="http://localhost:3100/loki/api/v1/push",       # Optional (default: None)
    log_level="INFO",                                        # Optional (default: "INFO")
    console_logging=True,                                    # Optional (default: True)
    file_logging=False,                                      # Optional (default: False)
    log_file_path="logs/app.log",                           # Required if file_logging=True
    enable_auto_config=False,                               # Optional (default: False)
    enable_context_enrichment=True,                         # Optional (default: True)
    enable_sensitive_data_filter=True                       # Optional (default: True)
)
```

### JSON Configuration

Create a `mohflow_config.json` file for advanced configuration:

```json
{
  "service_name": "my-app",
  "environment": "production",
  "log_level": "INFO",
  "console_logging": true,
  "file_logging": true,
  "log_file_path": "logs/app.log",
  "loki_url": "http://localhost:3100/loki/api/v1/push",
  "context_enrichment": {
    "include_timestamp": true,
    "include_system_info": true,
    "include_request_context": true
  },
  "sensitive_data_filter": {
    "enabled": true,
    "redaction_text": "[REDACTED]",
    "patterns": ["password", "token", "secret"]
  }
}
```

Use the JSON configuration:

```python
logger = MohflowLogger(config_file="mohflow_config.json")
```

### Auto-Configuration

Enable automatic environment detection and configuration:

```python
# Auto-detects AWS, GCP, Azure, Kubernetes, Docker, etc.
logger = MohflowLogger(
    service_name="my-app",
    enable_auto_config=True
)
```

## Advanced Features

### CLI Interface

MohFlow includes a powerful CLI for debugging and management:

```bash
# Basic usage
python -m mohflow.cli --service-name "my-app" --log-level DEBUG

# Validate configuration
python -m mohflow.cli --validate-config --config-file config.json

# Interactive debugging session
python -m mohflow.cli --interactive --service-name "my-app"

# Test logging functionality
python -m mohflow.cli --test --service-name "my-app" --loki-url "http://localhost:3100"
```

### Context Enrichment and Request Correlation

Automatically enrich logs with system metadata and request correlation:

```python
from mohflow.context import set_request_context, get_correlation_id

# Set request context for distributed tracing
with set_request_context(request_id="req-123", user_id="user-456"):
    logger.info("Processing request")  # Automatically includes request context
    
    # Get correlation ID for external service calls
    correlation_id = get_correlation_id()
    # Pass correlation_id to external services
```

### Dashboard Templates

Deploy pre-built dashboards for instant log visualization:

```python
from mohflow.templates import deploy_grafana_dashboard, deploy_kibana_dashboard

# Deploy Grafana dashboard
deploy_grafana_dashboard(
    template_name="application_logs",
    grafana_url="http://localhost:3000",
    api_key="your-api-key"
)

# Deploy Kibana dashboard
deploy_kibana_dashboard(
    template_name="error_tracking",
    kibana_url="http://localhost:5601"
)
```

### Security Features

Built-in sensitive data filtering:

```python
# Sensitive data is automatically redacted
logger.info("User login", password="secret123", token="abc123")
# Output: {"message": "User login", "password": "[REDACTED]", "token": "[REDACTED]"}

# Customize sensitive patterns
logger = MohflowLogger(
    service_name="my-app",
    enable_sensitive_data_filter=True
)
```

## Examples

### FastAPI Integration with Enhanced Features

```python
from fastapi import FastAPI, Request
from mohflow import MohflowLogger
from mohflow.context import set_request_context
import uuid

app = FastAPI()

# Initialize with auto-configuration and enhanced features
logger = MohflowLogger(
    service_name="fastapi-app",
    environment="production",
    enable_auto_config=True,  # Auto-detect cloud environment
    enable_context_enrichment=True,
    enable_sensitive_data_filter=True
)

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    
    # Set request context for correlation
    with set_request_context(request_id=request_id, path=str(request.url.path)):
        logger.info("Request started", method=request.method)
        response = await call_next(request)
        logger.info("Request completed", status_code=response.status_code)
        return response

@app.get("/")
async def root():
    logger.info("Processing root request")
    return {"message": "Hello World"}

@app.post("/login")
async def login(username: str, password: str):
    # Password automatically redacted in logs
    logger.info("Login attempt", username=username, password=password)
    return {"status": "success"}
```

### Cloud-Native Deployment

```python
# Auto-configure for cloud environments (AWS, GCP, Azure, K8s)
logger = MohflowLogger(
    service_name="cloud-app",
    enable_auto_config=True,  # Detects cloud provider automatically
    config_file="config.json"  # Load additional config from file
)

# Enhanced logging with automatic context enrichment
logger.info("Service started")  # Includes hostname, process_id, thread_id, etc.
```

### Microservices with Request Correlation

```python
import requests
from mohflow import MohflowLogger
from mohflow.context import set_request_context, get_correlation_id

logger = MohflowLogger(service_name="user-service", enable_auto_config=True)

def process_user_request(user_id: str):
    with set_request_context(request_id=f"user-{user_id}", user_id=user_id):
        logger.info("Processing user request")
        
        # Get correlation ID for downstream services
        correlation_id = get_correlation_id()
        
        # Call another service with correlation
        response = requests.post(
            "http://payment-service/process",
            headers={"X-Correlation-ID": correlation_id},
            json={"user_id": user_id}
        )
        
        logger.info("Payment processed", payment_status=response.status_code)
```

### Configuration Management

```python
# Use JSON configuration for complex setups
logger = MohflowLogger(config_file="production_config.json")

# Override specific settings at runtime
logger = MohflowLogger(
    config_file="base_config.json",
    environment="staging",  # Override environment
    log_level="DEBUG"       # Override log level
)
```

## Log Output Format

Logs are output in enriched JSON format for comprehensive observability:

### Basic Log Format
```json
{
    "timestamp": "2025-09-11T18:30:00.123456+00:00",
    "level": "INFO",
    "service_name": "my-app",
    "message": "User logged in",
    "environment": "production",
    "user_id": 123,
    "process_id": 12345,
    "thread_id": 67890,
    "hostname": "app-server-01"
}
```

### Enhanced Log with Request Context
```json
{
    "timestamp": "2025-09-11T18:30:00.123456+00:00",
    "level": "INFO",
    "service_name": "user-service",
    "message": "Processing payment",
    "environment": "production",
    "request_id": "req-uuid-123",
    "correlation_id": "corr-uuid-456",
    "user_id": "user-789",
    "process_id": 12345,
    "thread_id": 67890,
    "hostname": "k8s-pod-abc123",
    "cloud_provider": "aws",
    "region": "us-east-1"
}
```

### Security-Filtered Log
```json
{
    "timestamp": "2025-09-11T18:30:00.123456+00:00",
    "level": "INFO",
    "service_name": "auth-service",
    "message": "Login attempt",
    "username": "john_doe",
    "password": "[REDACTED]",
    "api_key": "[REDACTED]",
    "ip_address": "192.168.1.100"
}
```

## Dashboard Templates

MohFlow includes pre-built dashboard templates for instant log visualization:

### Available Templates

- **application_logs**: General application logging dashboard
- **error_tracking**: Error monitoring and alerting dashboard
- **performance_metrics**: Performance and latency tracking
- **security_audit**: Security events and audit trail
- **request_correlation**: Distributed tracing visualization

### Quick Dashboard Deployment

```python
from mohflow.templates import list_available_templates, deploy_grafana_dashboard

# List all available templates
templates = list_available_templates()
print(f"Available templates: {templates}")

# Deploy to Grafana
deploy_grafana_dashboard(
    template_name="application_logs",
    grafana_url="http://localhost:3000",
    api_key="your-grafana-api-key",
    datasource_name="Loki"
)
```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/parijatmukherjee/mohflow.git
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

# Build package
make build
```

### CLI Development and Testing

```bash
# Test CLI functionality
python -m mohflow.cli --help

# Run interactive debugging session
python -m mohflow.cli --interactive --service-name "dev-app"

# Validate configuration files
python -m mohflow.cli --validate-config --config-file examples/config.json
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
