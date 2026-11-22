# Guidelines

Coding standards, architecture rules, and agent workflow.

## Code guidelines
- **Self-documenting code.** Write code that reads clearly on its own. Use descriptive names and flat control flow (early returns over multi-layer nesting). Keep comments minimal and concise. Reserve them for *why*, non-obvious constraints, and maintained module invariants. A short local heading is fine when a file needs to explain an ownership, lifecycle, or persistence rule. Do not add commentary that merely narrates the code.
- **Performance first.** Avoid dynamic evaluations and allocations in hot paths. Cache aggressively.
  *Practical examples for agents (match the pattern to local and Google Drive snapshot scanning):*
  1. **Strict field projection.** Request only `nextPageToken, files(id, name, mimeType, size, modifiedTime)` on `files.list` and `id, name, mimeType` on `files.get`. Never omit `fields` or fetch full Drive metadata payloads.
  2. **Max page size.** Paginate `files.list` with `pageSize=1000` and exhaust `nextPageToken` to minimize API round-trips.
  3. **Thread-local Drive clients with bounded concurrency.** Build one `drive` v3 service per worker thread via `threading.local()` with `cache_discovery=False` under `ThreadPoolExecutor(max_workers=8)`. Never share a service instance across threads or rebuild clients per folder.
  4. **Cycle-safe single-visit traversal.** Track `visited_folder_ids` so shortcuts or repeated folder IDs are never re-fetched or infinitely traversed.
  5. **Single-pass local scans.** Collect stats and cumulative folder sizes in one `os.scandir` pass (`scan_tree`) without re-statting or walking trees twice. Keep local scans stdlib-only (`tqdm` optional; Drive packages only for cloud scans).
  6. **Read-only scope and Shared Drive flags.** Keep `SCOPES` at `drive.readonly` and pass `supportsAllDrives=True` and `includeItemsFromAllDrives=True` consistently so shared drives do not silently drop items.
- **Measure twice, cut once.** Read the surrounding code, verify assumptions, and trace downstream impact before editing so changes land cleanly on the first pass. Prefer small, deliberate changes over broad refactors.
- **Reuse existing helpers.** Before writing new logic, search the codebase for an existing helper that already does the job. Prefer intuitive shared helpers over inlining repeated lines of code for identical operations. If a change duplicates logic across callsites, extract it into a shared helper instead.
- **Work in logical slices.** Prioritize small, precise code changes rather than big blocks to prevent tooling and scope failures, especially during large refactors. Be surgical!
- **YAGNI.** Do not add abstractions, features, or complexity without a clear need.

## Agent behavior
- Read every rule and referenced skill before starting work. Confirm adherence to the user.
- Keep responses concise and focused on the task.
- Follow existing code style and formatting for each directory and its associated files.
- For writing work, read `.agents/skills/unslop/SKILL.md` and follow it even if the harness does not auto-load always-active skills. This applies to docs, prompts, comments, and user-facing copy.

### Guardrails
- **No automated git commits.** Never execute git commit commands or automate commits unless explicitly instructed. The user handles all commits manually or through the commit pipeline.
- **Downstream safety.** When modifying shared helpers, configurations, command-line interfaces, or core abstractions, stop and verify that downstream callers and consumers remain unbroken. Do not rely on speculation.
- **Respect established structure.** Do not move, rename, or reorganize files, folders, or asset paths. Keep changes localized to the files being edited.
- **Preserve behavioral contracts.** Refactors must not alter existing functionality, return types, or output schemas unless there is an explicit functional win.
- **No test harness creation during implementation.** Do not create new test suites or test harnesses while implementation work is in progress. Manual runtime tests carry higher value because test harnesses written against incomplete code are fragile and waste implementation time.
- **No premature finalization.** Never declare work done, implemented, or complete until the user explicitly says so. Do not write completion summaries or treat a slice as finished on your own.
