---
name: spec-driven-development
description: Turn software change requests into testable specifications and small dependent tasks, then implement and verify the authorized work with evidence and resumable notes. Use for spec-first feature work, bug fixes, test planning, or resuming a planned change. A request for a plan or tests alone does not authorize implementation. Do not impose this workflow on general questions or Git-only operations.
---

# Spec-driven development

Agree on observable completion conditions, implement small slices, and report
what was actually verified. This prevents plausible implementation choices from
silently replacing the requested behavior. It is a development procedure, not
an execution sandbox, test runner, or permission grant.

## Enter at the requested stage

Read the request, applicable repository instructions, existing specification,
relevant code/tests, and current changes before proposing work. Preserve unrelated
edits. Separate established requirements from assumptions and open questions.

- **Plan/spec only:** inspect and propose; do not implement, generate executable
  tests, or save documents unless requested. Clarify consequential ambiguity.
- **Tests only:** write/review/run the authorized tests; do not silently fix the
  production code to make them pass. Report expected failures explicitly.
- **Implementation:** reuse the approved requirements and plan. Do not restart
  planning or seek repeated permission for work already clearly authorized.
- **Resume:** reconcile the handoff with actual files, branch/HEAD where relevant,
  and test state before taking the next task. A note is not proof of current state.

Ask before choosing between materially different user-visible behaviors or
expanding scope. Record low-impact assumptions that allow progress. A clear,
bounded implementation request can itself establish the requirements baseline;
a separate ceremonial approval is not required. Reconfirm material changes to it.

## Choose the smallest useful record

For a small, unambiguous change, state the purpose, acceptance condition, and
verification method briefly in the conversation. Do not create a work-item file,
task graph, or test framework merely to satisfy this skill.

For multi-task or cross-session work, update the project's existing canonical
record. If none exists and persistence is in scope, use
[work-item.md](assets/work-item.md) at a location consistent with repository
conventions, confirming the location if unclear. This asset is a starting point,
not a mandatory schema. Omit unused sections; keep output in the user's/project's
language. Do not keep a second specification that can drift from the first.

## Establish specification, tasks, and test plan

1. State the goal, scope, non-goals, constraints, and observable acceptance
   criteria. Describe **what must happen**, including relevant error behavior,
   without prematurely prescribing internal implementation details.
2. Break the work into independently verifiable behavior slices. Identify
   dependencies and each slice's completion condition. A Markdown list/table
   is enough; do not introduce a task engine or automatic parallel agents.
3. Map each acceptance criterion to a verification method and expected result.
   Prefer existing tests and tooling. Include boundary, error, integration, and
   regression checks in proportion to the affected behavior and risk. If a
   performance target matters, agree on workload, environment, and metric.

Use Given/When/Then when it makes the behavior clearer, not as compulsory syntax.
Resolve conflicting criteria before implementation. A test plan describes how
to evaluate the specification; it does not replace the specification.

## Execute one slice at a time

Read [testing.md](references/testing.md) when designing/reviewing executable tests
or interpreting test failures. For documentation-only changes, direct review and
relevant link/format checks can suffice.

1. Establish relevant baseline behavior before changing it, where feasible.
   Record pre-existing failures instead of attributing all failures to this task.
2. Prefer a test-first loop for testable behavior: write one meaningful test,
   inspect its expected result against the requirement, and verify that it fails
   for the missing/wrong behavior. Then implement the smallest change and rerun.
   An environment/import/syntax failure is not the intended failing test.
3. Extend coverage to the agreed edge cases and affected existing behavior.
   Review test quality separately from executing tests. Do not weaken assertions,
   delete checks, or broaden mocks just to obtain a passing result. Correct a
   genuinely wrong test using the agreed requirement and explain the correction.
4. Inspect the actual diff for scope drift and unintended changes. Rerun relevant
   checks after the last meaningful edit; earlier results may no longer apply.
5. Record the completed slice, evidence, unresolved issues, and next dependency-
   ready task. Test creation alone is not completion. Preserve failing/unverified
   status when execution or acceptance checks cannot be completed.

Exploration or non-executable acceptance criteria may need a different order.
Explain the substitute validation and its limits rather than manufacturing a
test-first success. Test difficulty is a signal to investigate requirements,
dependencies, environment, or design—not permission for an unrelated refactor.

## Stop, reassess, and resume

Pause the affected work when attempts repeat without new evidence, the fix keeps
expanding, requirements conflict, or a new permission is needed. Summarize the
reproduction, attempted approaches/results, remaining hypotheses, and the
specific human decision needed. Do not loop on the same command or restart a
session as a substitute for diagnosis. Independent authorized tasks may continue.

Before a handoff, record the accepted requirements, completed/pending tasks,
verified state, remaining local changes, blockers, and the next concrete action.
Identify the tested revision or working diff; do not attach secrets or raw
sensitive logs. In a new session, recheck facts that may have changed and rerun
affected checks rather than inheriting a stale PASS.

## Finish and respect boundaries

Report delivered behavior, acceptance criteria verified, commands/checks and
actual outcomes, unresolved failures, and unverified limitations. Distinguish
PASS, FAIL, BLOCKED, and NOT RUN; a justified NOT APPLICABLE check is not a PASS.
For a plan-only request, completion means a usable plan—not implemented behavior.

Do not install dependencies, watchers, CI, or external services without authority.
Inspect unfamiliar test commands for external/destructive side effects before
running them. Use isolated fixtures and synthetic inputs, not real secrets or
production resources. Self-review and green tests do not prove complete correctness.

Git checkpoints can be useful but are not automatic. Commit, push, and PR creation
require their own user authorization. If available and appropriate, use the
separate `controlled-github` skill for those requested operations; it is not a
dependency and does not extend the development scope.
