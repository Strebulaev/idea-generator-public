import sys
import json
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python summary.py <final.json>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))

    lines = [
        "## 🚀 Idea Generator Run",
        "",
        f"- **Topic:** {data.get('topic', '-')}",
        f"- **Domain:** {data.get('domain', '-')}",
        f"- **Constraints:** {data.get('constraints', '-') or '-'}",
        f"- **Status:** {data.get('status', '-')}",
        f"- **Started at:** {data.get('started_at', '-')}",
        "",
    ]

    if data.get("ideas"):
        lines.append("### 💡 Ideas generated")
        for idea in data["ideas"][:5]:
            lines.append(f"- **{idea.get('title', idea.get('id', '-'))}** — {idea.get('description', '')}")
        lines.append("")

    if data.get("one_pager"):
        lines.append("### 📄 One-pager")
        lines.append(data["one_pager"][:2000])
        lines.append("")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
