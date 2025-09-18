# Tasks: Release Mohflow v1.1.1 (Patch Release)

**Input**: Design documents from `/specs/003-title-release-mohflow/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/, quickstart.md

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → Release process plan loaded - Python library release
   → Extract: Python 3.11+, git, GitHub CLI, pytest
2. Load optional design documents:
   → data-model.md: Version Information, Changelog Entry, Git Tag, Release Notes, Quality Gate Result
   → contracts/: Release process operations and validation contracts
   → research.md: Version config in pyproject.toml, Keep a Changelog format, quality gates
3. Generate tasks by category:
   → Setup: Prerequisites validation, environment checks
   → Version Updates: pyproject.toml version bump, changelog creation
   → Documentation: Add tracing exemption examples
   → Quality Gates: format, lint, test validation
   → Release: Git tagging, GitHub release publication
4. Apply task rules:
   → Sequential release process (no parallel execution for atomic release)
   → Quality gates must all pass before proceeding to release
   → Version updates before documentation before quality gates before release
5. Number tasks sequentially (T001, T002...)
6. Generate dependency graph
7. Validate task completeness:
   → Version updated? Changelog created? Docs updated? Quality gates passed? Release published?
8. Return: SUCCESS (tasks ready for execution)
```

## Format: `[ID] Description`
- **Sequential execution**: Release tasks must be atomic and ordered
- Include exact file paths and commands in descriptions

## Path Conventions
- **Single project**: Repository root structure
- **Configuration**: pyproject.toml at repository root
- **Documentation**: CHANGELOG.md, README.md, docs/ at repository root
- **Quality**: Makefile targets for format, lint, test

## Phase 3.1: Setup & Prerequisites
- [ ] T001 Verify release prerequisites and clean working directory
- [ ] T002 Validate GitHub CLI authentication and repository access
- [ ] T003 Confirm PRs #25 and #26 are merged and available

## Phase 3.2: Version & Configuration Updates
- [ ] T004 Update version from 1.1.0 to 1.1.1 in pyproject.toml
- [ ] T005 Create changelog entry for v1.1.1 in CHANGELOG.md with PR references

## Phase 3.3: Documentation Updates
- [ ] T006 Add tracing exemption usage examples to documentation files

## Phase 3.4: Quality Gate Validation ⚠️ MUST PASS BEFORE RELEASE
**CRITICAL: All quality gates MUST pass before proceeding to release**
- [ ] T007 Execute formatting check: `make format`
- [ ] T008 Execute linting validation: `make lint`
- [ ] T009 Execute comprehensive test suite: `make test`

## Phase 3.5: Release Publication
- [ ] T010 Create and push git tag v1.1.1 to origin
- [ ] T011 Publish GitHub release v1.1.1 with changelog content

## Phase 3.6: Release Validation
- [ ] T012 Verify release appears on GitHub and validate release notes
- [ ] T013 Execute post-release validation checklist from quickstart.md

## Dependencies
- T001-T003 (Setup) before T004-T005 (Version Updates)
- T004-T005 (Version Updates) before T006 (Documentation)
- T006 (Documentation) before T007-T009 (Quality Gates)
- T007-T009 (Quality Gates) must ALL pass before T010-T011 (Release)
- T010-T011 (Release) before T012-T013 (Validation)

## Task Details

### T001: Verify Release Prerequisites
**File**: Repository working directory
**Command**:
```bash
git status
git branch --show-current
gh auth status
```
**Expected**: Clean working directory, on branch 003-title-release-mohflow, GitHub CLI authenticated
**Contract**: Prerequisites validation from contracts/release-process.md

### T002: Validate GitHub CLI Authentication
**File**: GitHub API access
**Command**:
```bash
gh auth status
gh repo view --json name,owner
```
**Expected**: Authenticated and repository accessible
**Contract**: GitHub Release Contract preconditions

### T003: Confirm Merged PRs
**File**: Git history validation
**Command**:
```bash
git log --oneline --grep="#25"
git log --oneline --grep="#26"
```
**Expected**: Both PRs #25 and #26 appear in git history
**Contract**: Release process validation

### T004: Update Version in pyproject.toml
**File**: pyproject.toml
**Operation**: Change version from "1.1.0" to "1.1.1"
**Validation**: `grep version pyproject.toml` shows "1.1.1"
**Entity**: Version Information from data-model.md
**Contract**: Version Update Contract from contracts/release-process.md

### T005: Create Changelog Entry
**File**: CHANGELOG.md
**Operation**: Add new entry at top with format:
```markdown
## [1.1.1] - 2025-09-18

### Added
- Workflow scaffolding and automation for feature planning & task generation (PR #25)
- Enhanced Sensitive Data Filter with tracing field exemptions: keeps correlation_id, request_id, trace_id while redacting sensitive data; comprehensive TDD coverage (PR #26)

### Changed
- Docs aligned with Constitution: TDD, Spec-Kit flow, Quality Gates (format/lint/test)
- CI cleanup: remove obsolete debug test step (from PR #26 follow-ups)
```
**Entity**: Changelog Entry from data-model.md
**Contract**: Changelog Update Contract from contracts/release-process.md

