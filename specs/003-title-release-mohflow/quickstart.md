# Quickstart: Release Mohflow v1.1.1

## Release Process Validation

This quickstart validates the release process by walking through all steps and verifying successful completion.

### Prerequisites
- [ ] Git repository is clean (no uncommitted changes)
- [ ] GitHub CLI is authenticated (`gh auth status`)
- [ ] Current branch is `003-title-release-mohflow`
- [ ] PRs #25 and #26 have been merged

### Step 1: Version Update
```bash
# Update version in pyproject.toml
# Verify version changed from 1.1.0 to 1.1.1
grep version pyproject.toml
```
**Expected**: `version = "1.1.1"`

### Step 2: Changelog Update
```bash
# Add changelog entry for 1.1.1
# Verify entry appears at top of file
head -20 CHANGELOG.md
```
**Expected**: See `[1.1.1] - 2025-09-18` with PR references

### Step 3: Documentation Update
```bash
# Add tracing exemption examples
# Verify examples are present in documentation
grep -r "correlation_id\|request_id\|trace_id" docs/ README.md
```
**Expected**: See usage examples for tracing field preservation

### Step 4: Quality Gates
```bash
# Run all quality gates
make format
make lint
make test
```
**Expected**: All commands complete with exit code 0

### Step 5: Git Tagging
```bash
# Create and push version tag
git tag v1.1.1
git push origin v1.1.1
```
**Expected**: Tag created and pushed successfully

### Step 6: GitHub Release
```bash
# Create GitHub release with changelog content
gh release create v1.1.1 --title "Release v1.1.1" --notes-file release-notes.md
```
**Expected**: Release published and visible on GitHub

## Verification Checklist

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

## Success Criteria

✅ **Release Complete**: All checklist items completed successfully
✅ **Quality Assured**: All gates passed before release
✅ **Documentation Current**: Examples and changelog updated
✅ **Distribution Ready**: Tag and GitHub release available

## Rollback Procedure

If issues are discovered after release:
1. Do not delete the git tag (immutable history)
2. Create a new patch release (v1.1.2) with fixes
3. Mark the problematic release as deprecated in release notes

## Post-Release Validation

1. Verify release appears in GitHub releases page
2. Check that changelog is properly formatted
3. Confirm examples work as documented
4. Validate SemVer compliance (no breaking changes)