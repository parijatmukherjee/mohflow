# Tasks: Mohnitor (Auto-spun, Kibana-lite viewer for JSON logs)

**Input**: Design documents from `/specs/004-mohnitor-auto-spun/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Execution Flow (main)
```
1. Load plan.md from feature directory
   ✓ Loaded: FastAPI/Starlette + WebSockets + Next.js, single project structure
2. Load optional design documents:
   ✓ data-model.md: 5 entities extracted → model tasks
   ✓ contracts/: hub-api.yaml, websocket-protocol.md → contract test tasks
   ✓ research.md: tech decisions → setup tasks
3. Generate tasks by category:
   ✓ Setup: devui module, FastAPI dependencies, UI build pipeline
   ✓ Tests: contract tests, integration tests for discovery/failover
   ✓ Core: models, hub server, client forwarder, query engine
   ✓ Integration: discovery system, UI serving, WebSocket handling
   ✓ Polish: unit tests, performance benchmarks, documentation
4. Apply task rules:
   ✓ Different files = mark [P] for parallel
   ✓ Same file = sequential (no [P])
   ✓ Tests before implementation (TDD)
5. Number tasks sequentially (T001, T002...)
6. Generate dependency graph
7. Create parallel execution examples
8. Validate task completeness:
   ✓ All contracts have tests
   ✓ All entities have models
   ✓ All endpoints implemented
9. Return: SUCCESS (tasks ready for execution)
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- **Single project**: `src/mohflow/devui/`, `tests/test_devui/` (extending existing MohFlow)
- All paths relative to repository root: `/Users/parijatmukherjee/workspace/mohflow/`

## Phase 3.1: Setup
- [ ] T001 Create devui module structure in src/mohflow/devui/ with __init__.py, types.py, paths.py
- [ ] T002 Add FastAPI, websockets, and UI build dependencies to pyproject.toml [mohnitor] extra
- [ ] T003 [P] Configure flake8 rules for new devui module in .flake8
- [ ] T004 [P] Create UI build pipeline script in scripts/build-ui.py for Next.js static output

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

### Contract Tests [P]
- [ ] T005 [P] Contract test GET /healthz endpoint in tests/test_devui/test_contracts/test_healthz.py
- [ ] T006 [P] Contract test GET /system endpoint in tests/test_devui/test_contracts/test_system.py
- [ ] T007 [P] Contract test GET /version endpoint in tests/test_devui/test_contracts/test_version.py
- [ ] T008 [P] Contract test GET /ui endpoint serves HTML in tests/test_devui/test_contracts/test_ui.py
- [ ] T009 [P] Contract test WebSocket /ws endpoint authentication in tests/test_devui/test_contracts/test_websocket.py

### Data Model Tests [P]
- [ ] T010 [P] Unit test HubDescriptor validation in tests/test_devui/test_models/test_hub_descriptor.py
- [ ] T011 [P] Unit test LogEvent serialization in tests/test_devui/test_models/test_log_event.py
- [ ] T012 [P] Unit test ClientConnection lifecycle in tests/test_devui/test_models/test_client_connection.py
- [ ] T013 [P] Unit test FilterConfiguration parsing in tests/test_devui/test_models/test_filter_config.py
- [ ] T014 [P] Unit test UIState persistence in tests/test_devui/test_models/test_ui_state.py

### Integration Tests [P]
- [ ] T015 [P] Integration test single app becomes hub in tests/test_devui/test_integration/test_single_app_hub.py
- [ ] T016 [P] Integration test multi-app auto-discovery in tests/test_devui/test_integration/test_multi_app_discovery.py
- [ ] T017 [P] Integration test hub failover when primary crashes in tests/test_devui/test_integration/test_hub_failover.py
- [ ] T018 [P] Integration test real-time log streaming in tests/test_devui/test_integration/test_log_streaming.py
- [ ] T019 [P] Integration test trace correlation across services in tests/test_devui/test_integration/test_trace_correlation.py
- [ ] T020 [P] Integration test filtering performance <100ms in tests/test_devui/test_integration/test_filter_performance.py

## Phase 3.3: Core Implementation (ONLY after tests are failing)

### Data Models [P]
- [ ] T021 [P] HubDescriptor dataclass with validation in src/mohflow/devui/types.py
- [ ] T022 [P] LogEvent dataclass with JSON serialization in src/mohflow/devui/types.py
- [ ] T023 [P] ClientConnection tracking model in src/mohflow/devui/types.py
- [ ] T024 [P] FilterConfiguration with MQL parsing in src/mohflow/devui/types.py
- [ ] T025 [P] UIState with persistence methods in src/mohflow/devui/types.py

