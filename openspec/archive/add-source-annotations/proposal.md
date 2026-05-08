# Proposal: Add Source Annotations

**Change ID:** `add-source-annotations`
**Created:** 2026-05-08
**Status:** Implementation Complete
**Completed:** 2026-05-08

---

## Problem Statement

- Users can browse highlighted source files, but cannot leave durable notes on specific files or lines while studying a project.
- Learners reviewing unfamiliar repositories need a way to mark questions, insights, and follow-up items close to the code they refer to.
- Current workaround is to copy paths and line numbers into external notes, which breaks context and makes later review harder.

## Proposed Solution

- Add project-scoped source annotations attached to repository-relative file paths and optional line numbers.
- Add backend CRUD APIs backed by SQLite so annotations survive refreshes and project reloads.
- Extend the source browser preview with line-level annotation actions, visible markers, and an annotation side panel/list.
- Keep annotations separate from cloned repository contents; no source files are modified.

## Scope

### In Scope

- Create, list, update, and delete annotations for a project.
- Attach annotations to a file path and optionally a single source line.
- Show annotation markers in the code viewer gutter or line area.
- Show a compact annotation list for the active file, with jump-to-line behavior.
- Cover backend repository/API behavior, frontend state behavior, component rendering, and E2E annotation flow.

### Out of Scope

- Multi-user collaboration, author identity, mentions, or permissions.
- Inline rich text editing beyond plain text or lightweight Markdown-style display.
- Anchoring annotations to code after Git updates or line drift.
- Exporting annotations into reports or writing them back into the source repository.

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| Database | Yes | Add `source_annotations` table keyed by project id, path, line, body, timestamps. |
| API | Yes | Add REST endpoints under `/api/projects/{project_id}/source/annotations`. |
| State | Yes | Add composable state for active-file annotations, pending mutations, and stale-response guards. |
| UI | Yes | Add line markers, create/edit/delete controls, and active-file annotation list in `SourceBrowser`. |

## Architecture Considerations

- Backend should follow the existing `Database` class pattern in `backend/app/database.py` and route style in `backend/app/main.py`.
- Annotation access should reuse project existence checks, but annotations can be read for any existing project and should validate source readiness when creating line-bound annotations against real source files.
- Frontend should keep component boundaries intact: `SourceBrowser.vue` renders and emits annotation intents, while `useProjectHelper.js` owns API calls and project-scoped state.
- The line-based code viewer already renders one `.code-line` per line, which provides a stable UI hook for annotation markers and jump behavior.

## Success Criteria

- [ ] Users can add a note to a selected source line and see a marker immediately.
- [ ] Users can view all annotations for the active file after refreshing or reloading the project.
- [ ] Users can edit and delete annotations without changing source files.
- [ ] Switching projects or files cannot apply stale annotation responses to the wrong project/file.
- [ ] Unit, backend E2E, frontend component, and Playwright E2E tests pass after implementation.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Line numbers become stale after repository updates | Medium | Medium | Store path and line only for the first version; make drift handling out of scope and document it. |
| Source browser becomes visually crowded | Medium | Medium | Use small gutter markers and a collapsible/compact annotation panel. |
| Stale async responses show annotations for the wrong context | Medium | High | Mirror existing source tree/file request token guards in annotation fetches. |
| Invalid paths or binary files receive annotations | Low | Medium | Reuse source path validation for line-bound annotations and add API tests. |

---

## Archive Information

**Archived:** 2026-05-08 15:57
**Duration:** 0 days
**Outcome:** Successfully implemented

### Files Modified
- `backend/app/database.py` - Added source annotation persistence methods and schema.
- `backend/app/main.py` - Added source annotation CRUD API endpoints and validation.
- `frontend/src/composables/useProjectHelper.js` - Added annotation state, mutations, and stale response guards.
- `frontend/src/components/SourceBrowser.vue` - Added annotation markers, form, list, edit/delete actions, and line jump behavior.
- `docs/TESTING_CHECKLIST.md` - Documented source annotation test coverage expectations.
- `backend/tests/e2e/test_api_core_flow.py` and `backend/tests/unit/test_database.py` - Added backend annotation coverage.
- `frontend/src/components/SourceBrowser.test.js`, `frontend/src/composables/useProjectHelper.test.js`, and `frontend/tests/e2e/project-helper.spec.js` - Added frontend unit and E2E annotation coverage.

### Specs Updated
- `openspec/specs/source-annotations.md`
