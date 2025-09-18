# mohflow Development Guidelines

Auto-generated from feature plans. Last updated: 2025-09-18

## Active Technologies
- Python 3.8+ (logging library)
- pytest (TDD testing framework)
- pydantic (configuration validation)
- opentelemetry-api (distributed tracing)

## Project Structure
```
src/mohflow/
├── context/filters.py      # Sensitive data filtering (001-there-is-an)
├── static_config.py        # Configuration constants
├── logger/base.py          # Logger initialization
tests/
├── test_context/
│   └── test_filters.py     # Filter tests (TDD approach)
```

## TDD Commands
```bash
# Run tests (follow TDD: write failing tests first)
PYTHONPATH=src python3 -m pytest tests/test_context/test_filters.py -v

# Run specific test
PYTHONPATH=src python3 -m pytest tests/test_context/test_filters.py::TestSensitiveDataFilter::test_tracing_field_exemptions -v

# Check code quality
make format
make lint
```

## Code Style
- Follow constitutional TDD approach: failing tests first, minimal implementation, refactor
- Maintain backward compatibility for all existing APIs
- Use type hints for all new code
- Add comprehensive docstrings with examples

## Recent Changes
- 001-there-is-an: Enhanced sensitive data filter with tracing field exemptions for improved observability

## Current Feature: Enhanced Sensitive Data Filter (001-there-is-an)

### Context
Fixing issue where `correlation_id`, `request_id`, `trace_id` get incorrectly redacted by sensitive data filter, breaking distributed tracing observability.

### Key Requirements
- Preserve tracing fields while maintaining security
- Add configurable exemptions (exclude_tracing_fields parameter)
- Follow TDD approach: write comprehensive tests first
- Maintain 100% backward compatibility
- Zero new dependencies

### Implementation Notes
- Modify `src/mohflow/context/filters.py:SensitiveDataFilter` class
- Add context-aware field classification logic
- Implement built-in tracing field exemptions
- Add configuration options to MohflowLogger constructor

### Testing Priority
1. Write failing tests for all new functionality FIRST
2. Ensure existing tests continue to pass (regression testing)
3. Test edge cases: nested data, performance, configuration validation
4. Verify tracing fields preserved while auth fields redacted

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->