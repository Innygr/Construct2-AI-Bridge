"""Validate inline JavaScript in the local inspector page with Node.js."""
from __future__ import annotations

import subprocess
from html.parser import HTMLParser
from pathlib import Path


class ScriptCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_script = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self.in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self.in_script = False

    def handle_data(self, data: str) -> None:
        if self.in_script and self.scripts:
            self.scripts[-1] += data


def main() -> int:
    page = Path("src/construct2_ai_bridge/static/index.html")
    parser = ScriptCollector()
    parser.feed(page.read_text(encoding="utf-8"))
    inline_scripts = [script for script in parser.scripts if script.strip()]
    if not inline_scripts:
        raise SystemExit("No inline JavaScript found in inspector page.")
    for index, script in enumerate(inline_scripts, start=1):
        result = subprocess.run(
            ["node", "--check", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            print(f"Inline script {index} failed syntax validation:")
            print(result.stderr or result.stdout)
            return result.returncode
    print(f"Validated syntax for {len(inline_scripts)} inline script(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
