"""Tests for token-saving helpers in resume.tailor."""

from __future__ import annotations

import textwrap

from resume.tailor import _strip_latex_comments, _truncate_description


# ── _strip_latex_comments ────────────────────────────────────────


class TestStripLatexComments:
    """Verify that pure-comment lines are removed while code lines are kept."""

    def test_removes_pure_comment_lines(self):
        src = textwrap.dedent("""\
            \\begin{document}
            % This is a comment
            Hello
            % Another comment
            \\end{document}
        """)
        result = _strip_latex_comments(src)
        assert "% This is a comment" not in result
        assert "% Another comment" not in result

    def test_keeps_code_lines(self):
        src = textwrap.dedent("""\
            \\begin{document}
            Hello world
            \\end{document}
        """)
        result = _strip_latex_comments(src)
        assert "\\begin{document}" in result
        assert "Hello world" in result
        assert "\\end{document}" in result

    def test_keeps_inline_comments(self):
        src = "\\item Some text  % inline note\n"
        result = _strip_latex_comments(src)
        assert "\\item Some text  % inline note" in result

    def test_removes_indented_comment_lines(self):
        src = "  % indented comment\nKeep this\n"
        result = _strip_latex_comments(src)
        assert "% indented comment" not in result
        assert "Keep this" in result

    def test_empty_input(self):
        assert _strip_latex_comments("") == ""

    def test_all_comments(self):
        src = "% a\n% b\n% c\n"
        result = _strip_latex_comments(src)
        # Should be empty lines joined (all lines removed)
        assert "%" not in result

    def test_preserves_document_structure(self):
        """The stripped template should still be compilable LaTeX."""
        src = textwrap.dedent("""\
            \\documentclass{resume}
            \\begin{document}
            % ---- EXPERIENCE ----
            \\begin{rSection}{EXPERIENCE}
            \\item Did stuff
            % \\item Old stuff
            \\end{rSection}
            % ---- EXTRA ----
            % \\begin{rSection}{EXTRA}
            % \\item Removed
            % \\end{rSection}
            \\end{document}
        """)
        result = _strip_latex_comments(src)
        assert "\\documentclass{resume}" in result
        assert "\\begin{document}" in result
        assert "\\item Did stuff" in result
        assert "Old stuff" not in result
        assert "EXTRA" not in result
        assert "\\end{document}" in result


# ── _truncate_description ────────────────────────────────────────


class TestTruncateDescription:
    """Verify job-description truncation."""

    def test_short_text_unchanged(self):
        text = "Short description"
        assert _truncate_description(text, max_chars=100) == text

    def test_exact_length_unchanged(self):
        text = "a" * 100
        assert _truncate_description(text, max_chars=100) == text

    def test_long_text_truncated(self):
        text = "a" * 200
        result = _truncate_description(text, max_chars=100)
        assert len(result) == 101  # 100 chars + ellipsis
        assert result.endswith("…")
        assert result[:100] == "a" * 100

    def test_empty_text(self):
        assert _truncate_description("", max_chars=100) == ""

    def test_uses_config_default(self):
        """When max_chars is None, falls back to config.CLAUDE_JOB_DESC_MAX_CHARS."""
        import config
        long_text = "x" * (config.CLAUDE_JOB_DESC_MAX_CHARS + 500)
        result = _truncate_description(long_text)
        assert len(result) == config.CLAUDE_JOB_DESC_MAX_CHARS + 1  # +1 for ellipsis
