# Implementation Tasks: Add Source Annotations

**Change ID:** `add-source-annotations`

---

## Phase 1: Foundation (Data Layer)

- [x] 1.1 Add `source_annotations` SQLite table with project foreign key, path, optional line, body, and timestamps.
- [x] 1.2 Add database methods to list, create, update, and delete annotations by project and file path.
- [x] 1.3 Add repository/database unit tests for annotation persistence, ordering, and project isolation.

**Quality Gate:** PASSED 2026-05-08
- [x] Code analysis passes
- [x] Backend unit tests pass

---

## Phase 2: API & Validation

- [x] 2.1 Add Pydantic request models for creating and updating source annotations.
- [x] 2.2 Add `GET`, `POST`, `PATCH`, and `DELETE` annotation endpoints under the project source API.
- [x] 2.3 Validate project existence, source readiness for line-bound annotations, safe file paths, and valid line ranges.
- [x] 2.4 Add API E2E tests for create/list/update/delete and invalid project/path cases.

**Quality Gate:** PASSED 2026-05-08
- [x] Code analysis passes
- [x] Backend E2E tests pass

---

## Phase 3: Frontend State

- [x] 3.1 Add annotation state to `useProjectHelper.js` for active file annotations and mutation loading.
- [x] 3.2 Fetch annotations when a source file is loaded and clear them when the project/file changes.
- [x] 3.3 Guard annotation responses with project id, file path, and request tokens.
- [x] 3.4 Add composable tests for stale responses and CRUD state updates.

**Quality Gate:** PASSED 2026-05-08
- [x] Frontend unit tests pass
- [x] State transitions tested

---

## Phase 4: User Interface

- [x] 4.1 Extend `SourceBrowser.vue` with line annotation markers and an add button on source lines.
- [x] 4.2 Add active-file annotation list with jump-to-line, edit, and delete actions.
- [x] 4.3 Keep the source browser responsive on desktop and mobile layouts.
- [x] 4.4 Add component tests for marker rendering, emits, and empty/error states.

**Quality Gate:** PASSED 2026-05-08
- [x] Frontend unit tests pass
- [x] Browser layout check passes via Playwright E2E

---

## Phase 5: E2E & Documentation

- [x] 5.1 Add Playwright E2E flow for adding, editing, deleting, and reloading annotations.
- [x] 5.2 Update project documentation/checklist to describe annotation behavior and test coverage.
- [x] 5.3 Run backend tests, frontend unit tests, E2E tests, build, and diff checks.

**Quality Gate:** PASSED 2026-05-08
- [x] All tests pass
- [x] Code analysis clean for touched files; full `mypy app` still reports existing issues in `llm.py` and `observability.py`
- [x] Documentation synced

---

## Completion Checklist

- [x] All phases complete
- [x] All quality gates passed
- [x] Documentation synced
- [x] Ready for `/openspec-archive`
