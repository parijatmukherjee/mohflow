# Data Model: Sensitive Data Filter Enhancement

## Core Entities

### 1. FilterConfiguration
Represents the configuration state of the sensitive data filter.

**Fields**:
- `enabled: bool` - Whether filtering is active
- `exclude_tracing_fields: bool` - Whether to exempt tracing fields
- `custom_safe_fields: Set[str]` - User-defined safe field names
- `tracing_field_patterns: List[str]` - Regex patterns for tracing fields
- `sensitive_fields: Set[str]` - Fields to redact
- `sensitive_patterns: List[str]` - Patterns for sensitive data detection
- `case_sensitive: bool` - Whether field matching is case-sensitive

**Validation Rules**:
- `enabled` must be boolean
- `custom_safe_fields` must not contain empty strings
- `tracing_field_patterns` must be valid regex patterns
- `sensitive_fields` must not overlap with built-in tracing fields when `exclude_tracing_fields=True`

**State Transitions**:
- Configuration can be modified at runtime via add/remove methods
- Pattern compilation happens once during initialization
- Field lookup sets are rebuilt when fields are added/removed

### 2. FieldClassification
Represents the contextual classification of a field name.

**Fields**:
- `field_name: str` - The original field name
- `classification: FieldType` - Enum: TRACING, SENSITIVE, NEUTRAL
- `matched_pattern: Optional[str]` - Which pattern matched (if any)
- `exempted: bool` - Whether field is exempt from filtering

**Validation Rules**:
- `field_name` must not be None or empty
- `classification` must be valid FieldType enum value
- `matched_pattern` must be valid regex if provided

**Relationships**:
- Created by FilterConfiguration during field evaluation
- Used by filtering logic to determine redaction behavior

### 3. TracingFieldRegistry
Represents the registry of known tracing field patterns and exemptions.

**Fields**:
- `default_fields: Set[str]` - Built-in tracing field names
- `default_patterns: List[Pattern]` - Built-in tracing patterns
- `custom_fields: Set[str]` - User-added tracing fields
- `custom_patterns: List[Pattern]` - User-added tracing patterns

**Built-in Default Fields**:
```python
DEFAULT_TRACING_FIELDS = {
    "correlation_id", "request_id", "trace_id", "span_id",
    "transaction_id", "session_id", "operation_id",
    "parent_id", "root_id", "trace_context",
    "baggage", "trace_state"
}
```

**Built-in Default Patterns**:
```python
DEFAULT_TRACING_PATTERNS = [
    r"^trace_.*",           # trace_*
    r"^span_.*",            # span_*
    r"^request_.*",         # request_*
    r"^correlation_.*",     # correlation_*
    r".*_trace_id$",        # *_trace_id
    r".*_span_id$",         # *_span_id
    r".*_request_id$"       # *_request_id
]
```

**Validation Rules**:
- Pattern strings must compile to valid regex
- Custom fields must not conflict with sensitive field patterns
- Registry maintains immutable defaults while allowing customization

### 4. FilterResult
Represents the result of filtering a data structure.

**Fields**:
- `filtered_data: Any` - The data with sensitive fields redacted
- `redacted_fields: List[str]` - List of field names that were redacted
- `preserved_fields: List[str]` - List of tracing fields that were preserved
- `processing_time: float` - Time taken for filtering operation

**Validation Rules**:
- `redacted_fields` must contain only valid field names
- `preserved_fields` must not overlap with `redacted_fields`
- `processing_time` must be non-negative

**Relationships**:
- Returned by SensitiveDataFilter.filter_data() method
- Used for audit logging and performance monitoring

## Data Flow

### Field Classification Flow
```
Input: field_name: str
  ↓
1. Check TracingFieldRegistry.is_tracing_field(field_name)
  ↓ (if True)
2. Return FieldClassification(TRACING, exempted=True)
  ↓ (if False)
3. Check traditional sensitive patterns
  ↓ (if matches)
4. Return FieldClassification(SENSITIVE, exempted=False)
  ↓ (if no match)
5. Return FieldClassification(NEUTRAL, exempted=False)
```

### Filter Processing Flow
```
Input: data structure
  ↓
1. Recursively traverse data structure
  ↓
2. For each field:
   - Get FieldClassification
   - Apply redaction based on classification
  ↓
3. Build FilterResult with:
   - Filtered data
   - Lists of redacted/preserved fields
   - Performance metrics
```

### Configuration Update Flow
```
Input: configuration change
  ↓
1. Validate new configuration values
  ↓
2. Update FilterConfiguration state
  ↓
3. Recompile regex patterns if needed
  ↓
4. Rebuild field lookup sets
  ↓
5. Clear any cached classification results
```

## Performance Considerations

### Lookup Optimization
- Use `set` for O(1) field name lookups
- Pre-compile regex patterns during initialization
- Cache compiled patterns to avoid recompilation

### Memory Management
- Avoid creating unnecessary intermediate objects
- Reuse classification objects where possible
- Use generators for large data structure traversal

### Computational Complexity
- Field classification: O(1) for exact matches, O(p) for pattern matching where p = number of patterns
- Data filtering: O(n) where n = number of fields in data structure
- Configuration updates: O(k) where k = number of patterns to recompile

## Integration Points

### With Existing SensitiveDataFilter
- Extend existing class with new methods
- Maintain backward compatibility with current API
- Add new configuration parameters with sensible defaults

### With Logger Configuration
- Add parameters to MohflowLogger constructor
- Integrate with existing logger initialization flow
- Ensure configuration propagates to filter instances

### With Static Configuration
- Add new constants to static_config.py
- Maintain separation between default and user configuration
- Ensure thread-safe access to shared configuration

## Error Handling

### Invalid Configuration
- Raise `ValueError` for invalid regex patterns
- Raise `TypeError` for incorrect parameter types
- Provide clear error messages with suggested fixes

### Runtime Errors
- Gracefully handle regex compilation failures
- Fall back to basic string matching if pattern matching fails
- Log configuration errors without crashing the application

### Edge Cases
- Handle None/empty field names gracefully
- Manage circular references in nested data structures
- Prevent infinite recursion in malformed data