# Research: Mohnitor Technical Decisions

**Date**: 2025-09-23
**Status**: Complete
**Source**: Phase 0 research for implementation planning

## WebSocket Library Decision

**Decision**: FastAPI/Starlette WebSockets
**Rationale**:
- Built-in async WebSocket support with FastAPI
- Lightweight compared to full Django Channels
- Strong Python ecosystem adoption
- Consistent with MohFlow's async-first approach
- Auto-documentation with OpenAPI integration

**Alternatives considered**:
- `websockets` library: Too low-level, requires more boilerplate
- Django Channels: Heavyweight, requires Django dependency
- Socket.io: JavaScript-focused, adds complexity

## UI Framework Decision

**Decision**: Next.js static build + WebSocket client
**Rationale**:
- Static build eliminates runtime Node.js dependency
- Rich component ecosystem for log table + JSON viewer
- Built-in optimization (bundle splitting, compression)
- TypeScript support for type safety
- Can achieve <2.5MB gzipped bundle target

**Alternatives considered**:
- React SPA: More manual build setup required
- Vue.js: Smaller ecosystem for developer tools
- Vanilla JS: Development velocity too slow for complex UI

## Hub Discovery Pattern

**Decision**: File descriptor + health check + lockfile election
**Rationale**:
- Race-condition safe with atomic file operations
- PID validation prevents stale descriptor issues
- Health check endpoint validates hub responsiveness
- Graceful failover when hub process dies

**Alternatives considered**:
- Network discovery (mDNS): Too complex, platform dependencies
- Registry service: Adds external dependency
- Port scanning only: Unreliable, no metadata

## In-Memory Buffer Implementation

**Decision**: collections.deque with maxlen + drop-oldest policy
**Rationale**:
- Thread-safe append operations
- O(1) append performance
- Built-in size limiting
- Memory efficient for bounded usage

**Alternatives considered**:
- Ring buffer implementation: More complex, similar performance
- SQLite in-memory: Query capability but slower for streaming
- Redis: External dependency, overkill for single-process

## Query Language Design

**Decision**: KQL-inspired subset with client-side evaluation
**Rationale**:
- Developer familiarity from Kibana/Azure Monitor
- Client-side evaluation reduces hub complexity
- Can start simple and extend incrementally
- No additional database query engine needed

**Alternatives considered**:
- SQL subset: Less intuitive for log filtering
- JSONPath: Limited for complex boolean logic
- Custom DSL: Higher learning curve

## Authentication/Security Model

**Decision**: Token-based for non-localhost, none for localhost
**Rationale**:
- Localhost binding is inherently secure
- Token requirement for remote prevents accidental exposure
- Simple URL-safe token generation with secrets module
- No complex auth flows needed for development tool

**Alternatives considered**:
- Always require auth: Poor DX for local development
- IP allowlisting: Complex configuration, fragile
- mTLS: Overkill for development tool

## Performance Architecture

**Decision**: Non-blocking queue + background thread for forwarding
**Rationale**:
- Application logging never blocks on network I/O
- Bounded queue prevents memory issues under load
- Background thread handles connection management
- Drop policy when queue full protects main application

**Alternatives considered**:
- Synchronous forwarding: Blocks application on network issues
- Async forwarding in main thread: Adds complexity to host app
- Batch forwarding: Increases latency, complicates implementation

## Port Management Strategy

**Decision**: Auto-increment from base port (17361-17380)
**Rationale**:
- Handles multiple development environments on same machine
- Predictable port range for firewall/proxy configuration
- Atomic descriptor file update communicates chosen port
- Reasonable limit prevents infinite search

**Alternatives considered**:
- Fixed port: Conflicts when multiple developers/projects
- Random port: Hard to predict for tooling integration
- User-specified only: Poor default experience

## UI Bundle Distribution

**Decision**: Include in Python wheel under mohflow.devui.ui_dist/
**Rationale**:
- Single dependency installation (pip install mohflow[mohnitor])
- Version synchronization between UI and Python code
- Static files served directly by FastAPI
- No separate CDN or build-time download needed

**Alternatives considered**:
- Separate NPM package: Version drift risk, complex dependency
- CDN hosting: Network dependency, cache invalidation issues
- Runtime download: Security risk, offline capability lost

## Integration Points

**Decision**: Optional extra in existing MohFlow logger configuration
**Rationale**:
- Preserves backward compatibility
- Clear opt-in mechanism
- Integrates with existing MohFlow config patterns
- No breaking changes to core library

**Alternatives considered**:
- Separate package: Fragmented user experience
- Always-on: Resource usage when not needed
- Plugin system: Over-engineering for single feature

## Research Status

All technical decisions resolved. No remaining NEEDS CLARIFICATION items from Technical Context.
Ready to proceed to Phase 1 design.