### T006: Add Tracing Exemption Documentation
**File**: README.md and/or docs/ files
**Operation**: Add usage examples showing how tracing fields (correlation_id, request_id, trace_id) are preserved during sensitive data filtering
**Example**:
```python
# Tracing fields are preserved during filtering
logger.info("Processing request",
           correlation_id="abc-123",
           request_id="req-456",
           sensitive_data="[REDACTED]")
```
**Contract**: Documentation Update Contract from contracts/release-process.md

### T007: Execute Formatting Check
**File**: Entire codebase
**Command**: `make format`
**Expected**: Exit code 0, no formatting changes required
**Entity**: Quality Gate Result (format) from data-model.md
**Contract**: Quality Gate Contract from contracts/release-process.md

### T008: Execute Linting Validation
**File**: Entire codebase
**Command**: `make lint`
**Expected**: Exit code 0, no linting violations
**Entity**: Quality Gate Result (lint) from data-model.md
**Contract**: Quality Gate Contract from contracts/release-process.md

### T009: Execute Test Suite
**File**: Entire test suite
**Command**: `make test`
**Expected**: Exit code 0, all tests pass
**Entity**: Quality Gate Result (test) from data-model.md
**Contract**: Quality Gate Contract from contracts/release-process.md

### T010: Create Git Tag and Push
**File**: Git repository
**Command**:
```bash
git tag v1.1.1
git push origin v1.1.1
```
**Expected**: Tag created locally and pushed to origin successfully
**Entity**: Git Tag from data-model.md
**Contract**: Git Tagging Contract from contracts/release-process.md

### T011: Publish GitHub Release
**File**: GitHub Release
**Command**:
```bash
gh release create v1.1.1 --title "Release v1.1.1" --notes-from-tag
```
**Expected**: Release published and visible on GitHub
**Entity**: Release Notes from data-model.md
**Contract**: GitHub Release Contract from contracts/release-process.md

### T012: Verify Release Publication
**File**: GitHub releases page
**Command**:
```bash
gh release view v1.1.1
gh release list | grep v1.1.1
```
**Expected**: Release appears in list and details are correct
**Validation**: Release notes match changelog content

### T013: Execute Post-Release Validation
**File**: quickstart.md validation checklist
**Operation**: Execute verification checklist from quickstart.md
**Expected**: All checklist items completed successfully
- [ ] Version updated in pyproject.toml to 1.1.1
- [ ] CHANGELOG.md contains 1.1.1 entry with today's date
- [ ] CHANGELOG.md references PR #25 and PR #26
- [ ] Documentation includes tracing exemption examples
- [ ] `make format` passes with no changes
- [ ] `make lint` passes with no violations
- [ ] `make test` passes all tests
- [ ] Git tag v1.1.1 created and pushed
- [ ] GitHub release v1.1.1 published
- [ ] Release notes match changelog content

## Sequential Execution Example
```bash
# T001-T003: Setup
git status && gh auth status

# T004-T005: Version Updates
# Edit pyproject.toml: version = "1.1.1"
# Edit CHANGELOG.md: Add 1.1.1 entry

# T006: Documentation
# Add tracing exemption examples to docs

# T007-T009: Quality Gates (ALL must pass)
make format && make lint && make test

# T010-T011: Release (only if quality gates pass)
git tag v1.1.1 && git push origin v1.1.1
gh release create v1.1.1 --title "Release v1.1.1" --notes-from-tag

# T012-T013: Validation
gh release view v1.1.1
# Execute quickstart.md checklist
```

## Notes
- **NO parallel execution**: Release process must be atomic
- **Quality gates are blocking**: All must pass before release
- **Version format**: Must follow SemVer (1.1.1)
- **Tag format**: Must include 'v' prefix (v1.1.1)
- **Rollback strategy**: Create new patch release if issues found

## Task Generation Rules Applied
*Applied during main() execution*

1. **From Contracts**:
   - Version Update Contract → T004 (pyproject.toml update)
   - Changelog Update Contract → T005 (CHANGELOG.md update)
   - Quality Gate Contract → T007-T009 (format, lint, test)
   - Git Tagging Contract → T010 (tag creation and push)
   - GitHub Release Contract → T011 (release publication)
   - Documentation Update Contract → T006 (tracing examples)

2. **From Data Model**:
   - Version Information entity → T004 (version configuration)
   - Changelog Entry entity → T005 (changelog structure)
   - Quality Gate Result entity → T007-T009 (validation tracking)
   - Git Tag entity → T010 (tag creation)
   - Release Notes entity → T011 (GitHub release)

3. **From User Stories/Quickstart**:
   - Release process validation → T001-T003 (prerequisites)
   - Post-release validation → T012-T013 (verification)

4. **Ordering Applied**:
   - Setup → Version Updates → Documentation → Quality Gates → Release → Validation
   - Sequential dependencies: each phase blocks the next

## Validation Checklist
*GATE: Checked before execution*

- [x] All contracts have corresponding tasks
- [x] All entities have implementation tasks
- [x] Quality gates precede release tasks
- [x] Sequential execution (no parallel conflicts)
- [x] Each task specifies exact file path or command
- [x] Dependencies clearly documented
- [x] Release process follows constitutional requirements