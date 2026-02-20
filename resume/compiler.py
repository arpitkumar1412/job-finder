"""
Compile a tailored LaTeX resume to PDF using pdflatex.

Creates a temporary directory, copies the class file, writes the .tex,
runs pdflatex, and returns the resulting PDF bytes.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)


def compile_latex(tex_source: str, job: dict[str, Any]) -> bytes:
    """
    Compile *tex_source* (a complete LaTeX document) to PDF.

    Parameters
    ----------
    tex_source : str
        Full LaTeX source that uses ``resume.cls``.
    job : dict
        Used only for logging context (company / title).

    Returns
    -------
    bytes
        Raw PDF content.

    Raises
    ------
    RuntimeError
        If pdflatex fails after two passes.
    """
    company = job.get("company", "unknown")
    title = job.get("title", "unknown")
    label = f"{company} — {title}"

    with tempfile.TemporaryDirectory(prefix="resume_") as tmpdir:
        tmp = Path(tmpdir)

        # Copy the .cls file so pdflatex can find it
        cls_src = Path(config.RESUME_CLS)
        if cls_src.exists():
            shutil.copy2(cls_src, tmp / cls_src.name)
        else:
            raise FileNotFoundError(
                f"resume.cls not found at {cls_src.resolve()}"
            )

        # Write the .tex source
        tex_path = tmp / "resume.tex"
        tex_path.write_text(tex_source, encoding="utf-8")

        # Run pdflatex twice (for cross-references / page numbers)
        pdflatex = _find_pdflatex()
        for run in (1, 2):
            result = subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "resume.tex"],
                cwd=str(tmp),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0 and run == 2:
                # Log the tail of the output for debugging
                log_tail = result.stdout[-2000:] if result.stdout else "(empty)"
                logger.error(
                    "pdflatex failed for [%s] (run %d):\n%s",
                    label, run, log_tail,
                )
                raise RuntimeError(
                    f"pdflatex compilation failed for {label}. "
                    f"See logs for details."
                )

        pdf_path = tmp / "resume.pdf"
        if not pdf_path.exists():
            raise RuntimeError(f"PDF not produced for {label}")

        # ── page-count guard: resume must be exactly 1 page ──
        page_count = _count_pdf_pages(pdf_path)
        if page_count > 1:
            logger.warning(
                "PDF for [%s] is %d pages (expected 1). "
                "The tailored resume overflows — it will still be used "
                "but may need manual trimming.",
                label, page_count,
            )

        pdf_bytes = pdf_path.read_bytes()
        logger.info(
            "Compiled PDF for [%s]: %d bytes, %d page(s).",
            label, len(pdf_bytes), page_count,
        )
        return pdf_bytes


def _count_pdf_pages(pdf_path: Path) -> int:
    """Count pages in a PDF by scanning for /Type /Page entries."""
    try:
        raw = pdf_path.read_bytes()
        # Each page object contains '/Type /Page' (not '/Pages')
        import re
        pages = re.findall(rb"/Type\s*/Page(?!s)", raw)
        return len(pages) if pages else 1
    except Exception:
        return 1   # assume 1 if we can't parse


def _find_pdflatex() -> str:
    """Locate the pdflatex binary."""
    which = shutil.which("pdflatex")
    if which:
        return which
    # Common Windows MiKTeX path
    miktex = Path.home() / "AppData" / "Local" / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64" / "pdflatex.exe"
    if miktex.exists():
        return str(miktex)
    raise FileNotFoundError(
        "pdflatex not found on PATH or default MiKTeX location. "
        "Install MiKTeX or TeX Live."
    )
