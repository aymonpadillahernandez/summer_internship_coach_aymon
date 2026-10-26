"""Mark on screen where each printed page starts: reads the printed PDF (pypdf), finds the first line of every page
in report.html and puts a small "page N / M" mark there. The marks are hidden when printing, so the print is unchanged."""
import html, re, sys
from pypdf import PdfReader

report, pdf = sys.argv[1], sys.argv[2]
pages = PdfReader(pdf).pages
total = len(pages)
t = open(report, encoding="utf-8").read()
FOOT = re.compile(r"^\s*\d+ / \d+\s*Summer Internship Coach · Aymon Padilla Hernández · MGT 409\s*")
GAP = r"(?:<[^>]*>|\s|&nbsp;|&[a-z#0-9]+;|­)*"
start = t.index("<main")
body_from = t.index(">", start) + 1
mark = lambda n: f'<span class="pgno">page {n} / {total}</span>'
inserts, missed, pos = [(body_from, mark(1))], [], body_from
for n, page in enumerate(pages[1:], start=2):
    text = FOOT.sub("", page.extract_text() or "")
    # skip short lines and table headings repeated at the top of a page (printed in capitals)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) >= 12]
    line = next((l for l in lines if not l.isupper()), lines[0] if lines else "")
    chars = [c for c in line.replace("­", "")[:22] if not c.isspace()]
    rx = re.compile(GAP.join(re.escape(html.escape(c, quote=False)) if c in "&<>" else re.escape(c) for c in chars), re.I)
    m = rx.search(t, pos)
    if not m:
        missed.append((n, line[:40])); continue
    inserts.append((m.start(), mark(n))); pos = m.end()
for at, s in sorted(inserts, reverse=True):
    t = t[:at] + s + t[at:]
style = ('<style>.pgno{display:inline-block;margin:0 6pt 0 0;padding:0 6pt;border-radius:8pt;background:#eef0ff;color:#4b4fd6;'
         'font:600 8pt -apple-system,Helvetica,Arial,sans-serif;vertical-align:1pt;white-space:nowrap}'
         '@media print{.pgno{display:none}}</style>')
t = t.replace("</head>", style + "</head>", 1)
open(report, "w", encoding="utf-8").write(t)
print(f"marked {len(inserts)} of {total} pages; missed: {missed}")
