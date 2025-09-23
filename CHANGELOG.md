# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]



### Added
- Mohnitor auto-spun log viewer: Kibana-lite UI for structured JSON logs with automatic hub discovery
- Real-time log streaming with sub-150ms latency and live filtering capabilities
- Cross-service trace correlation supporting click-to-filter on trace identifiers
- Bounded in-memory buffer (50k events default) with configurable sizing
- Web-based UI accessible via local browser with export functionality (NDJSON format)
- Automatic hub failover and client discovery using file descriptors and health checks
- Browser automation test suite with Selenium WebDriver for comprehensive UI validation
- System metrics display including buffer usage, drop rates, and connected clients

### Changed
- Test organization restructured from scattered files to clean hierarchy (tests/unit/, tests/integration/, tests/ui/)
- README.md updated with comprehensive test suite details and browser automation testing capabilities
- Enhanced async test support with proper pytest-asyncio decorators
- Improved flake8 configuration for better code quality balance

### Fixed
- Missing async test decorators causing pytest collection failures
- Undefined variable errors in test scripts (missing sys imports)
- Bare except clauses updated to proper exception handling
- TestLogGenerator renamed to LogGenerator to avoid pytest collection confusion
- GitHub workflow now passes all quality gates (339 tests pass, 62 skip gracefully)

### Removed
- Root-level test files moved to proper test structure organization
- SECURITY.md (generic template with placeholder content)
- TECHNICAL_PLAN.md (outdated technical plan conflicting with current structure)
- benchmarks/README.md (specialized documentation not essential for core contributor workflow)

## [1.1.1] - 2025-09-18

### Added
- Workflow scaffolding and automation for feature planning & task generation (PR #25)
- Enhanced Sensitive Data Filter with tracing field exemptions: keeps correlation_id, request_id, trace_id while redacting sensitive data; comprehensive TDD coverage (PR #26)

### Changed
- Docs aligned with Constitution: TDD, Spec-Kit flow, Quality Gates (format/lint/test)
- CI cleanup: remove obsolete debug test step (from PR #26 follow-ups)

## [1.1.0] - 2025-09-18

### Added
- Enhanced Sensitive Data Filter with Tracing Field Exemptions
- Implementation planning and task generation workflows
- Major MohFlow enhancements with enterprise features

### Changed
- Recent improvements section in README
- Enhanced privacy and compliance features

### Fixed
- Various bug fixes and performance improvements

## [1.0.0] - 2025-08-29

### Added
- Initial stable release
- Structured JSON logging for Python applications
- Console, file, and Grafana Loki integration
- Environment-based configuration
- Rich context logging capabilities
- Auto-configuration based on environment detection
- Pre-built dashboard templates for Grafana and Kibana
- Enhanced context awareness with request correlation
- Built-in security with sensitive data filtering
- JSON configuration support with schema validation
- CLI interface for dynamic debugging and management

### Changed
- First major release establishing stable API

## [0.1.3] - 2025-06-27

### Added
- Performance optimizations
- Enhanced error handling

### Fixed
- Various stability improvements

## [0.1.2] - 2024-12-24

### Added
- Additional logging features
- Improved documentation

## [0.1.1] - 2024-12-24

### Added
- Initial public release
- Basic structured logging functionality

## [0.1.0] - 2024-12-22

### Added
- Initial development release
- Core logging infrastructure