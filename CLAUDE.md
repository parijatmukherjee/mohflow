# Claude Code Context - MohFlow

## Project Overview
MohFlow is a Python structured logging library (JSON-first) that targets console, files, and aggregators (e.g., Loki). The project follows strict principles including TDD, quality gates, and spec-kit development workflow.

## Current Feature: Mohnitor (Auto-spun, Kibana-lite viewer for JSON logs)
**Branch**: `004-mohnitor-auto-spun`
**Status**: Planning complete, ready for task generation

### Mohnitor Architecture
- Auto-spun log viewer with shared UI hub architecture
- Hub/client model with automatic discovery and failover
- FastAPI/Starlette WebSocket server + Next.js static UI
- Real-time log streaming with bounded in-memory buffer
- KQL-inspired query language for client-side filtering

### Key Implementation Requirements
- Discovery system: env vars → hub.json → port probe → lockfile election
- Hub responsibilities: serve UI, WebSocket streaming, metrics endpoint
- Client responsibilities: non-blocking log forwarding, retry logic
- UI features: filterable log table, trace correlation, export, dark mode
- Performance targets: 5k events/sec, P50 ≤150ms latency, 50MB memory

## Technology Stack
- **Language**: Python 3.11+
- **Testing**: pytest
- **Quality Gates**: make format, make lint, make test
- **CI**: GitHub Actions
- **Mohnitor Dependencies**: FastAPI/Starlette, WebSockets, Next.js (static build)
- **Documentation**: Markdown, Keep-a-Changelog format

## Development Workflow
- TDD approach required (fail � implement � refactor)
- Spec-kit flow: /specify � /plan � /tasks
- Quality gates must pass locally before PR
- Zero-error requirement for formatting and linting
- CI enforcement matches local requirements

## Quality Standards
- All code examples must be validated against actual API
- Cross-document consistency required
- Constitutional compliance mandatory
- Links and references must be functional

## Recent Changes (Feature 004)
- Created implementation plan for Mohnitor auto-spun log viewer
- Designed hub/client architecture with automatic discovery
- Specified WebSocket protocol for real-time log streaming
- Created data model for log events, filters, and UI state
- Generated API contracts and quickstart documentation

## Next Steps
Ready for `/tasks` command to generate specific implementation tasks for Mohnitor development.