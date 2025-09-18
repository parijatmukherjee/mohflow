
# Implementation Plan: Improve Sensitive Data Filter Configuration for Tracing Fields

**Branch**: `001-there-is-an` | **Date**: 2025-09-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-there-is-an/spec.md`

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
Fix the sensitive data filter in mohflow to prevent redaction of distributed tracing fields (correlation_id, request_id, trace_id) while maintaining security for authentication data. Add configurable exemptions for observability fields and comprehensive test coverage to ensure the issue is resolved.

## Technical Context
**Language/Version**: Python 3.8+ (supports 3.8-3.10+, tested environments)
**Primary Dependencies**: pydantic>=2.0.0, python-json-logger>=2.0.0, orjson>=3.8.0, opentelemetry-api>=1.20.0
**Storage**: N/A (logging library - outputs to console, files, Loki)
**Testing**: pytest (existing test framework, must add comprehensive tests)
**Target Platform**: Cross-platform Python library (Linux, macOS, Windows)
**Project Type**: single (Python logging library with existing src/ structure)
**Performance Goals**: Minimal logging overhead (<1ms per log call), async-friendly operations
**Constraints**: Must maintain backward compatibility, zero breaking changes, fail-safe operations
**Scale/Scope**: Library enhancement - modify existing SensitiveDataFilter class, add tracing field exemptions

**User-Provided Context**: the issue should be fixed. The tests should be added ensuring all the features are working and the issue is solved.

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**✅ I. Structured-First Logging**: Enhancement preserves existing JSON structured logging
**✅ II. Minimal Dependencies**: No new dependencies added, uses existing patterns
**✅ III. Test-First & TDD (NON-NEGOTIABLE)**: Will follow TDD approach - write failing tests first, then implement minimal code to pass tests, then refactor
**✅ IV. Configurability by Design**: Adding configurable tracing field exemptions with clear API
**✅ V. Failure-Safe Logging**: Enhancement maintains existing failure-safe behavior
**✅ VI. Performance Conscious**: Optimization focuses on reducing false positives, improving efficiency
**✅ VII. Documentation as a Feature**: Will update docstrings and examples
**✅ VIII. Semantic Versioning**: Backward-compatible enhancement = minor version bump
**✅ IX. Spec-Kit Flow (NON-NEGOTIABLE)**: Following /specify → /plan → /tasks flow
**✅ X. Observability & Integration**: Core purpose is improving observability while maintaining security
**✅ XI. Quality Gates (NON-NEGOTIABLE)**: Will ensure make format, make lint pass before commit

**Initial Constitution Check**: ✅ PASS - No violations detected

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

**Structure Decision**: Option 1 (Single project) - Python library with existing src/mohflow structure

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
- Generate TDD-focused tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each API contract method → failing test task [P] + minimal implementation task
- Each entity from data model → test creation + implementation
- Each acceptance scenario from spec → integration test task
- Configuration and performance validation tasks

**TDD-Focused Ordering Strategy**:
1. **Test Creation Phase**: All failing tests written first
   - Unit test tasks for each filter method [P]
   - Integration test tasks for logger configuration [P]
   - Regression test tasks for existing functionality [P]
2. **Minimal Implementation Phase**: Code to pass tests
   - Core filter logic implementation
   - Configuration parameter additions
   - Logger integration updates
3. **Refactoring Phase**: Optimize while maintaining green tests
   - Performance optimizations
   - Code quality improvements

**Key Task Categories**:
- Filter enhancement (core functionality)
- Logger integration (configuration API)
- Test coverage (comprehensive TDD tests)
- Documentation updates (docstrings, examples)
- Quality gates (linting, formatting, performance validation)

**Estimated Output**: 20-25 numbered, TDD-ordered tasks in tasks.md

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
- [x] Post-Design Constitution Check: PASS - TDD approach maintained, no new violations
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none required)

---
*Based on Constitution v2.1.1 - See `/memory/constitution.md`*
