# Tasks: Fix GitHub PR Test Failures for Sensitive Data Filter Enhancement

**Input**: Design documents from `/specs/001-there-is-an/` + GitHub PR #26 failing CI tests
**Prerequisites**: plan.md, data-model.md, contracts/filter_api.md, quickstart.md
**Context**: GitHub PR #26 has failing CI tests across Python versions 3.8-3.11

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → Tech stack: Python 3.8+, pytest, black, flake8
   → Structure: Single project with src/ and tests/
2. Analyze CI failure context:
   → GitHub Actions workflow: .github/workflows/ci.yml
   → Multi-version testing: Python 3.8, 3.9, 3.10, 3.11
   → Quality gates: black formatting, flake8 linting, pytest coverage
3. Load design documents:
   → data-model.md: 4 entities (FilterConfiguration, FieldClassification, TracingFieldRegistry, FilterResult)
   → contracts/: API methods (classify_field, filter_data_with_audit, field management)
   → research.md: Implementation status (COMPLETED), performance requirements
4. Generate diagnostic and fix tasks:
   → Diagnostic: Multi-version compatibility testing
   → CI Simulation: Environment matching, dependency validation
   → Performance: Test stability across environments
   → Quality: Formatting and linting compliance
5. Apply task rules:
   → Diagnostic tasks = mark [P] for parallel version testing
   → Fix tasks = sequential when modifying same files
   → Validation before fixes (diagnostic-first approach)
6. Number tasks sequentially (T001, T002...)
7. SUCCESS: 31 tasks ready for CI fix execution
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- **Single project**: `src/mohflow/`, `tests/` at repository root
- **CI Environment**: Ubuntu latest, Python 3.8-3.11 matrix testing
- **Key Files**: `tests/test_context/test_classify_field.py`, `.github/workflows/ci.yml`

## Phase 3.1: Environment Setup & Diagnostics
- [ ] T001 [P] Verify local Python environment compatibility with CI matrix (3.8-3.11)
- [ ] T002 [P] Check requirements-dev.txt for Python version conflicts
- [ ] T003 [P] Validate pyproject.toml configuration matches CI expectations

## Phase 3.2: Multi-Version Diagnostic Testing ⚠️ CRITICAL FOR CI FIX
**PRIORITY: Identify version-specific failures across Python 3.8-3.11**

### Python Version Compatibility Testing
- [ ] T004 [P] Run full test suite with Python 3.8 to identify failures in tests/
- [ ] T005 [P] Run full test suite with Python 3.9 to identify failures in tests/
- [ ] T006 [P] Run full test suite with Python 3.10 to identify failures in tests/
- [ ] T007 [P] Run full test suite with Python 3.11 to identify failures in tests/
- [ ] T008 Compare test results across versions to identify patterns

### CI Pipeline Simulation
- [ ] T009 [P] Test black formatting compliance: `black --check src tests`
- [ ] T010 [P] Test flake8 linting compliance: `flake8 src tests`
- [ ] T011 Test coverage requirements: `pytest tests/ --cov=mohflow --cov-report=xml`
- [ ] T012 Test package installation: `pip install -e .` (CI simulation)

## Phase 3.3: Performance Test Stabilization
**FOCUS: Fix test_classify_field_performance timing issues**

- [ ] T013 [P] Analyze performance test stability in tests/test_context/test_classify_field.py
- [ ] T014 [P] Test performance characteristics on Ubuntu environment (CI runner OS)
- [ ] T015 [P] Validate performance thresholds across Python versions 3.8-3.11
- [ ] T016 Adjust performance test timing for CI environment reliability

## Phase 3.4: Contract Compliance Validation
**ENSURE: All API contracts work across Python versions**

- [ ] T017 [P] Validate classify_field() contract in src/mohflow/context/filters.py
- [ ] T018 [P] Validate filter_data_with_audit() contract in src/mohflow/context/filters.py
- [ ] T019 [P] Validate FieldClassification model across Python versions
- [ ] T020 [P] Validate FilterConfiguration model across Python versions

## Phase 3.5: Integration Test Validation
**VERIFY: End-to-end scenarios work in CI environment**

