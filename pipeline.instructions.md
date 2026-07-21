## Critical Constraint

**Never modify the working tree.** Do not edit, create, or delete files. Your only permitted Git operations are staging (`git add`), committing, and pushing. Do not rewrite history or create unnecessary micro-commits.

---

### Instructions

To generate accurate commits and commit messages, you must understand the full context of the recent changes. Follow these steps:

1. **Review the working tree** using `git status` and `git diff`.
2. **Group changes into logical commits** — one commit per feature, fix, refactor, documentation update, build change, or other cohesive change. Keep related changes together, even if they span multiple files. Only split commits when the changes are independent and could reasonably be reviewed or reverted separately.
3. **Stage only the files for the current commit** using `git add`, then verify the staged changes with `git diff --cached`.
4. **Familiarize yourself with the project structure** and its related files to understand the environment. **Skip this step when the diffs contain only minimal or straightforward changes.**
5. **Read current and recent AI session data** that are strictly related to the code changes made. This focuses your context without needing to search everything. Refer to `.agents/sessions.md` to find the relevant session IDs and instructions on how to query the session logs. **Skip this step when the diffs contain only minimal or straightforward changes.**
6. **Use subagents efficiently** — delegate independent tasks (e.g., reading files, running git commands) to parallel subagents rather than doing them sequentially. This reduces context window usage and speeds up the pipeline.
7. **Commit the current logical group** using `git commit -m`, following the commit message guidelines below. Repeat until the working tree is clean.
8. **Push all commits** to the remote using `git push`.

## How to generate a commit message

After gathering context from the steps above, generate a commit message that follows best practices:

* **Header**: Write a concise summary in the imperative mood (e.g., "Fix bug in login flow"); keep it under 50 characters.
* **Body**: Provide a detailed explanation of *what* and *why* the changes were made, not just *how*. Separate it from the header with a blank line. Use bullet points for applicable items to improve readability.
* **Technical Details**: Document any complex, technical, or non-obvious implementation decisions or problems encountered. If AI sessions were used, specifically note anything that stood out—such as issues that took a long time to fix or areas where the user and AI got stuck.
