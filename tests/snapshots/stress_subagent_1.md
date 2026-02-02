❯ Implement TM-023: Intent Workflow by creating `src/orca/workflows/intent.py`.
  
  ## Context from existing codebase (read these files for patterns):
  - `src/orca/workflows/work_item.py` and `src/orca/workflows/issue.py` for workflow patterns
  - `src/orca/tasks/types.py`: Intent states: DRAFT, REFINING, AWAITING_CONFIRMATION, CONFIRMED, DECOMPOSING, DECOMPOSED
  - `src/orca/tasks/state_machine.py`: StateMachine class
  - `src/orca/tasks/workflow_models.py`: IntentWorkflowInput, IntentWorkflowResult, TaskId
  - `src/orca/tasks/signals.py`: UserReplySignal, CancellationSignal
  - `src/orca/activities/ai_tasks.py`: refine_intent, decompose_intent, confirm_issue activities
  
  ## Requirements from GitHub issue #24:
  
  ### 1. IntentWorkflow class with:
  - `@workflow.defn` decorator
  - Signal handlers: `user_reply(UserReplySignal)`, `cancel(CancellationSignal)`
  - Query handler: `get_status() -> dict[str, Any]`
  - Main workflow `run(input: IntentWorkflowInput) -> IntentWorkflowResult`
  
  ### 2. State transitions:
  ```
  DRAFT -> REFINING (automatic on start)
  REFINING -> AWAITING_CONFIRMATION (when ready_for_confirmation=True)
  REFINING -> REFINING (when questions answered, iterate)
  AWAITING_CONFIRMATION -> CONFIRMED (user confirms)
  AWAITING_CONFIRMATION -> REFINING (user requests revisions)
  CONFIRMED -> DECOMPOSING (automatic)
  DECOMPOSING -> DECOMPOSED (all issues created)
  ```
  
  ### 3. Key behaviors:
  - Refine intent using refine_intent activity
  - If questions needed, wait for user_reply signal (human-in-the-loop)
  - Get confirmation from user via Slack
  - Decompose confirmed intent into issues
  - Start IssueWorkflows for decomposed issues
  
  ### 4. Add workflow to `src/orca/workflows/__init__.py` and `src/orca/worker/main.py`
  
  ### 5. Create tests in `tests/test_workflows/test_intent.py`:
  - Test state transitions
  - Test signal handling
  - Test human-in-the-loop flow
  
  Use patterns from existing workflow files. Use `with workflow.unsafe.imports_passed_through():` for imports.

● 
  
  I'll start by reading the existing files to understand the patterns.
● Read(work_item.py)
  └      1→"""Work Item Workflow for executing and reviewing individual units of work.
         2→
         3→This workflow manages the lifecycle of a single work item from assignment
         4→through execution and review to completion or failure.
  └ …
● Read(issue.py)
  └      1→"""Issue Workflow for managing the lifecycle of a GitHub issue.
         2→
         3→This workflow manages an issue from initial triage through planning,
         4→work execution, verification, and resolution.
  └ …
● Read(types.py)
  └      1→"""Task type enums and state definitions for the Task Management System."""
         2→
         3→from enum import Enum
         4→
  └ …
