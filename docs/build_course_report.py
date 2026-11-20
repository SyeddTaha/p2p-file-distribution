"""Export the report as standalone HTML and optional PDF without new packages.

Regenerate plots first. PDF export requires an already installed Chrome/Chromium.
The Markdown renderer supports only the constructs used by course-report.md.
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "course-report.md"
OUTPUT = ROOT / "output"
CSS = """
@page { size:A4; margin:16mm 18mm; }
* { box-sizing:border-box; }
body { margin:0; color:#203047; background:#eef2f6; font:10pt/1.36 Arial,sans-serif; }
main { max-width:210mm; margin:auto; }
.page { padding:16mm 18mm; background:white; margin:12px auto; }
.kicker { font-size:8pt; color:#557085; letter-spacing:1.2px; text-transform:uppercase; }
h1 { font-size:29pt; line-height:1.08; color:#123b56; margin:10mm 0 6mm; }
h2 { font-size:17pt; line-height:1.16; color:#123b56; margin:0 0 5mm; }
h3 { font-size:11pt; color:#146f78; margin:5mm 0 2mm; }
p { margin:0 0 3mm; }
ul,ol { padding-left:5mm; margin:2mm 0 4mm; }
li { margin:0 0 1.5mm; }
table { width:100%; border-collapse:collapse; margin:3mm 0 4mm; font-size:9pt; }
th { background:#123b56; color:white; text-align:left; }
th,td { padding:2.1mm 2.4mm; vertical-align:top; border-bottom:0.3mm solid #d9e2e9; }
tr:nth-child(even) td { background:#f3f6f8; }
table,figure,pre { break-inside:avoid; }
h2,h3 { break-after:avoid; }
figure { margin:2mm 0 3mm; }
figure img { width:100%; height:77mm; object-fit:contain; display:block; }
code { font:8.2pt Consolas,monospace; background:#f0f4f6; overflow-wrap:anywhere; }
pre { padding:3mm; background:#f0f4f6; white-space:pre-wrap; font-size:8.1pt; }
pre code { font-size:8.1pt; background:transparent; }
a { color:#146f78; text-decoration:none; overflow-wrap:anywhere; }
.page-number { color:#657687; font-size:8pt; text-align:right; margin-top:5mm; }
.page:nth-child(3) { font-size:9.4pt; line-height:1.28; }
.page:nth-child(3) p { margin-bottom:2mm; }
.page:nth-child(3) th,.page:nth-child(3) td { padding:1.5mm 2.4mm; }
@media print {
 body { background:white; }
 main { max-width:none; }
 .page { padding:0; margin:0; break-after:page; }
 .page:last-child { break-after:auto; }
 * { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
}
"""


def inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)

    def link(match: re.Match[str]) -> str:
        target = os.path.relpath(SOURCE.parent / html.unescape(match[2]), OUTPUT)
        return f'<a href="{html.escape(Path(target).as_posix(), quote=True)}">{match[1]}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, escaped)


def render_page(text: str) -> str:
    lines = text.strip().splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("```"):
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code_lines.append(lines[index])
                index += 1
            blocks.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
        elif match := re.fullmatch(r"!\[([^]]*)\]\(([^)]+)\)", line):
            data = (SOURCE.parent / match[2]).read_bytes()
            uri = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
            blocks.append(f'<figure><img alt="{html.escape(match[1])}" src="{uri}"></figure>')
        elif line.startswith("|"):
            rows: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                    tag = "th" if not rows else "td"
                    rows.append(
                        "<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>"
                    )
                index += 1
            blocks.append("<table>" + "".join(rows) + "</table>")
            continue
        elif match := re.match(r"^(#{1,3}) (.*)", line):
            level = len(match[1])
            blocks.append(f"<h{level}>{inline(match[2])}</h{level}>")
        elif re.match(r"^(?:- |\d+\. )", line):
            tag = "ul" if line.startswith("- ") else "ol"
            pattern = r"^- " if tag == "ul" else r"^\d+\. "
            items = []
            while index < len(lines) and re.match(pattern, lines[index].strip()):
                content = re.sub(pattern, "", lines[index].strip())
                index += 1
                while index < len(lines) and lines[index].startswith("  "):
                    content += " " + lines[index].strip()
                    index += 1
                items.append(f"<li>{inline(content)}</li>")
            blocks.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        else:
            paragraph = [line]
            index += 1
            while index < len(lines) and lines[index].strip():
                paragraph.append(lines[index].strip())
                index += 1
            blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            continue
        index += 1
    return "\n".join(blocks)


def find_browser(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(f"Browser executable not found: {explicit}")
        return explicit.resolve()
    candidates = [
        Path(os.environ.get(variable, "")) / "Google/Chrome/Application/chrome.exe"
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
    ]
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if executable := shutil.which(name):
            candidates.append(Path(executable))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Use --browser with an installed Chrome/Chromium executable")


def build_report(*, pdf: bool = False, browser: Path | None = None) -> Path:
    OUTPUT.mkdir(exist_ok=True)
    pages = SOURCE.read_text(encoding="utf-8").split("<!-- pagebreak -->")
    sections = []
    for number, page in enumerate(pages, 1):
        sections.append(
            '<section class="page"><div class="kicker">Computer Networks / Course report</div>'
            + render_page(page)
            + '<div class="page-number">'
            + f"P2P File Distribution | {number} / {len(pages)}</div></section>"
        )
    target = OUTPUT / "course-report.html"
    target.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>P2P File Distribution - Course Report</title><style>{CSS}</style></head>"
        "<body><main>" + "\n".join(sections) + "</main></body></html>",
        encoding="utf-8",
    )
    if pdf:
        pdf_path = OUTPUT / "pdf" / "course-report.pdf"
        pdf_path.parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="p2p-report-browser-") as profile:
            subprocess.run(
                [
                    str(find_browser(browser)),
                    "--headless",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    f"--user-data-dir={profile}",
                    "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}",
                    target.as_uri(),
                ],
                check=True,
                capture_output=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        if not pdf_path.is_file() or not pdf_path.stat().st_size:
            raise RuntimeError("Browser returned without producing a PDF")
        return pdf_path
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true", help="also export PDF with installed Chrome")
    parser.add_argument("--browser", type=Path, help="installed Chrome/Chromium executable")
    args = parser.parse_args()
    try:
        result = build_report(pdf=args.pdf, browser=args.browser)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        parser.exit(
            1, f"Report export failed: {exc}\nRegenerate plots first; no packages installed.\n"
        )
    print(f"Exported {result.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
