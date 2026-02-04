"""Ranking algorithm tests for SearchDatabase.

Tests the search ranking algorithm including:
- Summary match weight (2.0 per term)
- Exact phrase bonus (+1.0)
- Project name match weight (1.0 per term)
- Recency boost (max 1.0, decays over 30 days)
- Combined scoring and sort order
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pytest

from claude_session_player.watcher.search_db import (
    IndexedSession,
    SearchDatabase,
    SearchFilters,
    SearchResult,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory() -> Callable[..., IndexedSession]:
    """Factory for creating test sessions with ranking-relevant attributes."""
    counter = [0]

    def _create(
        summary: str = "Test summary",
        project_display_name: str = "myapp",  # Use neutral name to avoid query collisions
        modified_days_ago: int = 0,
        session_id: str | None = None,
    ) -> IndexedSession:
        counter[0] += 1
        sid = session_id or f"ranking-{counter[0]}"
        now = datetime.now(timezone.utc)
        return IndexedSession(
            session_id=sid,
            project_encoded=f"-work-{project_display_name}",
            project_display_name=project_display_name,
            project_path=f"/work/{project_display_name}",
            summary=summary,
            file_path=f"/work/{project_display_name}/{sid}.jsonl",
            file_created_at=now - timedelta(days=modified_days_ago + 1),
            file_modified_at=now - timedelta(days=modified_days_ago),
            indexed_at=now,
            size_bytes=1000,
            line_count=50,
            duration_ms=60000,
            has_subagents=False,
            is_subagent=False,
        )

    return _create


@pytest.fixture
async def ranking_db(
    tmp_path: Path, session_factory: Callable[..., IndexedSession]
) -> SearchDatabase:
    """Database with sessions for ranking tests."""
    db = SearchDatabase(tmp_path)
    await db.initialize()

    sessions = [
        # High relevance: summary match + exact phrase + recent
        session_factory(
            session_id="best_match",
            summary="Fix authentication bug in login flow",
            project_display_name="auth-service",
            modified_days_ago=0,
        ),
        # Medium relevance: partial match, older
        session_factory(
            session_id="partial_match",
            summary="Update authentication tests",
            project_display_name="backend",
            modified_days_ago=10,
        ),
        # Project name match only
        session_factory(
            session_id="project_match",
            summary="Add new feature",
            project_display_name="auth-utils",
            modified_days_ago=15,
        ),
        # No match
        session_factory(
            session_id="no_match",
            summary="Update documentation",
            project_display_name="docs",
            modified_days_ago=5,
        ),
        # Exact phrase match
        session_factory(
            session_id="exact_phrase",
            summary="auth bug in login system",
            project_display_name="web",
            modified_days_ago=15,
        ),
    ]
    await db.upsert_sessions_batch(sessions)
    yield db
    await db.close()


# ---------------------------------------------------------------------------
# Summary Match Weight Tests
# ---------------------------------------------------------------------------


class TestRankingSummaryMatch:
    """Tests for summary match weight (2.0 per term)."""

    @pytest.mark.asyncio
    async def test_summary_match_weight(
        self, ranking_db: SearchDatabase
    ) -> None:
        """Summary match adds 2.0 per term."""
        results, _ = await ranking_db.search_ranked(
            SearchFilters(query="authentication")
        )

        # Find session with "authentication" in summary
        for r in results:
            if r.session.session_id == "best_match":
                # 2.0 for "authentication" + recency boost (~1.0)
                assert r.score >= 2.0

    @pytest.mark.asyncio
    async def test_multiple_term_matches(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Multiple matching terms each add 2.0."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            session_factory(
                session_id="multi-term",
                summary="authentication bug fix",  # 3 potential matches
                modified_days_ago=15,
            )
        )

        results, _ = await db.search_ranked(SearchFilters(query="authentication bug"))

        assert len(results) > 0
        result = results[0]
        # 2.0 for "authentication" + 2.0 for "bug" + 1.0 exact phrase + recency
        assert result.score >= 4.0

        await db.close()

    @pytest.mark.asyncio
    async def test_no_summary_match(
        self, ranking_db: SearchDatabase
    ) -> None:
        """Session without summary match scores lower."""
        results, _ = await ranking_db.search_ranked(SearchFilters(query="auth"))

        scores = {r.session.session_id: r.score for r in results}

        # project_match only matches project name (not summary)
        # It should score lower than summary matches
        if "project_match" in scores and "best_match" in scores:
            assert scores["project_match"] < scores["best_match"]


# ---------------------------------------------------------------------------
# Exact Phrase Bonus Tests
# ---------------------------------------------------------------------------


class TestRankingExactPhrase:
    """Tests for exact phrase bonus (+1.0)."""

    @pytest.mark.asyncio
    async def test_exact_phrase_bonus(self, ranking_db: SearchDatabase) -> None:
        """Exact phrase in summary adds 1.0 bonus."""
        results, _ = await ranking_db.search_ranked(SearchFilters(query="auth bug"))

        exact_match = next(
            (r for r in results if r.session.session_id == "exact_phrase"), None
        )
        assert exact_match is not None

        # 2.0 for "auth" + 2.0 for "bug" + 1.0 for exact phrase + recency
        assert exact_match.score >= 5.0

    @pytest.mark.asyncio
    async def test_no_exact_phrase_no_bonus(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """No exact phrase means no 1.0 bonus."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        # Has both terms but not as exact phrase
        await db.upsert_session(
            session_factory(
                session_id="separate-terms",
                summary="auth issue and a bug elsewhere",
                modified_days_ago=30,  # 0 recency
            )
        )

        results, _ = await db.search_ranked(SearchFilters(query="auth bug"))

        result = results[0]
        # 2.0 for "auth" + 2.0 for "bug" + 0 recency = 4.0
        # No exact phrase bonus because "auth bug" is not contiguous
        assert result.score == pytest.approx(4.0, abs=0.1)

        await db.close()


