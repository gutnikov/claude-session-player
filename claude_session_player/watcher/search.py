"""Search engine for querying indexed sessions.

This module provides:
- SearchEngine: Parses queries, filters sessions, and ranks results
- Query parsing: Handles terms, quoted phrases, and option flags
- Ranking algorithm: Scores results by summary/project matches and recency
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .indexer import SessionIndexer, SessionIndex, SessionInfo


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SearchFilters:
    """Filters to apply when searching sessions."""

    project: str | None = None
    since: datetime | None = None
    until: datetime | None = None


@dataclass
class SearchParams:
    """Parsed search parameters."""

    query: str
    terms: list[str]
    filters: SearchFilters = field(default_factory=SearchFilters)
    sort: str = "recent"
    limit: int = 5
    offset: int = 0


@dataclass
class SearchResults:
    """Search results with pagination info."""

    query: str
    filters: SearchFilters
    sort: str
    total: int
    offset: int
    limit: int
    results: list[SessionInfo]


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------


def parse_time_range(value: str) -> timedelta | None:
    """Parse a time range string like '7d', '2w', '1m'.

    Args:
        value: Time range string (e.g., '7d', '2w', '1m').

    Returns:
        timedelta if valid, None otherwise.
    """
    if not value:
        return None

    match = re.match(r"^(\d+)([dwm])$", value.lower())
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == "d":
        return timedelta(days=amount)
    elif unit == "w":
        return timedelta(weeks=amount)
    elif unit == "m":
        # Approximate month as 30 days
        return timedelta(days=amount * 30)

    return None


def parse_iso_date(value: str) -> datetime | None:
    """Parse an ISO date string.

    Args:
        value: ISO date string (e.g., '2024-01-01').

    Returns:
        datetime if valid, None otherwise.
    """
    if not value:
        return None

    try:
        # Try parsing as date first
        dt = datetime.fromisoformat(value)
        # If no timezone, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Query parsing
# ---------------------------------------------------------------------------


def parse_query(text: str) -> SearchParams:
    """Parse a search query string into SearchParams.

    Supports:
    - Simple terms: 'auth bug' → terms=['auth', 'bug']
    - Quoted phrases: '"auth bug"' → terms=['auth bug']
    - Options: --project/-p, --last/-l, --since/-s, --until/-u, --sort

    Args:
        text: The raw query string (e.g., 'auth bug -p trello -l 7d').

    Returns:
        Parsed SearchParams.
    """
    if not text or not text.strip():
        return SearchParams(query="", terms=[], filters=SearchFilters())

    # Use shlex to handle quoted strings properly
    try:
        tokens = shlex.split(text)
    except ValueError:
        # If shlex fails (unbalanced quotes), fall back to simple split
        tokens = text.split()

    terms: list[str] = []
    filters = SearchFilters()
    sort = "recent"

    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Check for options
        if token in ("--project", "-p"):
            if i + 1 < len(tokens):
                filters.project = tokens[i + 1]
                i += 2
                continue
        elif token in ("--last", "-l"):
            if i + 1 < len(tokens):
                delta = parse_time_range(tokens[i + 1])
                if delta:
                    filters.since = datetime.now(timezone.utc) - delta
                i += 2
                continue
        elif token in ("--since", "-s"):
            if i + 1 < len(tokens):
                dt = parse_iso_date(tokens[i + 1])
                if dt:
                    filters.since = dt
                i += 2
                continue
        elif token in ("--until", "-u"):
            if i + 1 < len(tokens):
                dt = parse_iso_date(tokens[i + 1])
                if dt:
                    filters.until = dt
                i += 2
                continue
        elif token == "--sort":
            if i + 1 < len(tokens):
                if tokens[i + 1] in ("recent", "oldest", "size", "duration"):
                    sort = tokens[i + 1]
                i += 2
                continue
        elif token.startswith("-"):
            # Unknown option, skip
            i += 1
            continue

        # Regular term (already unquoted by shlex)
        terms.append(token)
        i += 1

    # Build the original query string (for display/scoring)
    query = " ".join(terms)

    return SearchParams(
        query=query,
        terms=terms,
        filters=filters,
        sort=sort,
    )


# ---------------------------------------------------------------------------
# Ranking algorithm
# ---------------------------------------------------------------------------


def calculate_score(
    session: SessionInfo,
    query: str,
    terms: list[str],
    now: datetime | None = None,
) -> float:
    """Calculate relevance score for a session.

    Scoring weights:
    - Summary term match: 2.0 per term
    - Summary exact phrase match: +1.0 bonus
    - Project name term match: 1.0 per term
    - Recency boost: 0.0-1.0 (decays over 30 days)

    Args:
        session: The session to score.
        query: The original query string (for phrase matching).
        terms: List of search terms.
        now: Current time (for recency calculation). Defaults to UTC now.

    Returns:
        Relevance score (higher is better).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    score = 0.0

    # Summary matches (weight: 2.0 per term)
    if session.summary:
        summary_lower = session.summary.lower()
        for term in terms:
            if term.lower() in summary_lower:
                score += 2.0

        # Boost for exact phrase match
        if query and query.lower() in summary_lower:
            score += 1.0

    # Project name matches (weight: 1.0 per term)
    project_lower = session.project_display_name.lower()
    for term in terms:
        if term.lower() in project_lower:
            score += 1.0

    # Recency boost (max 1.0 for today, decays over 30 days)
    days_old = (now - session.modified_at).days
    recency_boost = max(0.0, 1.0 - (days_old / 30))
    score += recency_boost

    return score


