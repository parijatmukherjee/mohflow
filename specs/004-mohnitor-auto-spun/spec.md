# Feature Specification: Mohnitor (Auto-spun, Kibana-lite viewer for JSON logs)

**Feature Branch**: `004-mohnitor-auto-spun`
**Created**: 2025-09-23
**Status**: Draft
**Input**: User description: "A specification for a self-contained log viewer that automatically spins up with MohFlow. Provides a Kibana-lite UI for structured JSON logs, supports live filtering, and ensures a **single shared UI hub** when multiple apps use MohFlow."

## Execution Flow (main)
```
1. Parse user description from Input
   ’ Feature description provided: Mohnitor log viewer
2. Extract key concepts from description
   ’ Identified: log viewer, auto-discovery, shared UI hub, real-time filtering
3. For each unclear aspect:
   ’ Marked specific clarifications needed for security and deployment
4. Fill User Scenarios & Testing section
   ’ Clear user flows identified for single and multi-app scenarios
5. Generate Functional Requirements
   ’ Each requirement is testable and measurable
   ’ Some ambiguous requirements marked for clarification
6. Identify Key Entities (if data involved)
   ’ Hub descriptor, log events, client connections identified
7. Run Review Checklist
   ’ WARN "Spec has uncertainties around deployment environments"
   ’ No implementation details found in requirements
8. Return: SUCCESS (spec ready for planning with clarifications)
```

---

## ¡ Quick Guidelines
-  Focus on WHAT users need and WHY
- L Avoid HOW to implement (no tech stack, APIs, code structure)
- =e Written for business stakeholders, not developers

### Section Requirements
- **Mandatory sections**: Must be completed for every feature
- **Optional sections**: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### For AI Generation
When creating this spec from a user prompt:
1. **Mark all ambiguities**: Use [NEEDS CLARIFICATION: specific question] for any assumption you'd need to make
2. **Don't guess**: If the prompt doesn't specify something (e.g., "login system" without auth method), mark it
3. **Think like a tester**: Every vague requirement should fail the "testable and unambiguous" checklist item
4. **Common underspecified areas**:
   - User types and permissions
   - Data retention/deletion policies
   - Performance targets and scale
   - Error handling behaviors
   - Integration requirements
   - Security/compliance needs

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
As a developer working with JSON-structured logs, I want an automatic, lightweight log viewer that starts instantly and provides a unified dashboard across multiple applications, so I can debug issues without setting up heavy infrastructure like ELK stack.

### Acceptance Scenarios
1. **Given** I enable Mohnitor in my first application, **When** the application starts, **Then** it becomes the hub and displays the UI URL
2. **Given** a hub is already running, **When** I start a second application with Mohnitor enabled, **Then** it automatically connects to the existing hub and its logs appear in the same UI
3. **Given** I'm viewing logs in the UI, **When** I apply filters for log level or service name, **Then** results update in under 100ms
4. **Given** multiple services are logging, **When** I click on a trace_id, **Then** all logs with that trace_id are filtered across all connected services
5. **Given** the hub application crashes, **When** another Mohnitor-enabled app is running, **Then** it takes over as the new hub within 2 seconds

### Edge Cases
- What happens when the configured port range (17361-17380) is exhausted?
- How does the system handle network partitions between client and hub?
- What occurs when log volume exceeds the buffer capacity?
- How does the system behave when multiple processes attempt to become hub simultaneously?

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: System MUST automatically determine whether to become a hub or connect to an existing hub when Mohnitor is enabled
- **FR-002**: System MUST provide a web-based UI accessible via local browser for viewing structured JSON logs
- **FR-003**: System MUST support real-time log streaming with latency under 150ms for new log entries
- **FR-004**: System MUST maintain a bounded in-memory buffer with configurable size (default 50k events)
- **FR-005**: System MUST provide filtering capabilities for time ranges, log levels, service names, and arbitrary field values
- **FR-006**: System MUST support cross-service trace correlation by clicking trace identifiers
- **FR-007**: System MUST implement automatic hub discovery using file descriptors and health checks
- **FR-008**: System MUST handle hub failure scenarios with automatic failover to another running client
- **FR-009**: System MUST bind to localhost by default for security
- **FR-010**: System MUST support configuration persistence and loading for UI preferences
- **FR-011**: System MUST provide export functionality for logs in NDJSON format
- **FR-012**: System MUST implement non-blocking log forwarding to prevent application performance impact
- **FR-013**: System MUST support field redaction for sensitive data patterns [NEEDS CLARIFICATION: which specific patterns should be redacted by default?]
- **FR-014**: System MUST handle disconnection scenarios with exponential backoff retry logic
- **FR-015**: System MUST display system metrics including buffer usage, drop rates, and connected clients
- **FR-016**: System MUST support deployment in [NEEDS CLARIFICATION: container environments, serverless, or only traditional deployments?]
- **FR-017**: System MUST authenticate remote connections [NEEDS CLARIFICATION: what authentication mechanism for non-localhost deployments?]

### Key Entities *(include if feature involves data)*
- **Hub Descriptor**: Contains hub location, process ID, port, and access token for client discovery
- **Log Event**: Structured JSON log entry with timestamp, level, service, message, and contextual fields
- **Client Connection**: Represents a connected application forwarding logs to the hub
- **Filter Configuration**: User-defined criteria for displaying subset of log events
- **UI State**: Persistent configuration including column preferences, theme, and saved filters

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

### Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

---

## Execution Status
*Updated by main() during processing*

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [ ] Review checklist passed (pending clarifications)

---