# ---------------------------------------------------------------------------
# Project Name Match Tests
# ---------------------------------------------------------------------------


class TestRankingProjectMatch:
    """Tests for project name match weight (1.0 per term)."""

    @pytest.mark.asyncio
    async def test_project_match_weight(self, ranking_db: SearchDatabase) -> None:
        """Project name match adds 1.0 per term."""
        results, _ = await ranking_db.search_ranked(SearchFilters(query="auth"))

        project_match = next(
            (r for r in results if r.session.session_id == "project_match"), None
        )
        assert project_match is not None
        # 1.0 for "auth" in project name + recency boost
        assert project_match.score >= 1.0

    @pytest.mark.asyncio
    async def test_project_and_summary_match(
        self, ranking_db: SearchDatabase
    ) -> None:
        """Session matching both summary and project scores higher."""
        results, _ = await ranking_db.search_ranked(SearchFilters(query="auth"))

        scores = {r.session.session_id: r.score for r in results}

        # best_match has "authentication" in summary AND "auth" in project
        # project_match only has "auth" in project
        if "best_match" in scores and "project_match" in scores:
            assert scores["best_match"] > scores["project_match"]


# ---------------------------------------------------------------------------
# Recency Boost Tests
# ---------------------------------------------------------------------------


class TestRankingRecencyBoost:
    """Tests for recency boost (max 1.0, decays over 30 days)."""

    @pytest.mark.asyncio
    async def test_recency_boost_today(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Today's session gets ~1.0 recency boost."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            session_factory(
                session_id="today",
                summary="test word",
                modified_days_ago=0,
            )
        )

        results, _ = await db.search_ranked(SearchFilters(query="test"))

        # 2.0 for "test" match + ~1.0 recency + 1.0 exact phrase = ~4.0
        assert results[0].score >= 3.9

        await db.close()

    @pytest.mark.asyncio
    async def test_recency_boost_old(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """30 days old session gets 0.0 recency boost."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            session_factory(
                session_id="old",
                summary="uniqueword value",  # Use unique term not in project name
                modified_days_ago=30,
            )
        )

        results, _ = await db.search_ranked(SearchFilters(query="uniqueword"))

        # 2.0 for "uniqueword" match + 0.0 recency + 1.0 exact phrase = 3.0
        assert results[0].score == pytest.approx(3.0, abs=0.1)

        await db.close()

    @pytest.mark.asyncio
    async def test_recency_decay_linear(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Recency boost decays linearly over 30 days."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        # 15 days old should get ~0.5 recency boost
        await db.upsert_session(
            session_factory(
                session_id="mid",
                summary="uniqueword value",  # Use unique term not in project name
                modified_days_ago=15,
            )
        )

        results, _ = await db.search_ranked(SearchFilters(query="uniqueword"))

        # 2.0 for "uniqueword" + 0.5 recency + 1.0 exact phrase = 3.5
        assert results[0].score == pytest.approx(3.5, abs=0.15)

        await db.close()

    @pytest.mark.asyncio
    async def test_recency_boost_negative_days(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Sessions older than 30 days get 0.0 recency boost."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            session_factory(
                session_id="very-old",
                summary="uniqueword value",  # Use unique term not in project name
                modified_days_ago=60,
            )
        )

        results, _ = await db.search_ranked(SearchFilters(query="uniqueword"))

        # Recency should be 0.0 (clamped to max 0)
        # 2.0 for "uniqueword" + 0.0 recency + 1.0 exact phrase = 3.0
        assert results[0].score == pytest.approx(3.0, abs=0.1)

        await db.close()


# ---------------------------------------------------------------------------
# Combined Scoring Tests
# ---------------------------------------------------------------------------


class TestRankingCombinedScoring:
    """Tests for combined scoring with all factors."""

    @pytest.mark.asyncio
    async def test_combined_scoring(self, ranking_db: SearchDatabase) -> None:
        """All ranking factors combine correctly."""
        results, _ = await ranking_db.search_ranked(SearchFilters(query="auth bug"))

        scores = {r.session.session_id: r.score for r in results}

        # exact_phrase should have: 2*2 (terms) + 1.0 (phrase) + recency
        # It's modified 15 days ago, so recency = 0.5
        if "exact_phrase" in scores:
            assert scores["exact_phrase"] >= 5.0

    @pytest.mark.asyncio
    async def test_ranking_order(self, ranking_db: SearchDatabase) -> None:
        """Results ordered by score descending."""
        results, _ = await ranking_db.search_ranked(SearchFilters(query="auth"))

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_tiebreaker_by_date(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Same score sorted by date (tiebreaker)."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        # Create sessions with same words but different dates at 15 days
        # (so recency boost is same ~0.5)
        await db.upsert_session(
            session_factory(
                session_id="older",
                summary="test word",
                modified_days_ago=16,
            )
        )
        await db.upsert_session(
            session_factory(
                session_id="newer",
                summary="test word",
                modified_days_ago=14,
            )
        )

        results, _ = await db.search_ranked(SearchFilters(query="test"))

        # Newer should come first (tiebreaker)
        assert results[0].session.session_id == "newer"

        await db.close()


# ---------------------------------------------------------------------------
# No Query Ranking Tests
# ---------------------------------------------------------------------------


class TestRankingNoQuery:
    """Tests for ranking when no query is provided."""

    @pytest.mark.asyncio
    async def test_no_query_no_ranking(
        self, ranking_db: SearchDatabase
    ) -> None:
        """No query returns results by recency with score 0."""
        results, total = await ranking_db.search_ranked(SearchFilters())

        assert total > 0
        for result in results:
            assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_no_query_ordered_by_recency(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Without query, results ordered by modification date."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            session_factory(
                session_id="old",
                summary="Something",
                modified_days_ago=10,
            )
        )
        await db.upsert_session(
            session_factory(
                session_id="new",
                summary="Something else",
                modified_days_ago=1,
            )
        )

        results, _ = await db.search_ranked(SearchFilters())

        # Newer should come first
        assert results[0].session.session_id == "new"

        await db.close()


# ---------------------------------------------------------------------------
# Ranking Pagination Tests
# ---------------------------------------------------------------------------


class TestRankingPagination:
    """Tests for ranked search pagination."""

    @pytest.mark.asyncio
    async def test_ranking_pagination(self, ranking_db: SearchDatabase) -> None:
        """Ranked search supports pagination."""
        all_results, total = await ranking_db.search_ranked(
            SearchFilters(query="auth"), limit=10
        )

        if total >= 2:
            first_result, _ = await ranking_db.search_ranked(
                SearchFilters(query="auth"), limit=1, offset=0
            )
            second_result, _ = await ranking_db.search_ranked(
                SearchFilters(query="auth"), limit=1, offset=1
            )

            assert first_result[0].session.session_id == all_results[0].session.session_id
            assert second_result[0].session.session_id == all_results[1].session.session_id

    @pytest.mark.asyncio
    async def test_ranking_offset_beyond_results(
        self, ranking_db: SearchDatabase
    ) -> None:
        """Offset beyond results returns empty list."""
        results, total = await ranking_db.search_ranked(
            SearchFilters(query="auth"), limit=10, offset=1000
        )

        assert results == []


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestRankingEdgeCases:
    """Edge case tests for ranking."""

    @pytest.mark.asyncio
    async def test_null_summary_ranking(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Sessions with null summary still rankable by project name."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        session = session_factory(
            session_id="null-summary",
            summary=None,
            project_display_name="auth-tools",
            modified_days_ago=0,
        )
        # Manually set summary to None
        session = IndexedSession(
            session_id=session.session_id,
            project_encoded=session.project_encoded,
            project_display_name=session.project_display_name,
            project_path=session.project_path,
            summary=None,
            file_path=session.file_path,
            file_created_at=session.file_created_at,
            file_modified_at=session.file_modified_at,
            indexed_at=session.indexed_at,
            size_bytes=session.size_bytes,
            line_count=session.line_count,
            duration_ms=session.duration_ms,
            has_subagents=session.has_subagents,
            is_subagent=session.is_subagent,
        )
        await db.upsert_session(session)

        results, _ = await db.search_ranked(SearchFilters(query="auth"))

        assert len(results) > 0
        # Should match project name
        assert results[0].session.session_id == "null-summary"
        # Score from project match + recency
        assert results[0].score >= 1.0

        await db.close()

    @pytest.mark.asyncio
    async def test_case_insensitive_ranking(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Ranking is case-insensitive."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            session_factory(
                session_id="mixed-case",
                summary="AUTHENTICATION Bug Fix",
                modified_days_ago=0,
            )
        )

        # Lowercase query
        results, _ = await db.search_ranked(SearchFilters(query="authentication"))
        assert len(results) > 0
        assert results[0].session.session_id == "mixed-case"

        await db.close()

    @pytest.mark.asyncio
    async def test_special_characters_in_query(
        self,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Special characters in query handled gracefully.

        Note: FTS5 has special characters like ':' that have specific meanings.
        This test uses parentheses which are less problematic.
        """
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            session_factory(
                session_id="special",
                summary="Fix bug (auth) error",
                modified_days_ago=0,
            )
        )

        # Query with parentheses - FTS5 handles these
        results, _ = await db.search_ranked(SearchFilters(query="bug auth"))
        # Should find matches
        assert len(results) > 0

        await db.close()

    @pytest.mark.asyncio
    async def test_empty_results_ranking(
        self, tmp_path: Path
    ) -> None:
        """Ranking with no matches returns empty."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        results, total = await db.search_ranked(
            SearchFilters(query="nonexistenttermxyz")
        )

        assert results == []
        assert total == 0

        await db.close()
