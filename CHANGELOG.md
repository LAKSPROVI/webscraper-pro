# Changelog

## 2026-03-22

### Added
- Backend hardening with rate limiting, security headers, trusted hosts, gzip, and an initial auth endpoint.
- Frontend resilience and QA tooling with error boundary, Vitest, Storybook base setup, and ESLint configuration.
- Release and runtime operations support with CI workflow, health and release scripts, Kubernetes starter manifests, and structured worker logging.
- Repository staging helper to batch related files into logical commits.

### Changed
- API data, jobs, and scrape routes now include request throttling and better cache behavior.
- Worker and infrastructure configuration were aligned for release validation and runtime operations.
- Test and validation flow now includes backend tests, frontend tests, typecheck, build, and offline Alembic verification.

### Validation
- Backend tests: 143 passed.
- Frontend tests: passed.
- Frontend typecheck: passed.
- Frontend build: passed.
- Alembic offline SQL generation: passed.

### Commits
- 7aecbe1 feat(api): harden backend security and auth
- 0a2060a feat(frontend): add resilience and QA tooling
- e192797 chore(infra): prepare release workflow and runtime ops
- 7d77eb5 chore(repo): add staged commit batching helper