- [ ] T021 [P] Test basic tracing scenario from tests/integration/test_basic_tracing_scenario.py
- [ ] T022 [P] Test custom safe fields from tests/integration/test_custom_safe_fields_scenario.py
- [ ] T023 Test logger integration with tracing exemptions end-to-end
- [ ] T024 Validate backward compatibility across Python versions

## Phase 3.6: CI Environment Matching
**SIMULATE: Exact CI conditions locally**

- [ ] T025 [P] Test in Ubuntu environment using Docker/container
- [ ] T026 [P] Validate installation from clean environment
- [ ] T027 [P] Test optional dependencies across Python versions
- [ ] T028 Memory and performance validation in CI-like environment

## Phase 3.7: Fix Application & Validation
**APPLY: Identified fixes and verify success**

- [ ] T029 Apply fixes to failing tests based on diagnostic results
- [ ] T030 [P] Re-run complete test suite to confirm all fixes
- [ ] T031 [P] Final validation: make format && make lint (zero errors)
- [ ] T032 Push fixes and verify GitHub Actions CI success

## Dependencies
- Environment setup (T001-T003) before diagnostics (T004-T012)
- Multi-version testing (T004-T008) before performance analysis (T013-T016)
- Diagnostic results (T004-T028) before fix application (T029)
- T029 (fixes applied) before final validation (T030-T032)
- All validation tasks before pushing fixes (T032)

## Parallel Execution Examples

### Phase 3.2 - Multi-Version Testing
```bash
# Launch Python version compatibility tests together:
Task: "Run full test suite with Python 3.8 to identify failures in tests/"
Task: "Run full test suite with Python 3.9 to identify failures in tests/"
Task: "Run full test suite with Python 3.10 to identify failures in tests/"
Task: "Run full test suite with Python 3.11 to identify failures in tests/"

# Launch CI pipeline simulation together:
Task: "Test black formatting compliance: black --check src tests"
Task: "Test flake8 linting compliance: flake8 src tests"
```

### Phase 3.3 - Performance Analysis
```bash
# Launch performance tests together:
Task: "Analyze performance test stability in tests/test_context/test_classify_field.py"
Task: "Test performance characteristics on Ubuntu environment"
Task: "Validate performance thresholds across Python versions 3.8-3.11"
```

### Phase 3.4 - Contract Validation
```bash
# Launch contract compliance tests together:
Task: "Validate classify_field() contract in src/mohflow/context/filters.py"
Task: "Validate filter_data_with_audit() contract in src/mohflow/context/filters.py"
Task: "Validate FieldClassification model across Python versions"
Task: "Validate FilterConfiguration model across Python versions"
```

## Known CI Issues to Address
Based on GitHub PR #26 failures:
1. **Test Failures**: Python 3.8, 3.9, 3.10, 3.11 all failing
2. **Performance Instability**: test_classify_field_performance timing sensitive to CI environment
3. **Environment Differences**: Ubuntu CI vs local macOS development
4. **Coverage Requirements**: Ensuring consistent coverage across Python versions

## Critical Success Criteria
- [ ] All GitHub Actions CI tests pass across Python 3.8-3.11
- [ ] Black formatting check passes (exit code 0)
- [ ] Flake8 linting check passes (exit code 0)
- [ ] Test coverage requirements met consistently
- [ ] Performance tests stable in CI environment
- [ ] PR #26 ready for merge after fixes

## File Modifications for CI Fixes
**Primary Focus Files**:
- `tests/test_context/test_classify_field.py` - Performance test timing adjustments
- `src/mohflow/context/filters.py` - Core implementation validation
- `.github/workflows/ci.yml` - CI configuration analysis
- `requirements-dev.txt` - Dependency compatibility
- `pyproject.toml` - Project configuration validation

**CI Environment Simulation**:
- Ubuntu latest environment testing
- Python version matrix compatibility
- Package installation validation
- Memory and performance characteristics

## Validation Checklist
*GATE: Checked before task completion*

- [x] All Python versions (3.8-3.11) have diagnostic tasks
- [x] CI pipeline simulation matches GitHub Actions workflow
- [x] Performance tests address timing stability issues
- [x] Contract validation covers cross-version compatibility
- [x] Environment simulation includes Ubuntu testing
- [x] Fix application task waits for diagnostic completion
- [x] Final validation ensures CI success before completion
- [x] Tasks are immediately executable with specific file paths