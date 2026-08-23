from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from import_sichengshuo_batch5 import parse_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render client-facing Feishu XML for 思丞说 batch 5.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("runs/creation-deliveries/sichengshuo-batch5-20260813/scripts.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    items = parse_manifest(args.manifest)
    current_direction = ""
    lines: list[str] = []
    for item in items:
        if item["direction"] != current_direction:
            if current_direction:
                lines.append("<hr/>")
            current_direction = item["direction"]
            lines.append(f"<h2>{escape(current_direction)}</h2>")
        lines.append(f"<h3>{escape(item['number'])}｜{escape(item['title'])}</h3>")
        for paragraph in item["body"].split("\n\n"):
            if paragraph.strip():
                lines.append(f"<p>{escape(paragraph.strip())}</p>")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
