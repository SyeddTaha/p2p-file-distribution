"""Check the documentation exporter without a browser or repository output writes."""

import base64
import shutil
import subprocess
import sys
from pathlib import Path


def prepare_report(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    builder = docs / "build_course_report.py"
    shutil.copyfile(Path(__file__).resolve().parents[2] / "docs/build_course_report.py", builder)
    (docs / "figure.png").write_bytes(b"fixture-image")
    (docs / "course-report.md").write_text(
        "# Export fixture\n\n<script>unsafe()</script>\n\n"
        "| Item | Value |\n|---|---|\n| mode | `p2p` |\n\n"
        "![Fixture](figure.png)\n\n<!-- pagebreak -->\n\n"
        "## Evidence\n\n- First\n  continuation\n- Second\n\n"
        "[Local evidence](evidence.md)\n\n```text\n<literal>\n```\n",
        encoding="utf-8",
    )
    return builder


def test_export_embeds_figures_escapes_text_and_preserves_page_breaks(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(prepare_report(tmp_path))],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    exported = (tmp_path / "output/course-report.html").read_text(encoding="utf-8")
    assert "Exported" in result.stdout
    assert exported.count('<section class="page">') == 2
    assert "<script>" not in exported and "&lt;script&gt;" in exported
    assert "data:image/png;base64," + base64.b64encode(b"fixture-image").decode() in exported
    assert "<th>Item</th>" in exported and "<td><code>p2p</code></td>" in exported
    assert "<li>First continuation</li>" in exported
    assert 'href="../docs/evidence.md"' in exported
    assert "&lt;literal&gt;" in exported
    assert "P2P File Distribution | 2 / 2" in exported


def test_pdf_export_reports_missing_browser_without_installing(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(prepare_report(tmp_path)),
            "--pdf",
            "--browser",
            str(tmp_path / "no-browser.exe"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert "Browser executable not found" in result.stderr
    assert (tmp_path / "output/course-report.html").is_file()
    assert not (tmp_path / "output/pdf/course-report.pdf").exists()