### Discovery & Election System [P]
- [ ] T026 [P] Hub discovery logic with env/file/probe fallback in src/mohflow/devui/discovery.py
- [ ] T027 [P] Lockfile election algorithm with PID validation in src/mohflow/devui/election.py
- [ ] T028 [P] File paths and descriptor management in src/mohflow/devui/paths.py

### Hub Server Implementation
- [ ] T029 FastAPI application setup with WebSocket support in src/mohflow/devui/hub.py
- [ ] T030 GET /healthz endpoint implementation in src/mohflow/devui/hub.py
- [ ] T031 GET /system metrics endpoint in src/mohflow/devui/hub.py
- [ ] T032 GET /version endpoint implementation in src/mohflow/devui/hub.py
- [ ] T033 GET /ui static file serving in src/mohflow/devui/hub.py
- [ ] T034 WebSocket /ws endpoint with authentication in src/mohflow/devui/hub.py
- [ ] T035 Ring buffer implementation with drop-oldest policy in src/mohflow/devui/hub.py
- [ ] T036 Client connection management and broadcasting in src/mohflow/devui/hub.py

### Client Forwarder Implementation [P]
- [ ] T037 [P] MohnitorForwardingHandler for Python logging in src/mohflow/devui/client.py
- [ ] T038 [P] Non-blocking queue with background thread in src/mohflow/devui/client.py
- [ ] T039 [P] WebSocket sender with exponential backoff in src/mohflow/devui/client.py
- [ ] T040 [P] Connection retry logic and error handling in src/mohflow/devui/client.py

### Query Language Engine [P]
- [ ] T041 [P] MQL parser for KQL-inspired syntax in src/mohflow/devui/query/mql.py
- [ ] T042 [P] Filter evaluator for client-side processing in src/mohflow/devui/query/evaluator.py

### Security & Redaction [P]
- [ ] T043 [P] Sensitive data patterns and redaction in src/mohflow/devui/redaction.py
- [ ] T044 [P] Token generation and validation in src/mohflow/devui/utils.py

## Phase 3.4: Integration
- [ ] T045 Integrate Mohnitor with MohFlow get_logger() function in src/mohflow/__init__.py
- [ ] T046 Add enable_mohnitor parameter to logger configuration in src/mohflow/config_loader.py
- [ ] T047 Hub startup/shutdown lifecycle management in src/mohflow/devui/mohnitor.py
- [ ] T048 Client auto-discovery and connection in src/mohflow/devui/mohnitor.py
- [ ] T049 Environment variable handling (MOHNITOR_REMOTE, MOHNITOR_TOKEN, etc) in src/mohflow/devui/mohnitor.py
- [ ] T050 Error handling and graceful degradation in src/mohflow/devui/mohnitor.py

## Phase 3.5: UI Implementation
- [ ] T051 [P] Next.js project setup with TypeScript in ui/package.json
- [ ] T052 [P] WebSocket client with auto-reconnection in ui/src/lib/websocket.ts
- [ ] T053 [P] Log table component with virtual scrolling in ui/src/components/LogTable.tsx
- [ ] T054 [P] JSON viewer with expand/collapse in ui/src/components/JsonViewer.tsx
- [ ] T055 [P] Filter controls and MQL input in ui/src/components/FilterBar.tsx
- [ ] T056 [P] Dark mode and theme switching in ui/src/components/ThemeProvider.tsx
- [ ] T057 [P] Export functionality (NDJSON download) in ui/src/lib/export.ts
- [ ] T058 Build static UI bundle and embed in Python package in scripts/build-ui.py

## Phase 3.6: Performance & Polish
- [ ] T059 [P] Performance benchmark harness for 5k events/sec in tests/test_devui/test_performance/test_throughput.py
- [ ] T060 [P] Latency tests for P50 ≤150ms, P95 ≤300ms in tests/test_devui/test_performance/test_latency.py
- [ ] T061 [P] Memory usage validation ≤50MB for 50k events in tests/test_devui/test_performance/test_memory.py
- [ ] T062 [P] UI bundle size validation <2.5MB gzipped in tests/test_devui/test_performance/test_bundle_size.py
- [ ] T063 [P] Unit tests for edge cases and error conditions in tests/test_devui/test_unit/
- [ ] T064 [P] Update README.md with Mohnitor quickstart section
- [ ] T065 [P] Update CHANGELOG.md with new feature entry
- [ ] T066 [P] Add docstrings to all public APIs per constitution
- [ ] T067 End-to-end testing with real MohFlow integration using quickstart examples
- [ ] T068 Manual testing validation following quickstart.md scenarios