# ---------------------------------------------------------------------------
# SearchEngine
# ---------------------------------------------------------------------------


class SearchEngine:
    """Search engine for querying indexed sessions.

    Parses search queries, applies filters, ranks results by relevance,
    and returns paginated results.
    """

    def __init__(self, indexer: SessionIndexer) -> None:
        """Initialize the search engine.

        Args:
            indexer: The session indexer to search against.
        """
        self.indexer = indexer

    def parse_query(self, text: str) -> SearchParams:
        """Parse a search query string.

        Args:
            text: The raw query string.

        Returns:
            Parsed SearchParams.
        """
        return parse_query(text)

    async def search(self, params: SearchParams) -> SearchResults:
        """Search sessions matching the given parameters.

        Args:
            params: Search parameters (query, filters, sort, pagination).

        Returns:
            SearchResults with matching sessions.
        """
        # Get the current index
        index = await self.indexer.get_index()

        # Filter sessions
        candidates = self._filter_sessions(index, params)

        # Calculate scores for ranking (only if there are search terms)
        now = datetime.now(timezone.utc)
        scored: list[tuple[SessionInfo, float]] = []
        for session in candidates:
            score = calculate_score(session, params.query, params.terms, now)
            scored.append((session, score))

        # Sort results
        sorted_results = self._sort_results(scored, params.sort)

        # Extract just the sessions
        total = len(sorted_results)

        # Apply pagination
        start = params.offset
        end = params.offset + params.limit
        page = sorted_results[start:end]

        return SearchResults(
            query=params.query,
            filters=params.filters,
            sort=params.sort,
            total=total,
            offset=params.offset,
            limit=params.limit,
            results=page,
        )

    def _filter_sessions(
        self,
        index: SessionIndex,
        params: SearchParams,
    ) -> list[SessionInfo]:
        """Filter sessions based on search parameters.

        Args:
            index: The session index.
            params: Search parameters with filters.

        Returns:
            List of sessions that match filters.
        """
        candidates: list[SessionInfo] = []

        for session in index.sessions.values():
            # Apply project filter (case-insensitive substring match)
            if params.filters.project:
                project_filter = params.filters.project.lower()
                if project_filter not in session.project_display_name.lower():
                    continue

            # Apply since filter
            if params.filters.since:
                if session.modified_at < params.filters.since:
                    continue

            # Apply until filter
            if params.filters.until:
                if session.modified_at > params.filters.until:
                    continue

            # Apply term filter (only if there are terms with 2+ chars)
            if params.terms:
                # Check minimum query length (2 characters)
                valid_terms = [t for t in params.terms if len(t) >= 2]
                if valid_terms:
                    # At least one term must match (OR logic)
                    if not self._matches_any_term(session, valid_terms):
                        continue

            candidates.append(session)

        return candidates

    def _matches_any_term(self, session: SessionInfo, terms: list[str]) -> bool:
        """Check if session matches any of the search terms.

        Args:
            session: The session to check.
            terms: List of search terms (minimum 2 chars each).

        Returns:
            True if any term matches summary, project name, or session ID.
        """
        # Check summary
        if session.summary:
            summary_lower = session.summary.lower()
            for term in terms:
                if term.lower() in summary_lower:
                    return True

        # Check project name
        project_lower = session.project_display_name.lower()
        for term in terms:
            if term.lower() in project_lower:
                return True

        # Check session ID (exact match only)
        session_id_lower = session.session_id.lower()
        for term in terms:
            if term.lower() == session_id_lower:
                return True

        return False

    def _sort_results(
        self,
        scored: list[tuple[SessionInfo, float]],
        sort: str,
    ) -> list[SessionInfo]:
        """Sort results by the specified criteria.

        Args:
            scored: List of (session, score) tuples.
            sort: Sort mode ('recent', 'oldest', 'size', 'duration').

        Returns:
            Sorted list of sessions.
        """
        if sort == "recent":
            # Sort by score first (descending), then by modified_at (descending)
            scored.sort(key=lambda x: (x[1], x[0].modified_at), reverse=True)
        elif sort == "oldest":
            # Sort by modified_at (ascending)
            scored.sort(key=lambda x: x[0].modified_at)
        elif sort == "size":
            # Sort by size_bytes (descending)
            scored.sort(key=lambda x: x[0].size_bytes, reverse=True)
        elif sort == "duration":
            # Sort by duration_ms (descending), sessions without duration go last
            scored.sort(
                key=lambda x: (x[0].duration_ms is not None, x[0].duration_ms or 0),
                reverse=True,
            )
        else:
            # Default to recent
            scored.sort(key=lambda x: (x[1], x[0].modified_at), reverse=True)

        return [session for session, _ in scored]
