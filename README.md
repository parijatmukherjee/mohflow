# MohFlow - Structured Logging for Python

[![CI](https://github.com/parijatmukherjee/mohflow/actions/workflows/ci.yml/badge.svg)](https://github.com/parijatmukherjee/mohflow/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/mohflow.svg)](https://badge.fury.io/py/mohflow)
[![Python Support](https://img.shields.io/pypi/pyversions/mohflow.svg)](https://pypi.org/project/mohflow/)
[![Code Quality](https://img.shields.io/badge/code%20quality-A+-brightgreen.svg)](https://github.com/parijatmukherjee/mohflow)
[![Lint Compliance](https://img.shields.io/badge/lint%20compliance-100%25-green.svg)](https://github.com/parijatmukherjee/mohflow)

**Python Versions**: 3.8, 3.9, 3.10, 3.11+

MohFlow is a Python structured logging library (JSON-first) that targets console, files, and aggregators (e.g., Loki). It's designed to be easy to use while providing powerful logging capabilities for modern Python applications.

## 🚀 Quickstart

### Installation
```bash
pip install mohflow
```

### Basic Usage
```python
from mohflow import MohflowLogger

# Create a logger instance
logger = MohflowLogger(service_name="my-app")

# Log structured data
logger.info("User action completed", user_id="123", action="login", success=True)
```

**Output:**
```json
{
  "timestamp": "2025-09-18T10:30:00.123456+00:00",
  "level": "INFO",
  "service": "my-app",
  "message": "User action completed",
  "user_id": "123",
  "action": "login",
  "success": true
}
```

## 🔒 Quality Gates

Before submitting any changes, ensure all quality gates pass locally:

```bash
make format    # Format code with black (must pass with zero errors)
make lint      # Lint code with flake8 (must pass with zero errors)
make test      # Run test suite with pytest (must pass all tests)
```

**Requirements:**
- All commands must execute with **zero errors** before PR submission
- GitHub Actions CI enforces the same standards
- Quality gates are **non-negotiable** for code acceptance

## 🧪 TDD Workflow

MohFlow follows **Test-Driven Development** (TDD) for all new features:

### 3-Step Process:
1. **Write failing test** → Create test that validates expected behavior
2. **Implement minimal code** → Write just enough code to make test pass
3. **Refactor** → Improve code while keeping tests green

### Example TDD Cycle:
```python
# tests/test_example.py
import pytest
from mohflow import MohflowLogger

def test_logger_creates_structured_output():
    """Test that logger produces JSON-structured output."""
    # 1. Write failing test (RED)
    logger = MohflowLogger(service_name="test")

    # 2. Implement feature to make test pass (GREEN)
    # Logger should be created successfully and not raise errors
    logger.info("test message", user_id="123")

    # 3. Refactor while keeping tests green (REFACTOR)
    assert logger.config.SERVICE_NAME == "test"
```

Run tests: `pytest tests/`

## 📋 Spec-Kit Workflow

For structured feature development, use the spec-kit process:

- **`/specify`** → Create feature specification with requirements and user stories
- **`/plan`** → Generate implementation plan with technical design and tasks
- **`/tasks`** → Create numbered, actionable tasks for implementation

**Example:**
```bash
/specify "Add user authentication to logging context"
/plan "Based on specification, create technical design"
/tasks "Generate specific implementation steps"
```

New specifications go in the `specs/` directory.

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

## 🏆 Code Quality & Production Readiness

MohFlow is built with enterprise-grade code quality standards:

- ✅ **100% Lint Compliance** - Zero flake8 violations across entire codebase
- ✅ **Type Safety** - Full type hints with mypy compatibility
- ✅ **Security Focused** - Built-in PII detection and sensitive data filtering
- ✅ **Performance Optimized** - Async handlers and high-throughput batching
- ✅ **Framework Integration** - Intelligent auto-detection for Django, FastAPI, Flask, and more
- ✅ **Production Tested** - Comprehensive test coverage with real-world scenarios
- ✅ **Clean Architecture** - Modular design with clear separation of concerns

### Recent Improvements (v1.0.0+)

- 🔧 **Enhanced Lint Compliance**: Resolved all code style violations for production readiness
- 🚀 **Optimized Performance**: Improved async handlers and reduced memory footprint
- 🔐 **Security Hardening**: Enhanced PII detection with compliance reporting
- 🎯 **Framework Detection**: Smarter auto-configuration for popular Python frameworks
- 🛠️ **Developer Experience**: Better error messages and debugging capabilities

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

### Configuration Precedence

MohFlow follows a clear configuration precedence order (highest to lowest priority):

1. **Runtime parameters** (direct function arguments)
2. **Environment variables** (prefixed with `MOHFLOW_`)
3. **JSON configuration file**
4. **Default values**

```python
# Example showing precedence
logger = MohflowLogger(
    config_file="config.json",        # Base configuration
    environment="staging",            # Overrides config file
    log_level="DEBUG"                 # Overrides environment variable
)
```

### Environment Variables

Configure MohFlow using environment variables:

```bash
export MOHFLOW_SERVICE_NAME="my-app"
export MOHFLOW_LOG_LEVEL="INFO"
export MOHFLOW_ENVIRONMENT="production"
export MOHFLOW_CONSOLE_LOGGING="true"
export MOHFLOW_LOKI_URL="http://loki:3100/loki/api/v1/push"

# For nested configurations
export MOHFLOW_CONTEXT_ENRICHMENT_INCLUDE_TIMESTAMP="true"
export MOHFLOW_SENSITIVE_DATA_FILTER_ENABLED="true"
```

```python
# Will automatically pick up environment variables
logger = MohflowLogger()  # service_name from MOHFLOW_SERVICE_NAME
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

## Enhanced Features

### Thread-Safe Context Management

MohFlow provides thread-safe context management for microservices and async applications:

```python
from mohflow.context.enrichment import RequestContextManager
from mohflow.context.correlation import get_correlation_id, set_correlation_id
import threading

def handle_request(request_id, user_id):
    # Each thread gets its own context
    with RequestContextManager(request_id=request_id, user_id=user_id):
        logger.info("Processing request")
        
        # Correlation ID is automatically generated and thread-local
        correlation_id = get_correlation_id()
        logger.info("Generated correlation", correlation_id=correlation_id)

# Multiple threads with independent contexts
for i in range(3):
    thread = threading.Thread(target=handle_request, args=(f"req-{i}", f"user-{i}"))
    thread.start()
```

### Sensitive Data Protection

Automatic detection and redaction of sensitive information:

```python
# Built-in patterns detect and redact sensitive data
logger.info("User registration", 
    username="john_doe",
    password="secret123",           # [REDACTED]
    email="john@example.com",       # [REDACTED] 
    credit_card="4111-1111-1111-1111",  # [REDACTED]
    api_key="sk-abc123def456"       # [REDACTED]
)

# Add custom sensitive patterns
logger.add_sensitive_field("internal_id")
logger.info("Processing", internal_id="12345")  # [REDACTED]
```

### Auto-Configuration with Environment Detection

Automatically configure logging based on your deployment environment:

```python
# Detects AWS, GCP, Azure, Kubernetes, Docker, etc.
logger = MohflowLogger(
    service_name="my-app",
    enable_auto_config=True  # Automatically configures based on environment
)

# Get detected environment information
env_info = logger.get_environment_info()
print(f"Running on: {env_info}")
# Output: {'cloud_provider': 'aws', 'region': 'us-east-1', 'environment_type': 'production'}
```

### Custom Context Enrichers

Add custom metadata to all log messages:

```python
import os

# Add custom enrichers
logger.add_custom_enricher("version", lambda: os.getenv("APP_VERSION", "unknown"))
logger.add_custom_enricher("build", lambda: os.getenv("BUILD_NUMBER", "dev"))

# All logs will now include version and build information
logger.info("Application started")  # Includes version and build fields
```

### Factory Methods for Common Use Cases

Convenient factory methods for quick setup:

```python
# Create logger with auto-configuration
logger = MohflowLogger.with_auto_config(
    service_name="my-app"
)

# Create logger from configuration file
logger = MohflowLogger.from_config_file(
    "config.json",
    log_level="DEBUG"  # Override specific settings
)
```

## Practical Usage Examples

### Complete Microservice Setup

```python
from mohflow import MohflowLogger
from mohflow.context.enrichment import RequestContextManager
from mohflow.context.correlation import get_correlation_id
import os
import uuid

# Initialize with full feature set
logger = MohflowLogger(
    service_name="payment-service",
    environment=os.getenv("ENVIRONMENT", "development"),
    enable_auto_config=True,           # Auto-detect cloud environment
    enable_context_enrichment=True,    # Add system metadata
    enable_sensitive_data_filter=True, # Protect sensitive data
    loki_url=os.getenv("LOKI_URL"),    # Optional Loki integration
)

def process_payment(user_id: str, amount: float, card_number: str):
    """Process payment with full observability"""
    request_id = str(uuid.uuid4())
    
    with RequestContextManager(
        request_id=request_id, 
        user_id=user_id,
        operation_name="process_payment"
    ):
        logger.info("Payment processing started", 
            amount=amount,
            currency="USD"
        )
        
        try:
            # Sensitive data is automatically redacted
            logger.debug("Payment details", 
                card_number=card_number,  # [REDACTED]
                amount=amount
            )
            
            # Simulate payment processing
            if amount > 0:
                # Get correlation ID for external service calls
                correlation_id = get_correlation_id()
                
                # Call external payment gateway
                # headers = {"X-Correlation-ID": correlation_id}
                
                logger.info("Payment processed successfully", 
                    transaction_id=f"txn_{request_id}",
                    status="completed"
                )
                return {"status": "success", "transaction_id": f"txn_{request_id}"}
            else:
                raise ValueError("Invalid amount")
                
        except Exception as e:
            logger.error("Payment processing failed", 
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise

# Usage
result = process_payment("user_123", 99.99, "4111-1111-1111-1111")
```

### Flask Application with Request Tracking

```python
from flask import Flask, request, g
from mohflow import MohflowLogger
from mohflow.context.enrichment import RequestContextManager
import uuid
import time

app = Flask(__name__)

# Initialize logger with auto-configuration
logger = MohflowLogger(
    service_name="flask-api",
    enable_auto_config=True,
    enable_context_enrichment=True,
    enable_sensitive_data_filter=True
)

@app.before_request
def before_request():
    """Set up request context for each request"""
    g.request_id = str(uuid.uuid4())
    g.start_time = time.time()

@app.after_request
def after_request(response):
    """Log request completion"""
    duration = time.time() - g.start_time
    logger.info("Request completed",
        method=request.method,
        path=request.path,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
        user_agent=request.headers.get('User-Agent')
    )
    return response

@app.route('/api/users/<user_id>')
def get_user(user_id):
    with RequestContextManager(
        request_id=g.request_id,
        user_id=user_id,
        operation_name="get_user"
    ):
        logger.info("Fetching user data")
        
        # Simulate database query
        user_data = {"id": user_id, "name": "John Doe"}
        
        logger.info("User data retrieved", user_found=True)
        return user_data

if __name__ == '__main__':
    app.run(debug=True)
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
from mohflow.context.enrichment import RequestContextManager
from mohflow.context.correlation import get_correlation_id

# Set request context for distributed tracing
with RequestContextManager(request_id="req-123", user_id="user-456"):
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
from mohflow.context.enrichment import RequestContextManager
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
    with RequestContextManager(request_id=request_id, path=str(request.url.path)):
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
from mohflow.context.enrichment import RequestContextManager, get_correlation_id

logger = MohflowLogger(service_name="user-service", enable_auto_config=True)

def process_user_request(user_id: str):
    with RequestContextManager(request_id=f"user-{user_id}", user_id=user_id):
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

# Lint code (100% compliant)
make lint

# Build package
make build
```

### Code Quality Standards

MohFlow maintains strict code quality standards:

```bash
# All code passes flake8 linting with zero violations
make lint  # ✅ 0 violations

# Type checking (when available)
mypy src/mohflow/

# Security scanning
bandit -r src/mohflow/
```

**Recent Quality Improvements:**

- 🎯 Resolved all 142 initial lint violations 
- 🔧 Fixed syntax errors and undefined variables
- 📏 Enforced 79-character line limits across entire codebase
- 🧹 Removed unused imports and variables
- 🏗️ Refactored complex functions for better maintainability
- 🔍 Enhanced f-string usage and blank line formatting

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

### Code Quality Requirements

Before submitting a pull request, please ensure:

1. **All tests pass**: `make test`
2. **Code is formatted**: `make format` 
3. **Linting passes**: `make lint` ✅ (zero violations required)
4. **Type hints are used** where appropriate
5. **Documentation is updated** for new features

We maintain 100% lint compliance - your code should pass `make lint` without any violations.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
