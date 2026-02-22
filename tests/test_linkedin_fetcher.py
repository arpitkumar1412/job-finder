"""Tests for the LinkedIn fetcher helper functions."""

from __future__ import annotations

from fetchers.linkedin import _make_job_id, _strip_html


# ── _make_job_id ─────────────────────────────────────────────────


class TestMakeJobId:
    """Verify job-ID derivation from LinkedIn URLs."""

    def test_extracts_numeric_id_from_view_url(self):
        url = "https://www.linkedin.com/jobs/view/1234567890"
        result = _make_job_id(url, "SDE2", "Acme")
        assert result == "li-1234567890"

    def test_extracts_numeric_id_with_trailing_slash(self):
        url = "https://www.linkedin.com/jobs/view/9876543210/"
        result = _make_job_id(url, "Backend Eng", "Corp")
        assert result == "li-9876543210"

    def test_hash_fallback_when_no_view_id(self):
        url = "https://linkedin.com/jobs/some-other-path"
        result = _make_job_id(url, "Eng", "Co")
        assert result.startswith("li-")
        assert len(result) == 3 + 12  # "li-" + 12 hex chars

    def test_same_inputs_give_same_hash(self):
        url = "https://linkedin.com/jobs/other"
        a = _make_job_id(url, "T", "C")
        b = _make_job_id(url, "T", "C")
        assert a == b

    def test_different_inputs_give_different_hash(self):
        a = _make_job_id("https://linkedin.com/a", "T1", "C1")
        b = _make_job_id("https://linkedin.com/b", "T2", "C2")
        assert a != b

    def test_empty_url_uses_hash(self):
        result = _make_job_id("", "Title", "Company")
        assert result.startswith("li-")


# ── _strip_html ──────────────────────────────────────────────────


class TestStripHtml:
    """Verify HTML stripping for LinkedIn descriptions."""

    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self):
        assert _strip_html("  a   b   c  ") == "a b c"

    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_no_tags(self):
        assert _strip_html("plain text") == "plain text"

    def test_nested_tags(self):
        html = "<div><ul><li>Item 1</li><li>Item 2</li></ul></div>"
        result = _strip_html(html)
        assert "Item 1" in result
        assert "Item 2" in result
        assert "<" not in result
