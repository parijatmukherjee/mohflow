# README.md Content Contract

## Required Sections Contract

### 1. Header Section
- **Title**: "MohFlow - Structured Logging for Python"
- **CI Badge**: GitHub Actions workflow status
- **Python Versions**: Supported versions list (3.11+)
- **Installation**: pip install and local development instructions

### 2. Quickstart Section
```yaml
contract:
  title: "🚀 Quickstart"
  requirements:
    - Installation command (pip or local)
    - Minimal code example (3-5 lines)
    - JSON output example
    - Working against actual MohFlow API
  validation:
    - Code must execute without errors
    - Output must be valid JSON
    - Example must demonstrate structured logging
```

### 3. Quality Gates Section
```yaml
contract:
  title: "🔒 Quality Gates"
  requirements:
    - List of make commands: format, lint, test
    - Zero-error requirement statement
    - CI enforcement explanation
    - Local development workflow
  validation:
    - Commands must exist in Makefile
    - Commands must execute successfully
    - CI workflow must enforce same rules
```

### 4. TDD Workflow Section
```yaml
contract:
  title: "🧪 TDD Workflow"
  requirements:
    - 3-step process explanation (fail → implement → refactor)
    - Minimal pytest example
    - Test file location guidance
    - Testing best practices link
  validation:
    - Test example must use pytest
    - Example must demonstrate red-green-refactor
    - Test must be runnable
```

### 5. Spec-Kit Workflow Section
```yaml
contract:
  title: "📋 Spec-Kit Workflow"
  requirements:
    - Three command explanations (/specify, /plan, /tasks)
    - specs/ directory usage example
    - Feature development process
    - Link to CONTRIBUTING.md
  validation:
    - Commands must be accurately described
    - Directory structure must match actual repo
    - Process must align with constitution.md
```

## Content Quality Requirements

### Code Examples
- Must be syntactically correct Python
- Must import from actual mohflow module
- Must produce expected output
- Must be minimal but functional

### Command References
- Make targets must exist in repository Makefile
- CI workflows must exist in .github/workflows/
- All commands must be tested and working

### Links and References
- Internal links must point to existing files
- External links must be valid and stable
- Badge URLs must point to actual CI workflows

## Acceptance Criteria

### Functional Requirements Mapping
- **FR-001**: Quickstart section with working JSON logging example ✓
- **FR-002**: Quality gate commands with clear instructions ✓
- **FR-003**: TDD workflow with concrete steps and example ✓
- **FR-006**: CI build status badge and Python versions ✓
- **FR-007**: Spec-kit workflow with command examples ✓

### User Scenario Support
- New contributor can install and run example ✓
- Contributor understands quality gate requirements ✓
- Contributor understands TDD expectations ✓
- Contributor understands spec-kit development process ✓