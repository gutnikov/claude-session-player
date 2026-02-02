# Claude Session Player — Issue Tracker

Issues are numbered 01–10 and designed to be implemented sequentially.
Each issue writes a worklog to `issues/worklogs/XX-worklog.md` upon completion.
Subsequent issues MUST read all prior worklogs before starting.

## Execution Order

| Issue | Title | Dependencies |
|---|---|---|
| 01 | Project scaffolding & models | None |
| 02 | JSONL parser & line classification | 01 |
| 03 | User message rendering | 01, 02 |
| 04 | Assistant text block rendering | 01, 02 |
| 05 | Tool call rendering & abbreviation | 01, 02, 04 |
| 06 | Tool result matching & rendering | 05 |
| 07 | Thinking, turn duration & system messages | 01, 02 |
| 08 | Progress message rendering | 05, 06 |
| 09 | Compaction, sub-agents & edge cases | All prior |
| 10 | Integration tests with real sessions | All prior |

## Worklog Convention

Each issue creates `issues/worklogs/XX-worklog.md` with:
- What was implemented
- Files created/modified
- Design decisions made
- Known issues or deviations from spec
- Test results
