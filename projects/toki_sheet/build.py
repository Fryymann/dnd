#!/usr/bin/env python3
"""Assemble the publishable Toki console from template + fonts + character data.

  python3 distill.py       # character_exports/*.json -> toki.data.json
  python3 build.py         # sheet.html + fonts.css + toki.data.json -> dist/toki.html

Run both after dropping a fresh D&D Beyond export in character_exports/, then
re-publish dist/toki.html to the same Artifact URL.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
TEMPLATE = HERE / "sheet.html"
FONTS = HERE / "fonts.css"
DATA = HERE / "toki.data.json"
OUT = HERE / "dist" / "toki.html"


def check_syntax(html):
    """Parse the page's inline script before writing dist/.

    A stray quote inside a play string is a silent, total failure: the page ships,
    the browser refuses the whole script, and nothing renders. Catch it at build.
    """
    node = shutil.which("node")
    if not node:
        print("  ! node not found — skipping the JavaScript syntax check")
        return
    blocks = re.findall(r"<script>([\s\S]*?)</script>", html)
    for i, js in enumerate(blocks):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
            path = f.name
        result = subprocess.run([node, "--check", path], capture_output=True, text=True)
        Path(path).unlink()
        if result.returncode != 0:
            detail = (result.stderr or "").strip().split("\n")
            print(f"JavaScript syntax error in script block {i + 1}:", file=sys.stderr)
            for line in detail[:8]:
                print("  " + line.replace(path, "<inline script>"), file=sys.stderr)
            sys.exit(1)
    print(f"  syntax OK ({len(blocks)} script block{'s' if len(blocks) != 1 else ''})")


def main():
    html = TEMPLATE.read_text()
    for marker, path in (("/*__FONTS__*/", FONTS), ("/*__DATA__*/", DATA)):
        if marker not in html:
            sys.exit(f"template is missing {marker}")
        html = html.replace(marker, path.read_text().strip(), 1)

    check_syntax(html)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)

    data = json.loads(DATA.read_text())
    size = OUT.stat().st_size / 1024
    print(f"{OUT}  {size:.0f} KB")
    print(f"  {data['identity']['name']} — exported {data['exportedAt'][:10]}")
    if size > 16 * 1024:
        sys.exit("over the 16 MB artifact limit")


if __name__ == "__main__":
    main()
