"""Tests for the auto-apply pipeline helpers and sheets reader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sheets.sheets_reader import _detect_source


# ── _detect_source ───────────────────────────────────────────────


class TestDetectSource:
    """Verify ATS source detection from URLs."""

    def test_greenhouse_boards_url(self):
        url = "https://boards.greenhouse.io/airbnb/jobs/12345"
        assert _detect_source(url) == "greenhouse"

    def test_greenhouse_url(self):
        url = "https://job-boards.greenhouse.io/stripe/jobs/67890"
        assert _detect_source(url) == "greenhouse"

    def test_lever_url(self):
        url = "https://jobs.lever.co/openai/abc-def-123"
        assert _detect_source(url) == "lever"

    def test_lever_alternative_url(self):
        url = "https://lever.co/company/posting-id"
        assert _detect_source(url) == "lever"

    def test_unknown_url(self):
        url = "https://careers.google.com/jobs/results/12345"
        assert _detect_source(url) == "unknown"

    def test_empty_url(self):
        assert _detect_source("") == "unknown"

    def test_case_insensitive(self):
        url = "https://BOARDS.GREENHOUSE.IO/company/jobs/123"
        assert _detect_source(url) == "greenhouse"


# ── _validate_profile ───────────────────────────────────────────


class TestValidateProfile:
    """Verify applicant profile validation."""

    @patch("config.APPLICANT_FIRST_NAME", "Jane")
    @patch("config.APPLICANT_LAST_NAME", "Doe")
    @patch("config.APPLICANT_EMAIL", "jane@example.com")
    def test_valid_profile(self):
        from auto_apply import _validate_profile
        assert _validate_profile() is True

    @patch("config.APPLICANT_FIRST_NAME", "")
    @patch("config.APPLICANT_LAST_NAME", "Doe")
    @patch("config.APPLICANT_EMAIL", "jane@example.com")
    def test_missing_first_name(self):
        from auto_apply import _validate_profile
        assert _validate_profile() is False

    @patch("config.APPLICANT_FIRST_NAME", "Jane")
    @patch("config.APPLICANT_LAST_NAME", "Doe")
    @patch("config.APPLICANT_EMAIL", "")
    def test_missing_email(self):
        from auto_apply import _validate_profile
        assert _validate_profile() is False

    @patch("config.APPLICANT_FIRST_NAME", "  ")
    @patch("config.APPLICANT_LAST_NAME", "  ")
    @patch("config.APPLICANT_EMAIL", "  ")
    def test_whitespace_only(self):
        from auto_apply import _validate_profile
        assert _validate_profile() is False


# ── print_summary ────────────────────────────────────────────────


class TestPrintSummary:
    """Verify summary output doesn't crash."""

    def test_prints_without_error(self, capsys):
        from auto_apply import print_summary
        print_summary(total=5, applied=3, failed=1, skipped=1, elapsed=12.5)
        captured = capsys.readouterr()
        assert "AUTO-APPLY PIPELINE" in captured.out
        assert "5" in captured.out
        assert "3" in captured.out