● Read(state_machine.py)
  └      1→"""State machine validator for task state transitions."""
         2→
         3→from orca.tasks.types import (
         4→    TASK_TYPE_TERMINAL_STATES,
  └ …
● Read(workflow_models.py)
  └      1→"""Workflow data classes for the Task Management System.
         2→
         3→These dataclasses are used as inputs and outputs for Temporal workflows
         4→that manage tasks through their lifecycle.
  └ …
● Read(signals.py)
  └      1→"""Signal data classes for workflow communication in the Task Management System.
         2→
         3→These dataclasses define the signals used for inter-workflow communication
         4→and external event handling in the Temporal-based task management system.
  └ …
● Read(ai_tasks.py)
  └      1→"""Generic AI task activities.
         2→
         3→This module provides a schema-driven wrapper around Claude Code execution.
         4→It:
  └ …
● Read(__init__.py)
  └      1→"""Temporal workflows module."""
         2→
         3→from orca.workflows.ask_project import AskProjectWorkflow
         4→from orca.workflows.example import ExampleWorkflow
  └ …
● Read(main.py)
  └      1→"""Temporal worker entrypoint."""
         2→
         3→import asyncio
         4→import logging
  └ …

● Now let me check the existing tests for patterns and also look at the GitHub activities for `create_issue_comment` / Slack activities to understand how to send messages.
● Glob(tests/test_workflows/*.py)
  └ /Users/agutnikov/work/orca/tests/test_workflows/__init__.py
    /Users/agutnikov/work/orca/tests/test_workflows/test_work_item.py
    /Users/agutnikov/work/orca/tests/test_workflows/test_issue.py
● Read(github.py)
  └      1→"""GitHub-related Temporal activities."""
         2→
         3→from collections.abc import Callable
         4→from typing import Any
  └ …
● Read(slack.py)
  └      1→"""Slack-related Temporal activities."""
         2→
         3→from collections.abc import Callable
         4→from dataclasses import dataclass
  └ …

● Read(test_issue.py)
  └      1→"""Tests for IssueWorkflow."""
         2→
         3→from __future__ import annotations
         4→
  └ …
● Read(slack.py)
  └     50→        channel=input.channel,
        51→        text=input.text,
        52→        blocks=input.blocks,
        53→        thread_ts=input.thread_ts,
  └ …
● Read(projects.py)
  └      1→"""Projects configuration loader."""
         2→
         3→from pathlib import Path
         4→
  └ …

● Now I have a thorough understanding of all patterns. Let me also check the GitHub activities for creating issues, since the workflow needs to create GitHub issues from decomposed intents.
● Grep(create_issue)
  └ Found 3 files
    src/orca/activities/task_github.py
    src/orca/activities/github.py
    src/orca/integrations/github_client.py

● Read(task_github.py)
  └      1→"""Task GitHub activities for creating and managing task issues."""
         2→
         3→import re
         4→from dataclasses import dataclass
  └ …

● Now I have a complete picture. Let me create the workflow and tests.
● TaskCreate(…)
  └ Task #1 created successfully: Create IntentWorkflow in src/orca/workflows/intent.py

● TaskCreate(…)
  └ Task #2 created successfully: Register IntentWorkflow in __init__.py and worker

● TaskCreate(…)
  └ Task #3 created successfully: Create tests in tests/test_workflows/test_intent.py

● TaskCreate(…)
  └ Task #4 created successfully: Run tests and lint checks

● TaskUpdate(…)
  └ Updated task #1 status

● Write(intent.py)
  └ File created successfully at: /Users/agutnikov/work/orca/src/orca/workflows/intent.py

● TaskUpdate(…)
  └ Updated task #1 status
● TaskUpdate(…)
  └ Updated task #2 status

● Now register the workflow in `__init__.py` and `worker/main.py`.
● Edit(__init__.py)
  └ The file /Users/agutnikov/work/orca/src/orca/workflows/__init__.py has been updated successfully.

● Edit(main.py)
  └ The file /Users/agutnikov/work/orca/src/orca/worker/main.py has been updated successfully.

● Edit(main.py)
  └ The file /Users/agutnikov/work/orca/src/orca/worker/main.py has been updated successfully.

● TaskUpdate(…)
  └ Updated task #2 status
● TaskUpdate(…)
  └ Updated task #3 status

● Now create the tests.
● Write(test_intent.py)
  └ File created successfully at: /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py

● TaskUpdate(…)
  └ Updated task #3 status
● TaskUpdate(…)
  └ Updated task #4 status

● Now let me run the tests and lint.
● Bash(Run IntentWorkflow tests)
  └ (eval):1: command not found: python

● Bash(Run IntentWorkflow tests)
  └ /usr/bin/python3
    ImportError while loading conftest '/Users/agutnikov/work/orca/tests/conftest.py'.
    tests/conftest.py:5: in <module>
        from temporalio.testing import WorkflowEnvironment
    E   ModuleNotFoundError: No module named 'temporalio'

● Bash(Find Python environment)
  └ lrwxr-xr-x@ 1 agutnikov  staff  44 Jan 28 08:00 .venv/bin/python -> /opt/homebrew/opt/python@3.14/bin/python3.14
    lrwxr-xr-x@ 1 agutnikov  staff   6 Jan 28 08:00 .venv/bin/python3 -> python
    lrwxr-xr-x@ 1 agutnikov  staff   6 Jan 28 08:00 .venv/bin/python3.14 -> python

● Bash(Run IntentWorkflow tests with venv Python)
  └ Command running in background with ID: b5fb988. Output is being written to: /private/tmp/claude/-Users-agutnikov-work-orca/tasks/b5fb988.output

● Bash(Test import of IntentWorkflow)
  └ Import OK

● Bash(Test import from __init__)
  └ Init import OK

● Bash(Test worker import)
  └ Worker import OK

● Bash(Check test output)
  └ 

● Bash(Run IntentWorkflow tests)
  └ Command running in background with ID: ba3fb65. Output is being written to: /private/tmp/claude/-Users-agutnikov-work-orca/tasks/ba3fb65.output

● Bash(Wait and check test output)
  └ ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/agutnikov/work/orca
  └ …

● Tests are running. Let me wait for them to complete.
● Bash(Wait more and check test output)
  └ ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/agutnikov/work/orca
  └ …

● The integration test is still running (time-skipping environment can be slow). Let me wait longer.
● Bash(Wait and check full test results)
  └ ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/agutnikov/work/orca
  └ …

● The test is still hanging at the first integration test. This is likely because the Temporal time-skipping test environment is downloading/starting a test server for the first time, or there's a signal timing issue. Let me check if the test is stuck due to the workflow waiting for user reply before the signal is sent.
  
  The issue is that in the test, the workflow starts, transitions DRAFT -> REFINING, refines (gets ready_for_confirmation=True), transitions to AWAITING_CONFIRMATION, runs confirm_issue, sends confirmation to Slack, and then waits for user reply. The signal might be sent before the workflow reaches the wait_condition. Let me look at how the issue workflow tests handle this -- they don't have signal-dependent tests that complete. The cancellation test just fires the signal and it works because the workflow processes it at the top of the loop.
  
  The problem is timing: the signal arrives before or after the `wait_condition`. In Temporal's time-skipping env, the signal should work because `wait_condition` checks the condition on each signal. Let me check if there's a startup delay causing the signal to arrive before the workflow is even started.
  
  Let me cancel the hanging test and check if there's an issue with the retry policy on the mock activities.
● Bash(Kill hanging test process)
  └ killed

● The issue might be that the `decompose_intent` mock activity raises an exception on retries. Let me look more carefully -- the mock `mock_decompose_intent_success` is registered with `@activity.defn(name="decompose_intent")` but the workflow runs `decompose_intent` which is imported via `workflow.unsafe.imports_passed_through()`. In the Temporal test, mock activities override by name.
  
  Actually, the likely issue is that the activities are being retried with default retry policy. Let me check what happens when activities fail -- the `execute_activity` calls don't have retry policies specified, so they use defaults which retry indefinitely. But the mocks should succeed.
  
  Wait, I think the real issue might be that the `test_happy_path_no_questions` sends a signal immediately after `start_workflow`, but the workflow needs time to reach `AWAITING_CONFIRMATION` and the `wait_condition`. In time-skipping mode, the workflow might not have advanced enough when the signal is sent. Let me add a small delay or use a different approach.
  
  Actually, looking at the issue test `test_cancellation_during_processing` -- it also sends a signal immediately and it works. The difference is that cancellation is checked at the top of each loop iteration, while `user_reply` is only picked up by `wait_condition`.
  
  The time-skipping environment should handle this -- the signal sets `self._user_reply` and `wait_condition` should re-evaluate. But maybe the workflow hasn't reached the `wait_condition` yet when the signal arrives.
  
  Let me restructure the test to add a small sleep before sending the signal, or better yet, poll for the workflow state before signaling.
● Read(test_intent.py)
  └    188→@activity.defn(name="refine_intent")
       189→async def mock_refine_intent_needs_questions(input: object) -> RefineIntentOutput:
       190→    """Mock refine_intent that needs to ask questions."""
       191→    return RefineIntentOutput(
  └ …

● The issue is likely that the integration tests need to wait for the workflow to reach the AWAITING_CONFIRMATION state before sending the user_reply signal. Let me update the tests to poll the status query before sending signals.
● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Now update all the integration tests to use the polling helper.
● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Now update the cancellation, status query, and decomposition failure tests similarly.
● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Wait, the `wait_for_state` function has a problem -- the REFINING state polling won't work correctly because the state transitions through REFINING quickly. The workflow might already be in AWAITING_CONFIRMATION by the time we poll. For the "with questions" test, we need to wait for the workflow to be waiting for a reply while in REFINING state.
  
  Actually, looking more carefully: when the workflow is in the REFINING state and needs questions, it doesn't transition out of REFINING -- it stays in REFINING and waits for user_reply. So polling for REFINING state should work. But the timing issue is that the workflow might process REFINING so fast it's already in AWAITING_CONFIRMATION.
  
  Let me reconsider the "with questions" test. The flow is:
  1. DRAFT -> REFINING
  2. First refine call returns needs_questions (not ready)
  3. Questions sent to Slack
  4. Wait for user reply <-- workflow is stuck here, still in REFINING state
  
  So I should wait for REFINING state. But the issue is that REFINING is set before the activity runs, so we might see REFINING before the wait_condition starts. Let me add a check for `questions_for_user` in the status.
  
  Actually, the simpler approach is just to add `await asyncio.sleep(2)` to let the workflow advance to the wait point. That's what Temporal test examples typically do. Let me simplify.
● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Now let me also check for a potential issue with the `wait_for_state` function. In the "revision" test, after rejection the workflow goes AWAITING_CONFIRMATION -> REFINING -> AWAITING_CONFIRMATION. The second `wait_for_state` call might see the state is already AWAITING_CONFIRMATION from before the rejection was processed. Let me update that test to wait for REFINING first, then AWAITING_CONFIRMATION.
● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Now let me run the tests again.
● Bash(Run IntentWorkflow tests with timeout)
  ✗ Exit code 4
    ERROR: usage: python -m pytest [options] [file_or_dir] [file_or_dir] [...]
    python -m pytest: error: unrecognized arguments: --timeout=120
      inifile: /Users/agutnikov/work/orca/pyproject.toml
      rootdir: /Users/agutnikov/work/orca

● Bash(Run IntentWorkflow tests)
  ✗ Exit code 1
    ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
  └ …

● The issue is clear: the mock activities have `input: object` as their parameter type, which Temporal can't deserialize. I need to use the proper dataclass types for the mock activity inputs. Let me look at how the issue tests handle this -- they also use `input: object` but they work because the issue workflow's activities use different types.
  
  Wait, the issue tests also use `input: object` and they work. The difference is that the activities being called in the intent workflow have dataclass inputs like `RefineIntentInput`, `SlackMessageInput`, etc. Looking at the error more carefully:
  
  ```
  TypeError: Unserializable type during conversion: <class 'object'>
  ```
  
  This happens when Temporal tries to deserialize the activity input. The mock `send_slack_message_v2` uses `input: object` but the real `send_slack_message_v2` takes `SlackMessageInput`. The mock needs to match the parameter type.
  
  Let me fix the mock activities to use proper types.
● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Now update all mock activity signatures.
● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_refine_intent_ready(input: object) -> RefineIntentOutput:' were successfully replaced with 'async def mock_refine_intent_ready(input: RefineIntentInput) -> RefineIntentOutput:'.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_refine_intent_needs_questions(input: object) -> RefineIntentOutput:' were successfully replaced with 'async def mock_refine_intent_needs_questions(input: RefineIntentInput) -> RefineIntentOutput:'.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_confirm_issue_success(input: object) -> ConfirmIssueOutput:' were successfully replaced with 'async def mock_confirm_issue_success(input: ConfirmIssueInput) -> ConfirmIssueOutput:'.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_decompose_intent_success(input: object) -> DecomposeIntentOutput:' were successfully replaced with 'async def mock_decompose_intent_success(input: DecomposeIntentInput) -> DecomposeIntentOutput:'.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_create_task_issue(input: object) -> CreateTaskIssueOutput:' were successfully replaced with 'async def mock_create_task_issue(input: CreateTaskIssueInput) -> CreateTaskIssueOutput:'.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_link_tasks(input: object) -> LinkTasksOutput:' were successfully replaced with 'async def mock_link_tasks(input: LinkTasksInput) -> LinkTasksOutput:'.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_send_slack_message(input: object) -> SlackMessageResult:' were successfully replaced with 'async def mock_send_slack_message(input: SlackMessageInput) -> SlackMessageResult:'.

● Now fix the inline mock activities in test methods too.
● Grep(async def mock_refine_then_ready\(input: object\))
  └ 364:        async def mock_refine_then_ready(input: object) -> RefineIntentOutput:

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_refine_then_ready(input: object) -> RefineIntentOutput:' were successfully replaced with 'async def mock_refine_then_ready(input: RefineIntentInput) -> RefineIntentOutput:'.

● Grep(async def mock_refine_always_ready\(input: object\))
  └ 448:        async def mock_refine_always_ready(input: object) -> RefineIntentOutput:

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_refine_always_ready(input: object) -> RefineIntentOutput:' were successfully replaced with 'async def mock_refine_always_ready(input: RefineIntentInput) -> RefineIntentOutput:'.

● Grep(async def mock_decompose_failure\(input: object\))
  └ 619:        async def mock_decompose_failure(input: object) -> DecomposeIntentOutput:

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated. All occurrences of 'async def mock_decompose_failure(input: object) -> DecomposeIntentOutput:' were successfully replaced with 'async def mock_decompose_failure(input: DecomposeIntentInput) -> DecomposeIntentOutput:'.

● Now run the tests again.
● Bash(Run single integration test)
  └ ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/agutnikov/work/orca
  └ …

● Now run all the tests.
● Bash(Run all IntentWorkflow tests)
  ✗ Exit code 1
    ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
  └ …

● The "with questions" test is timing out. The issue is that `wait_for_state(handle, REFINING)` returns immediately because the workflow transitions to REFINING first, but the workflow might not have reached the `wait_condition` yet. The signal arrives, gets consumed, but the workflow might still be executing the refine activity when the signal arrives.
  
  Actually, the real issue is: when we wait for REFINING state, the workflow is in REFINING but may not have executed the activity yet. Then when the activity runs and returns with questions, it sends questions to Slack and enters `wait_condition`. But by then, the signal was already sent and consumed (`self._user_reply` was set and the `wait_condition` picks it up immediately). But wait -- actually the `wait_condition` should see `_user_reply is not None` immediately and proceed. That should work.
  
  Let me think again... The problem might be different. When the signal arrives before `wait_condition`, `self._user_reply` is set. Then when `wait_condition` starts, it checks `self._user_reply is not None` which is true, so it returns immediately. Then the user_reply is consumed, conversation context is updated, and we loop back to refine again. The second refine returns `ready_for_confirmation=True`, so we transition to AWAITING_CONFIRMATION. Then confirm_issue runs, Slack message sent, and we enter another `wait_condition`.
  
  But the test code does `wait_for_state(REFINING)` which immediately returns, then sends the signal. Then does `wait_for_state(AWAITING_CONFIRMATION)`. The workflow should process the signal and reach AWAITING_CONFIRMATION. But it times out at 30s.
  
  The likely problem is that the signal arrives BEFORE the workflow even reaches the first `wait_condition`. So the signal gets set, but the workflow is still running the refine activity. By the time it reaches `wait_condition`, `_user_reply` is already set, which is fine. But then when the second refine returns ready, it transitions to AWAITING_CONFIRMATION. That should work...
  
  Let me add some debugging to understand. Actually, let me check if the issue is that the time-skipping environment requires time to advance. The `wait_condition` has a 72-hour timeout, and in the time-skipping environment, time might not automatically advance.
  
  The Temporal time-skipping environment automatically advances time when there are no pending tasks. But the `asyncio.sleep` in the `wait_for_state` polling function uses real time, not Temporal time. The issue is that the workflow is in a `wait_condition` with a 72-hour timeout, and the time-skipping environment needs the workflow to wake up. The signal should wake it up though.
  
  Let me try a different approach: just use `asyncio.sleep` with a small delay instead of polling, since in the time-skipping env signals are processed immediately.
● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Wait -- I think the issue might be that `wait_for_state` is using real `asyncio.sleep` but the test env uses time-skipping. The `wait_condition` in the workflow uses Temporal's time, so when the test polls, the workflow is blocked on `wait_condition` and time is not advancing. The signal should wake it up though.
  
  Actually, I think the fundamental issue is race condition. When `wait_for_state(REFINING)` succeeds, the workflow just transitioned to REFINING. It hasn't even called the activity yet. The signal is sent, `_user_reply` gets set. Then the activity runs, returns with questions, Slack message is sent, and then `wait_condition` starts -- but `_user_reply` is already set so it returns immediately. Then the second refine runs, it returns ready=True, transitions to AWAITING_CONFIRMATION, runs confirm_issue, sends Slack, enters second `wait_condition`. At this point the test should be polling for AWAITING_CONFIRMATION. This should work...
  
  Unless the issue is that `_user_reply` was consumed by the `_wait_for_user_reply` method which sets it to None first:
  
  ```python
  self._user_reply = None
  ```
  
  So the signal arrives, sets `_user_reply` to the signal. Then `_wait_for_user_reply` sets `_user_reply = None` before calling `wait_condition`. And since signal handlers are async but run in the workflow event loop, the order should be deterministic.
  
  Actually wait, there's a timing issue here. The `_wait_for_user_reply` method does:
  1. `self._user_reply = None`  -- clears any previous reply
  2. `wait_condition(lambda: self._user_reply is not None or self._cancelled, ...)`
  
  If the signal arrives BETWEEN step 1 and step 2, the condition lambda will see it. But if the signal arrives BEFORE step 1, the reply gets cleared! And this is exactly what happens: the signal arrives before the workflow reaches `_wait_for_user_reply`, `_user_reply` gets set, but then step 1 clears it.
  
  That's the bug. The signal arrives early, sets `_user_reply`, but then `_wait_for_user_reply` resets it to None. I need to not clear the reply if one is already pending. Let me fix the workflow.
● Edit(intent.py)
  └ The file /Users/agutnikov/work/orca/src/orca/workflows/intent.py has been updated successfully.

● Wait, I need to fix the indentation. Let me rewrite this method properly.
● Read(intent.py)
  └    405→        raw_intent = (
       406→            f"Intent #{input.task_id.github_issue_number} "
       407→            f"from {input.task_id.repository}"
       408→        )
  └ …

● Read(intent.py)
  └    560→                    github_issue_number=result.issue_number,
       561→                    repository=input.task_id.repository,
       562→                )
       563→                created_issues.append(task_id)
  └ …

● Read(intent.py)
  └    660→            "or describe what changes you'd like._"
       661→        )
       662→
       663→        try:
  └ …

● The indentation is broken. Let me rewrite the method properly.
● Edit(intent.py)
  └ The file /Users/agutnikov/work/orca/src/orca/workflows/intent.py has been updated successfully.

● Now run the tests again.
● Bash(Run all IntentWorkflow tests)
  └ Command running in background with ID: be6111b. Output is being written to: /private/tmp/claude/-Users-agutnikov-work-orca/tasks/be6111b.output

● Bash(Wait and check test results)
  └ ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/agutnikov/work/orca
  └ …

● 14 of 15 passed. Let me wait for the last one.
● Bash(Check final test result)
  └ ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/agutnikov/work/orca
  └ …

● The last test (decomposition failure) is still running. The problem is that the mock activity raises an exception, and with default retry policy Temporal retries indefinitely. I need to set a retry policy with max_attempts on the decompose activity call in the workflow, or handle the exception differently.
  
  Actually, looking at the workflow code, the `_decompose` method catches exceptions and returns None. The issue is that `workflow.execute_activity` with default retry policy retries the activity before raising the exception to the caller. The mock raises `RuntimeError` which gets retried.
  
  Let me check how the issue workflow test handles this -- it doesn't test activity failures that raise exceptions. Let me update the decomposition failure test to use a mock that returns successfully but with empty results, or better yet, let me set a retry policy on the decompose activity call.
  
  The simplest fix is to add a retry policy with limited attempts to the `_decompose` method in the workflow.
● Bash(Kill hanging test)
  └ killed

● I need to add retry policies to the activity calls so they don't retry forever in tests. Let me update the workflow to use `RetryPolicy` with limited attempts.
● Read(intent.py)
  └      1→"""Intent Workflow for refining, confirming, and decomposing user intents.
         2→
         3→This workflow manages the lifecycle of an intent from initial draft through
         4→refinement, user confirmation, and decomposition into individual issues.
  └ …

● Edit(intent.py)
  └ The file /Users/agutnikov/work/orca/src/orca/workflows/intent.py has been updated successfully.

● Now add retry policy to the `_decompose` method's activity call.
● Edit(intent.py)
  └ The file /Users/agutnikov/work/orca/src/orca/workflows/intent.py has been updated successfully.

● Also add retry policies to other activity calls for consistency.
● Edit(intent.py)
  └ The file /Users/agutnikov/work/orca/src/orca/workflows/intent.py has been updated successfully.

● Edit(intent.py)
  └ The file /Users/agutnikov/work/orca/src/orca/workflows/intent.py has been updated successfully.

● Now run the tests again.
● Bash(Run all IntentWorkflow tests)
  └ ============================= test session starts ==============================
    platform darwin -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0 -- /Users/agutnikov/work/orca/.venv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/agutnikov/work/orca
  └ …

● All 15 tests pass. Now let me run the existing tests to make sure nothing is broken, and also run lint.
● Bash(Run all other tests)
  └ Command running in background with ID: b477a13. Output is being written to: /private/tmp/claude/-Users-agutnikov-work-orca/tasks/b477a13.output

● Bash(Run ruff lint on changed files)
  ✗ Exit code 1
    E501 Line too long (105 > 100)
      --> src/orca/worker/main.py:42:101
       |
  └ …

● Edit(main.py)
  └ The file /Users/agutnikov/work/orca/src/orca/worker/main.py has been updated successfully.

● Edit(test_intent.py)
  └ The file /Users/agutnikov/work/orca/tests/test_workflows/test_intent.py has been updated successfully.

● Bash(Fix import sorting)
  └ Found 1 error (1 fixed, 0 remaining).

● Bash(Verify lint passes)
  └ All checks passed!

● Now let me also run mypy/type checking if available.
● Bash(Run mypy on intent workflow)
  └ Success: no issues found in 1 source file

● Let me check the other tests too.
● Bash(Check other tests output)
  └ 

● Bash(Run all other tests quickly)
  └ Command running in background with ID: ba9f154. Output is being written to: /private/tmp/claude/-Users-agutnikov-work-orca/tasks/ba9f154.output

● Bash(Wait and check other tests)
  └ 

● Bash(Read other tests output)
  └ 

● Bash(Check output file)
  └ -rw-r--r--@ 1 agutnikov  wheel  0 Jan 28 19:32 /private/tmp/claude/-Users-agutnikov-work-orca/tasks/ba9f154.output

● The output file is empty. Let me try running in foreground.
● Bash(Run existing workflow tests)
  ✗ Exit code 137
    [Request interrupted by user for tool use]
    ....

❯ [Request interrupted by user for tool use]