# Mohflow Constitution

## Core Principles

### I. Structured-First Logging
All logs must be structured as JSON. Keys should be consistent across outputs (console, file, Loki).  
Free-form strings are discouraged unless under a `message` field.  

### II. Minimal Dependencies
Keep the library lightweight. Only standard library + well-justified, small dependencies are allowed.  
Every dependency must be evaluated for long-term stability, licensing, and security.  

### III. Test-First (NON-NEGOTIABLE)
Every feature or bugfix must include automated tests.  
Unit tests cover all log levels, outputs, and failure scenarios.  
No PR is merged without passing tests.  

### IV. Configurability by Design
Users should be able to configure outputs (console, files, Loki), log levels, and contexts via clear APIs.  
Defaults must “just work,” while configuration should be explicit and documented.  

### V. Failure-Safe Logging
Logging must never crash the host application.  
If a downstream sink (like Loki) fails, logs should gracefully fallback (queue, retry, or console).  

### VI. Performance Conscious
Logging must add minimal overhead in hot paths.  
Avoid blocking I/O in main execution flow.  
Consider async, buffering, or batching where appropriate.  

### VII. Documentation as a Feature
Every public function and class must have docstrings and usage examples.  
README and CHANGELOG must be updated when APIs evolve.  

### VIII. Semantic Versioning
Follow SemVer strictly.  
Breaking changes → major bump.  
Backward-compatible features → minor bump.  
Bug fixes → patch bump.  

### IX. Spec-Kit Flow (NON-NEGOTIABLE)
All features and significant changes must go through the `/specify → /plan → /tasks` flow.  
Specs live under `specs/` and must capture the **why**, **how**, and **what**.  

### X. Observability & Integration
Logs should be easy to integrate with downstream tools (Grafana Loki, ELK, etc.).  
Include metadata like timestamp, level, source, and context in every log event.  

### XI. Quality Gates (NON-NEGOTIABLE)
- **CI Validation**: All code must pass the GitHub Actions workflow before merging.  
- **Formatting & Linting**: The following commands must run with **zero errors** before any commit is accepted:  
  ```bash
  make format
  make lint
