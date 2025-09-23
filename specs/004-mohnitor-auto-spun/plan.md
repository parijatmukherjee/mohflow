
# Implementation Plan: Mohnitor (Auto-spun, Kibana-lite viewer for JSON logs)

**Branch**: `004-mohnitor-auto-spun` | **Date**: 2025-09-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-mohnitor-auto-spun/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Auto-spun log viewer with shared UI hub architecture. When `enable_mohnitor=True` is set, applications either become the central hub (serving web UI + WebSocket endpoints) or auto-discover and connect to existing hub. Provides real-time, filterable JSON log viewing with KQL-like queries, trace correlation, and bounded in-memory buffering. Designed for local/staging development with zero infrastructure setup.

## Technical Context
**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI/Starlette (hub server), WebSockets (real-time), Next.js (UI static build)
**Storage**: In-memory ring buffer (50k events), filesystem descriptor files (/tmp/mohnitor/)
**Testing**: pytest (unit tests), integration tests for race conditions and failover
**Target Platform**: Local development (localhost), staging environments, containerized deployments
**Project Type**: Single (library extension to existing MohFlow)
**Performance Goals**: ≥5k events/sec, P50 ≤150ms latency, P95 ≤300ms at 500 events/sec
**Constraints**: 50MB memory for 50k events, <2.5MB UI bundle, non-blocking log forwarding
**Scale/Scope**: Multi-service development environments, up to 20 port range (17361-17380)

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Structured-First Logging ✅
- Mohnitor processes and displays structured JSON logs (aligns with principle I)
- UI preserves JSON structure with expandable views

### Minimal Dependencies ⚠️
- FastAPI/Starlette: Well-justified for WebSocket + HTTP server (lightweight, async)
- Next.js build: Static output only, no runtime dependency
- WebSockets: Standard library support
- **Risk**: Next.js build toolchain adds complexity but justified for UI quality

### Test-First & TDD ✅
- TDD approach mandatory per constitution
- Unit tests for discovery, election, client, hub, query language
- Integration tests for race conditions, failover scenarios
- Performance benchmarking tests

### Configurability by Design ✅
- Clear configuration surface via MohFlow logger parameters
- Environment variable overrides supported
- Defaults work out-of-box (localhost, auto-port detection)

### Failure-Safe Logging ✅
- Non-blocking forwarding handler prevents application impact
- Graceful degradation when hub unavailable
- Exponential backoff retry logic

### Performance Conscious ✅
- Bounded buffers prevent memory bloat
- Non-blocking queue design
- Specific latency targets defined

### Documentation as a Feature ✅
- quickstart.md will provide usage examples
- Docstrings required for all public APIs

### Semantic Versioning ✅
- Feature addition = minor version bump

### Spec-Kit Flow ✅
- Following /specify → /plan → /tasks workflow

### Observability & Integration ✅
- Hub exposes /system metrics endpoint
- Self-logging under service="mohnitor"

### Quality Gates ✅
- make format, make lint, make test will be enforced
- CI validation required

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure]
```

**Structure Decision**: Option 1 (Single project) - Mohnitor is a library extension to existing MohFlow, adding devui/ module

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh claude` for your AI assistant
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each contract → contract test task [P]
- Each entity → model creation task [P] 
- Each user story → integration test task
- Implementation tasks to make tests pass

**Ordering Strategy**:
- TDD order: Tests before implementation 
- Dependency order: Models before services before UI
- Mark [P] for parallel execution (independent files)

**Estimated Output**: 25-30 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented

---
*Based on Constitution v2.1.1 - See `/memory/constitution.md`*
