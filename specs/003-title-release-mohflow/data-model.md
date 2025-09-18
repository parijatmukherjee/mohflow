# Data Model: Release Mohflow v1.1.1

## Release Entities

### Version Information
**Purpose**: Represents semantic version metadata
**Attributes**:
- `major`: Integer (1)
- `minor`: Integer (1)
- `patch`: Integer (1)
- `version_string`: String ("1.1.1")
- `tag_name`: String ("v1.1.1")

**Validation Rules**:
- Version must follow SemVer format
- Patch increment only (no major/minor changes)
- Tag name must include 'v' prefix

### Changelog Entry
**Purpose**: Structured release notes
**Attributes**:
- `version`: String ("1.1.1")
- `release_date`: Date (2025-09-18)
- `added_features`: List of strings
- `changed_items`: List of strings
- `pr_references`: List of PR numbers
- `description`: Formatted text

**Validation Rules**:
- Date must be in ISO format
- PR references must be valid GitHub PR numbers
- Description must include PR links

### Git Tag
**Purpose**: Immutable version reference
**Attributes**:
- `name`: String ("v1.1.1")
- `commit_sha`: String (40-character hash)
- `message`: String (changelog excerpt)
- `created_date`: Timestamp

**Validation Rules**:
- Tag name must be unique
- Must point to valid commit
- Message must be non-empty

### Release Notes
**Purpose**: Human-readable release information
**Attributes**:
- `title`: String ("Release v1.1.1")
- `body`: Markdown text
- `tag_name`: String ("v1.1.1")
- `prerelease`: Boolean (false)
- `draft`: Boolean (false)

**Validation Rules**:
- Body must be valid Markdown
- Must reference correct tag
- Cannot be both draft and published

### Quality Gate Result
**Purpose**: Validation status tracking
**Attributes**:
- `gate_name`: String ("format", "lint", "test")
- `status`: Enum (PASS, FAIL, PENDING)
- `output`: String (command output)
- `execution_time`: Duration

**State Transitions**:
- PENDING → PASS (on successful execution)
- PENDING → FAIL (on error/failure)
- No transitions from PASS/FAIL states

## Entity Relationships

```
Version Information ---> Git Tag
                    ---> Changelog Entry
                    ---> Release Notes

Quality Gate Result ---> Release Process
                   (must all be PASS before release)

Changelog Entry ---> Release Notes
               (content flows from changelog to release)
```

## Data Flow

1. Version Information updated in configuration files
2. Changelog Entry created with PR references
3. Quality Gates executed and validated
4. Git Tag created pointing to release commit
5. Release Notes generated from Changelog Entry
6. GitHub Release published with Release Notes