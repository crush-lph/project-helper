# Frontend Architecture Notes

## Component split rule

`frontend/src/App.vue` should stay as the page orchestration layer. Keep data ownership, cross-module workflow, and top-level composition there through `useProjectHelper`, but move visible feature areas into focused components.

Current feature components:

- `components/CommandPanel.vue`: repository input and analysis command area.
- `components/ProjectSidebar.vue`: cached project list and project actions.
- `components/ProgressPanel.vue`: analysis progress, stage map, and event log.
- `components/ViewSwitcher.vue`: workspace view tabs.
- `components/SourceBrowser.vue`: source tree, folder collapse state, and file preview.
- `components/ReportPanel.vue`: sanitized markdown report rendering.
- `components/ChatPanel.vue`: source Q&A messages and input.

When adding frontend functionality:

- Add or extend a component for a distinct visual/workflow area instead of growing `App.vue`.
- Put shared stateful workflow logic in `composables/`.
- Put reusable pure helpers in `helpers/`.
- Keep component props and events explicit, so each component can be read without scanning the whole page.
- Run `npm run build` after each frontend change.
