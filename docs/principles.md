# Skill development principles

This repository is a personal collection of reusable agent skills. Start with a
real, repeated task; add only the mechanism that makes that task safer or clearer.

1. **One useful workflow per skill.** Keep each directory independently usable.
   Do not require repository-level policy files or another skill by default.
2. **Short entry point, focused references.** Put trigger and decision rules in
   `SKILL.md`; load detailed recipes only when needed. Avoid duplicate instructions.
3. **Deterministic checks where they matter.** Prefer small standard-library
   helpers and trusted CLIs over a framework or a custom API client.
4. **Credentials stay outside reasoning.** Invoke the approved authenticated
   tool; do not retrieve tokens or improvise authentication recovery.
5. **Permission follows the requested operation.** Read-only inspection is not
   permission to write. Stop at a changed target or scope, without asking again
   for authority already clearly granted.
6. **Fail closed and preserve work.** Inspect before writing, preserve unrelated
   changes, and verify uncertain outcomes before retrying.
7. **Make limits visible.** A skill is guidance, not a sandbox. Describe which
   checks are enforced by code and which depend on the agent or environment.
8. **Test the artifact, not just the idea.** Use isolated fixtures for helpers,
   check standalone references, and distinguish executed tests from behavioral
   scenarios and live-service validation.

Keep the root README in Japanese and skill instructions, technical references,
and code in English. Prefer one canonical procedure with migration links over
parallel translations that can drift.
