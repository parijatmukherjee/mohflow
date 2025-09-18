# Claude Code Context - MohFlow

## Project Overview
MohFlow is a Python structured logging library (JSON-first) that targets console, files, and aggregators (e.g., Loki). The project follows strict principles including TDD, quality gates, and spec-kit development workflow.

## Current Feature: Documentation & Quality Gates Hardening
**Branch**: `002-title-documentation-quality`
**Status**: Planning complete, ready for task generation

### Documentation Entities
- README.md: Primary entry point with quickstart, quality gates, TDD workflow, spec-kit sections
- CONTRIBUTING.md: Contributor guidance with pre-PR checklist and conventions
- constitution.md: Project governance with enhanced quality gate requirements
- CHANGELOG.md: Release history following Keep-a-Changelog format

### Key Implementation Requirements
- Quickstart section with working JSON logging example
- Quality gates documentation (`make format`, `make lint`, `make test`)
- TDD workflow explanation with pytest example
- Spec-kit workflow (`/specify ’ /plan ’ /tasks`) guidance
- CI badge and Python version support
- Pre-PR checklist for contributors

## Technology Stack
- **Language**: Python 3.11+
- **Testing**: pytest
- **Quality Gates**: make format, make lint, make test
- **CI**: GitHub Actions
- **Documentation**: Markdown, Keep-a-Changelog format

## Development Workflow
- TDD approach required (fail ’ implement ’ refactor)
- Spec-kit flow: /specify ’ /plan ’ /tasks
- Quality gates must pass locally before PR
- Zero-error requirement for formatting and linting
- CI enforcement matches local requirements

## Quality Standards
- All code examples must be validated against actual API
- Cross-document consistency required
- Constitutional compliance mandatory
- Links and references must be functional

## Recent Changes (Feature 002)
- Created comprehensive implementation plan for documentation hardening
- Generated content contracts for all documentation files
- Designed data model for documentation entities
- Established validation requirements and quality gates integration

## Next Steps
Ready for `/tasks` command to generate specific implementation tasks for documentation updates.