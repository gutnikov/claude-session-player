#!/usr/bin/env bash
set -euo pipefail

# Claude Session Player — Automated Issue Implementation
# Finds the next unimplemented GH issue and runs Claude Code to implement it.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Claude Session Player: Implement Next Issue ==="
echo ""

# Find the next open issue (lowest number first, enforced sort by number)
NEXT_ISSUE=$(gh issue list --state open --label enhancement --json number,title --jq 'sort_by(.number) | .[0]')

if [ -z "$NEXT_ISSUE" ] || [ "$NEXT_ISSUE" = "null" ]; then
    echo "No open issues found. All done!"
    exit 0
fi

ISSUE_NUMBER=$(echo "$NEXT_ISSUE" | jq -r '.number')
ISSUE_TITLE=$(echo "$NEXT_ISSUE" | jq -r '.title')

echo "Next issue: #${ISSUE_NUMBER} — ${ISSUE_TITLE}"
echo ""

# Get the full issue body
ISSUE_BODY=$(gh issue view "$ISSUE_NUMBER" --json body --jq '.body')

PROMPT=$(cat <<PROMPT_EOF
You are implementing issue #${ISSUE_NUMBER}: "${ISSUE_TITLE}" for the Claude Session Player project.

## Instructions

1. FIRST: Read the spec at .claude/specs/claude-session-player.md
2. THEN: Read ALL existing worklogs in issues/worklogs/ (read every file that exists)
3. THEN: Read the full issue description below and understand all requirements

## Issue Description

${ISSUE_BODY}

## Implementation Steps

Follow this exact workflow:

### Step 1: Understand Context
- Read the spec file
- Read all worklogs from prior issues
- Read any existing code that this issue builds on
- Understand the codebase state

### Step 2: Implement
- Write the code as described in the issue
- Follow the project structure from the spec
- Use Python 3.12+ features, type hints, dataclasses
- Keep it simple — no over-engineering
- Make sure imports are correct and modules exist

### Step 3: Write Tests
- Write all tests described in the issue "Test Requirements" section
- Add fixtures as needed in tests/conftest.py
- Aim for the test count specified in the DoD

### Step 4: Validate
- Run: pytest -xvs
- Fix any failures
- Run: pytest --tb=short to verify all tests pass
- If there are prior tests, make sure they still pass too

### Step 5: Write Worklog
- Create issues/worklogs/${ISSUE_NUMBER}-worklog.md
- Include: files created/modified, decisions made, test count, any deviations from spec

### Step 6: Commit and Create PR
- Create a new branch: issue-${ISSUE_NUMBER}
- Commit all changes with a descriptive message
- Push and create a PR that closes #${ISSUE_NUMBER}
- PR title: "Issue #${ISSUE_NUMBER}: ${ISSUE_TITLE}"

### Step 7: Code Review
- Review your own PR using: gh pr diff
- Check for:
  - Missing test cases
  - Type hint issues
  - Import errors
  - Unused code
  - Logic bugs
- Fix any findings, commit, and push

### Step 8: Merge
- After review passes, merge the PR: gh pr merge --squash --delete-branch
- Verify the issue is closed

## Important Notes
- The project has NO external runtime dependencies (stdlib only)
- Dev dependencies: pytest, pytest-cov
- Always run tests before creating the PR
- Always write the worklog before committing
- If you encounter issues with prior implementations, document them in the worklog and fix if possible
PROMPT_EOF
)

echo "Starting Claude Code for issue #${ISSUE_NUMBER}..."
echo ""

claude -p "$PROMPT" --dangerously-skip-permissions
