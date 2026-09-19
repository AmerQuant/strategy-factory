# Standing prompt (Claude Code)

Paste this at the start of every batch session:

```
Read CLAUDE.md, HANDOFF.md (section 'Next batch') and docs/decisions/decisions_log.md.
PHASE 1 — PLAN: draft one task file per task of the next batch in docs/tasks/ (based on the acceptance criteria in docs/features.md, the spec, the design and the decisions log; cite feature and decision IDs), plus docs/tasks/RUNBOOK_<batch>.md. Put every assumption or open question in docs/decisions/pending.md. Commit on branch docs/<batch>. Then STOP and print a plan summary: tasks, features covered, decisions used, assumptions, open questions.
PHASE 2 — only after the user writes 'Plan approved' (possibly with corrections): execute the runbook. Per task: tests first, implementation, acceptance commands, acceptance-reviewer subagent, fix findings, review file in docs/reviews/, commit. Critical tasks (decision D-402) STOP after their review and wait for 'Approved' before the next task. At the end: open the PR(s) with gh (body = reviews), update HANDOFF.md status, print the batch report. Never merge without 'Approved. Merge …'.
```
