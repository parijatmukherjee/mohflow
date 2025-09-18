# Filter API Contract

## SensitiveDataFilter Enhanced API

### Core Classification Method

#### classify_field(field_name: str) -> FieldClassification
**Purpose**: Classify a field name to determine filtering behavior.

**Input Contract**:
```python
field_name: str  # Field name to classify (can be None/empty for edge cases)
```

**Output Contract**:
```python
FieldClassification(
    field_name=str,                    # Original field name
    classification=FieldType,          # TRACING, SENSITIVE, or NEUTRAL
    matched_pattern=Optional[str],     # Pattern that matched (if any)
    exempted=bool                      # Whether field is exempted from filtering
)
```

**Behavior Contract**:
- MUST check sensitive patterns first (security priority)
- MUST check tracing exemptions second (if enabled)
- MUST default to NEUTRAL classification
- MUST handle None/empty field names gracefully
- MUST NOT raise exceptions for any string input

**Example**:
```python
filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

# Tracing field
result = filter_obj.classify_field("correlation_id")
assert result.classification == FieldType.TRACING
assert result.exempted == True

# Sensitive field
result = filter_obj.classify_field("api_key")
assert result.classification == FieldType.SENSITIVE
assert result.exempted == False

# Neutral field
result = filter_obj.classify_field("user_id")
assert result.classification == FieldType.NEUTRAL
assert result.exempted == False
```

### Enhanced Filtering Methods

#### filter_data_with_audit(data: Any) -> FilterResult
**Purpose**: Filter sensitive data with comprehensive audit trail.

**Input Contract**:
```python
data: Any  # Any data structure (dict, list, primitive, None)
```

**Output Contract**:
```python
FilterResult(
    filtered_data=Any,                 # Filtered data structure
    redacted_fields=List[str],         # Field paths that were redacted
    preserved_fields=List[str],        # Tracing fields that were preserved
    processing_time=float              # Time taken (seconds, >= 0)
)
```

**Behavior Contract**:
- MUST preserve tracing fields when exclude_tracing_fields=True
- MUST redact sensitive fields regardless of tracing settings
- MUST handle circular references gracefully
- MUST process nested data structures recursively
- MUST track field paths in dot notation (e.g., "user.profile.email")
- MUST complete processing in <100ms for typical data structures
- MUST NOT modify original input data

**Example**:
```python
data = {
    "correlation_id": "req-123",
    "api_key": "secret-key",
    "user": {"email": "user@example.com"}
}

result = filter_obj.filter_data_with_audit(data)

assert result.filtered_data["correlation_id"] == "req-123"
assert result.filtered_data["api_key"] == "[REDACTED]"
assert result.preserved_fields == ["correlation_id"]
assert result.redacted_fields == ["api_key", "user.email"]
assert result.processing_time >= 0
```

#### filter_data(data: Any) -> Any
**Purpose**: Filter sensitive data (backward compatibility).

**Input Contract**:
```python
data: Any  # Any data structure
```

**Output Contract**:
```python
Any  # Filtered data structure (same type as input)
```

**Behavior Contract**:
- MUST maintain backward compatibility with existing usage
- MUST return only the filtered data (not audit information)
- MUST delegate to filter_data_with_audit() internally

### Field Management Methods

#### add_safe_field(field_name: str) -> None
**Purpose**: Add a field to the safe exemption list.

**Input Contract**:
```python
field_name: str  # Field name to add (must be valid)
```

**Validation Contract**:
- MUST NOT be None
- MUST NOT be empty string or whitespace-only
- MUST match pattern `^[a-zA-Z0-9_.-]+$`
- MUST NOT conflict with sensitive field patterns

**Error Contract**:
```python
# Raises ValueError with specific messages:
- "invalid field name: cannot be None"
- "invalid field name: cannot be empty"
- "invalid field name: contains invalid characters"
- "conflict with sensitive field"
```

**Example**:
```python
filter_obj.add_safe_field("custom_trace_id")  # Success

filter_obj.add_safe_field("api_key")  # ValueError: conflict with sensitive field
filter_obj.add_safe_field("")         # ValueError: invalid field name: cannot be empty
```

#### remove_safe_field(field_name: str) -> None
**Purpose**: Remove a field from the safe exemption list.

**Input Contract**:
```python
field_name: str  # Field name to remove
```

**Behavior Contract**:
- MUST handle non-existent fields gracefully (no error)
- MUST NOT allow removal of built-in tracing fields
- MUST support None/empty inputs gracefully

**Error Contract**:
```python
# Raises ValueError for built-in fields:
- "cannot remove built-in field"
```

#### is_tracing_field(field_name: str) -> bool
**Purpose**: Check if a field should be exempted as a tracing field.

**Input Contract**:
```python
field_name: str  # Field name to check (can be None)
```

**Output Contract**:
```python
bool  # True if field is considered a tracing field
```

**Behavior Contract**:
- MUST return False if exclude_tracing_fields=False
- MUST return False for None/non-string inputs
- MUST check both exact matches and pattern matches

### Configuration Methods

#### get_configuration() -> FilterConfiguration
**Purpose**: Get current filter configuration.

**Output Contract**:
```python
FilterConfiguration(
    enabled=bool,
    exclude_tracing_fields=bool,
    custom_safe_fields=Set[str],        # Copy, not reference
    tracing_field_patterns=List[str],   # Copy, not reference
    sensitive_fields=Set[str],          # Copy, not reference
    sensitive_patterns=List[str],       # Copy, not reference
    case_sensitive=bool
)
```

**Behavior Contract**:
- MUST return a copy to prevent external modification
- MUST reflect current state accurately

## Performance Contracts

### Time Complexity
- `classify_field()`: O(1) for exact matches, O(P) for patterns
- `filter_data_with_audit()`: O(N) where N = number of fields
- `add_safe_field()`: O(1) for field addition
- `get_configuration()`: O(F+P) where F=fields, P=patterns (copy cost)

### Space Complexity
- Field registry: O(F+P) where F=fields, P=patterns
- Filter result: O(N) for audit trail
- Circular reference protection: O(D) where D=depth

### Performance Guarantees
- Processing time: <100ms for complex nested structures
- Memory overhead: <10MB for typical configurations
- Throughput: Support 10k+ filter operations/second

## Error Handling Contracts

### No Exceptions for Normal Operation
- `classify_field()` MUST NOT raise exceptions for any string input
- `filter_data_with_audit()` MUST NOT raise exceptions for any data input
- `is_tracing_field()` MUST NOT raise exceptions for any input

### Validation Exceptions Only
- `add_safe_field()` MAY raise ValueError for invalid inputs
- Constructor MAY raise ValueError/TypeError for invalid configuration

### Graceful Degradation
- Invalid regex patterns SHOULD be ignored during initialization
- Circular references SHOULD be handled with placeholder values
- Performance limits SHOULD log warnings but not fail operations

## Backward Compatibility Contracts

### Existing API Preservation
- All existing `filter_data()` calls MUST continue working
- Existing constructor parameters MUST remain functional
- Default behavior MUST remain unchanged when new features not enabled

### Migration Path
- New functionality MUST be opt-in via configuration
- Existing tests MUST continue passing without modification
- Performance characteristics MUST NOT degrade significantly