## Dependencies

### Sequential Dependencies
- Setup (T001-T004) → Tests (T005-T020) → Implementation (T021-T068)
- T021-T025 (models) → T026-T028 (discovery) → T029-T036 (hub)
- T029 (FastAPI setup) → T030-T036 (endpoints)
- T045-T050 (integration) → T067-T068 (E2E testing)
- T051 (UI setup) → T052-T057 (UI components) → T058 (build)

### Parallel Groups
- **Contract Tests**: T005-T009 (different endpoints)
- **Model Tests**: T010-T014 (different entities)
- **Integration Tests**: T015-T020 (different scenarios)
- **Data Models**: T021-T025 (same file, different classes)
- **Discovery Components**: T026-T028 (different files)
- **Client Components**: T037-T040 (same file, different functions)
- **Query Engine**: T041-T042 (different files)
- **Security**: T043-T044 (different files)
- **UI Components**: T052-T057 (different files)
- **Performance Tests**: T059-T062 (different files)
- **Polish Tasks**: T063-T066 (different files)

## Parallel Example
```bash
# Phase 3.2 - Launch contract tests together:
Task: "Contract test GET /healthz endpoint in tests/test_devui/test_contracts/test_healthz.py"
Task: "Contract test GET /system endpoint in tests/test_devui/test_contracts/test_system.py"
Task: "Contract test GET /version endpoint in tests/test_devui/test_contracts/test_version.py"
Task: "Contract test WebSocket /ws endpoint authentication in tests/test_devui/test_contracts/test_websocket.py"

# Phase 3.3 - Launch model implementations together:
Task: "HubDescriptor dataclass with validation in src/mohflow/devui/types.py"
Task: "Hub discovery logic with env/file/probe fallback in src/mohflow/devui/discovery.py"
Task: "Lockfile election algorithm with PID validation in src/mohflow/devui/election.py"
Task: "MohnitorForwardingHandler for Python logging in src/mohflow/devui/client.py"
```

## Critical Success Criteria

**Every phase can only be marked as completed when End to End tests (All tests) are green:**

### Phase Completion Gates
- **Phase 3.2 Complete**: All tests T005-T020 written and FAILING
- **Phase 3.3 Complete**: All tests T005-T020 PASSING + implementation tests green
- **Phase 3.4 Complete**: Integration tests T015-T019 PASSING with real MohFlow
- **Phase 3.5 Complete**: UI components functional + E2E browser tests passing
- **Phase 3.6 Complete**: Performance benchmarks meeting targets + all tests green

### Final Acceptance
```bash
# Must pass before marking feature complete:
PYTHONPATH=src python3 -m pytest tests/test_devui/ -v
make test  # All existing MohFlow tests still pass
make lint  # Zero linting errors
make format # Code properly formatted

# Performance validation:
python3 tests/test_devui/test_performance/test_throughput.py  # ≥5k events/sec
python3 tests/test_devui/test_performance/test_latency.py     # P50 ≤150ms
python3 tests/test_devui/test_performance/test_memory.py      # ≤50MB
```

## Notes
- [P] tasks = different files, no dependencies, can run concurrently
- ALL tests must be written BEFORE implementation (TDD requirement)
- Tests must FAIL initially, then PASS after implementation
- No phase marked complete until ALL tests are green
- Hub server tasks (T029-T036) modify same file, so sequential
- UI build (T058) requires all UI components (T052-T057) complete
- Final E2E testing (T067-T068) validates complete feature integration

## Task Generation Rules Applied

1. **From Contracts**: ✓ Each API endpoint → contract test + implementation
2. **From Data Model**: ✓ Each entity → model creation + validation tests
3. **From User Stories**: ✓ Each quickstart scenario → integration test
4. **Ordering**: ✓ Setup → Tests → Models → Services → Integration → Polish
5. **Dependencies**: ✓ Tests before implementation, models before services

## Validation Checklist ✓

- [x] All contracts have corresponding tests (T005-T009)
- [x] All entities have model tasks (T021-T025)
- [x] All tests come before implementation (T005-T020 before T021+)
- [x] Parallel tasks truly independent ([P] tasks use different files)
- [x] Each task specifies exact file path
- [x] No task modifies same file as another [P] task
- [x] Critical requirement: All tests must pass for phase completion