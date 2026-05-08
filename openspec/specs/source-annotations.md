# Source Annotations Specification

## Requirements

### Project-Scoped Source Annotations

The system shall let users create persistent annotations for a project source file without modifying the cloned repository files.

#### Scenario: Create a line annotation
- GIVEN a ready project and an opened text source file
- WHEN the user adds an annotation to line 12
- THEN the annotation is saved with the project id, repository-relative file path, line number, body, and timestamps
- AND the source file content remains unchanged

#### Scenario: Create a file-level annotation
- GIVEN a ready project and an opened text source file
- WHEN the user adds an annotation without selecting a specific line
- THEN the annotation is saved for the file path with no line number

### Annotation Retrieval

The system shall return annotations filtered by project and optionally by source file path.

#### Scenario: Load annotations for active file
- GIVEN a user opens `src/main.js` in project A
- WHEN the frontend requests annotations for that path
- THEN only annotations belonging to project A and `src/main.js` are returned
- AND annotations for other projects or files are excluded

### Annotation Updates

The system shall let users update and delete existing annotations in the current project.

#### Scenario: Update annotation body
- GIVEN an existing annotation in the active project
- WHEN the user saves edited annotation text
- THEN the stored body and updated timestamp are changed
- AND the annotation remains attached to the same project, path, and line

#### Scenario: Delete annotation
- GIVEN an existing annotation in the active project
- WHEN the user deletes the annotation
- THEN it is removed from the active file annotation list
- AND subsequent reloads do not return it

### Source Browser Annotation UI

The source browser shall show annotation affordances beside source lines and a readable annotation list for the active file.

#### Scenario: Show line marker
- GIVEN a source file has an annotation on line 8
- WHEN the file is displayed
- THEN line 8 shows an annotation marker in or near the gutter
- AND the active-file annotation list includes the same annotation

#### Scenario: Jump to annotated line
- GIVEN the active-file annotation list contains an annotation for line 30
- WHEN the user selects that annotation
- THEN the code preview scrolls to line 30
- AND the line is visually highlighted or focused

### Async Context Safety

The frontend shall not apply stale annotation responses after the active project or active file changes.

#### Scenario: Ignore stale annotation response
- GIVEN annotations for project A and file `a.py` are loading
- WHEN the user switches to project B before the response resolves
- THEN the project A response is ignored
- AND project B does not display project A annotations

### Source File Preview

The source file preview shall remain responsible for rendering highlighted source lines and shall add annotation controls without breaking code folding, syntax highlighting, or directory browsing.

#### Scenario: Preserve folding and highlighting
- GIVEN a source file supports syntax highlighting and foldable regions
- WHEN annotations are displayed on one or more lines
- THEN syntax highlighting remains visible
- AND folding controls continue to hide and reveal the same line ranges
