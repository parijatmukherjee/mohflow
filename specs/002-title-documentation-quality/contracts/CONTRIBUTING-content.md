# CONTRIBUTING.md Content Contract

## Required Sections Contract

### 1. Getting Started Section
```yaml
contract:
  title: "Getting Started"
  requirements:
    - Fork and clone instructions
    - Virtual environment setup
    - Development installation steps
    - Initial verification command
  validation:
    - Commands must be accurate for repository
    - Setup must result in working development environment
    - Instructions must be platform-agnostic where possible
```

### 2. Pre-PR Checklist Section
```yaml
contract:
  title: "📋 Pre-PR Checklist"
  requirements:
    - Copy-pasteable checkbox format
    - Spec requirement for non-trivial changes
    - TDD requirement with test verification
    - Quality gates requirement (make format && make lint && make test)
    - Documentation update requirement
  validation:
    - Checklist must be actionable
    - All items must be verifiable
    - Must align with constitutional requirements
```

### 3. Branch Naming Section
```yaml
contract:
  title: "Branch Naming"
  requirements:
    - feat/ prefix for new features
    - fix/ prefix for bug fixes
    - chore/ prefix for maintenance
    - Examples of good branch names
  validation:
    - Patterns must match actual repository practices
    - Examples must be realistic and clear
```

### 4. Review Expectations Section
```yaml
contract:
  title: "Review Expectations"
  requirements:
    - Code coverage considerations
    - Performance impact assessment
    - Backward compatibility requirements
    - Documentation quality standards
  validation:
    - Expectations must be reasonable and measurable
    - Must align with constitutional principles
```

## Content Quality Requirements

### Checklist Format
```markdown
- [ ] Specification written under `specs/` for non-trivial changes
- [ ] TDD workflow followed: tests added/updated before implementation
- [ ] Quality gates pass: `make format && make lint && make test` all green locally
- [ ] Documentation updated (README/docstrings) as needed
- [ ] Branch follows naming convention (feat/, fix/, chore/)
- [ ] PR title describes change clearly
- [ ] No breaking changes without major version bump
```

### Environment Setup
```bash
# Fork repository on GitHub
git clone https://github.com/YOUR_USERNAME/mohflow.git
cd mohflow

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# Install in development mode
pip install -e .

# Verify installation
python -c "from mohflow import MohflowLogger; print('✓ MohFlow development setup complete')"
```

## Constitutional Alignment

### TDD Requirements (III)
- Pre-PR checklist must include TDD verification
- Test-first approach must be explicitly required
- No implementation without corresponding tests

### Quality Gates (XI)
- make format and make lint must be zero-error requirements
- CI validation must be mentioned as non-negotiable
- Local verification must precede PR submission

### Spec-Kit Flow (IX)
- Specification requirement for non-trivial changes
- specs/ directory usage must be explained
- /specify → /plan → /tasks workflow reference

## Acceptance Criteria

### Functional Requirements Mapping
- **FR-004**: Complete pre-PR checklist covering specs, TDD, quality gates, docs ✓
- **FR-008**: Branch naming conventions and PR title standards ✓
- **FR-011**: Consistency with README, constitution, and CI configurations ✓

### User Scenario Support
- New contributor can follow setup instructions ✓
- Contributor can use checklist for PR preparation ✓
- Contributor understands review expectations ✓
- Contributor knows how to structure contributions ✓

## Links and References

### Required Links
- Link to constitution.md for governance principles
- Link to README.md for quick project overview
- Link to specs/ directory for specification examples
- Link to GitHub Issues for bug reports and feature requests

### Internal Consistency
- Branch naming must match actual repository patterns
- Quality gate commands must match README.md and Makefile
- Review expectations must align with constitutional principles
- Setup instructions must work with current repository structure