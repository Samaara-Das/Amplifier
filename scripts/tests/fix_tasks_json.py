"""Fix encoding issues in tasks.json and add task 56."""
import json
import re
from pathlib import Path

tasks_file = Path(__file__).resolve().parent.parent.parent / ".taskmaster" / "tasks" / "tasks.json"

with open(tasks_file, "rb") as f:
    raw = f.read()

# Strip ALL non-ASCII bytes
clean = bytearray(b for b in raw if b < 128)
text = bytes(clean).decode("ascii")
text = text.replace("\r\n", "\n").replace("\r", "\n")

# Fix orphaned unescaped double quotes inside JSON string values
# These appear when mojibake (smart quotes) get stripped to bare "
# Strategy: process line by line, fix description lines
lines = text.split("\n")
fixed_lines = []
for line in lines:
    if '"description":' in line and len(line) > 200:
        # Extract the JSON string value manually
        # Format: "description": "...value...",
        colon_pos = line.index('"description":') + len('"description":')
        rest = line[colon_pos:].strip()
        if rest.startswith('"'):
            # Find the closing quote (last " before optional comma)
            # Remove all inner bare quotes from the value
            value_start = colon_pos + len(rest) - len(rest.lstrip()) + 1
            # Find everything between first and last quote
            inner_start = line.index('"', colon_pos) + 1
            # Find last quote (possibly followed by comma)
            stripped = line.rstrip()
            if stripped.endswith('",'):
                inner_end = len(stripped) - 2
                suffix = '",'
            elif stripped.endswith('"'):
                inner_end = len(stripped) - 1
                suffix = '"'
            else:
                fixed_lines.append(line)
                continue

            prefix = line[:inner_start]
            value = line[inner_start:inner_end]
            # Remove bare double quotes from value (they're mojibake artifacts)
            value = value.replace('"', "'")
            fixed_lines.append(prefix + value + suffix)
            continue
    fixed_lines.append(line)

text = "\n".join(fixed_lines)

try:
    data = json.loads(text)
    print(f"Parsed OK: {len(data['master']['tasks'])} tasks")

    # Add task 56
    task_ids = {t["id"] for t in data["master"]["tasks"]}
    if "56" not in task_ids:
        data["master"]["tasks"].append({
            "id": "56",
            "title": "Integrate video generation (Seedance 2 or similar) as user-toggleable feature",
            "description": "Add video generation integration to Amplifier. Users can enable/disable from settings. Content pipeline produces short-form UGC videos for TikTok, Instagram Reels, LinkedIn, Facebook. Requirements: 1) Research best ultra-cheap video gen tool at implementation time 2) Plug-and-play toggle in user settings 3) Enable/disable per platform 4) Videos stored locally, attached to drafts 5) Campaign wizard: companies can request video content 6) Model-agnostic architecture. Do NOT lock in a specific tool now.",
            "status": "pending",
            "priority": "medium",
            "dependencies": ["54"],
            "tags": ["future", "user", "content-generation", "video-gen"],
            "subtasks": [],
        })
        print("Added task #56")

    data["master"]["metadata"]["taskCount"] = len(data["master"]["tasks"])

    with open(tasks_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
    print(f"Written clean JSON: {len(data['master']['tasks'])} tasks")

    for t in data["master"]["tasks"]:
        if int(t["id"]) >= 15:
            print(f"  #{t['id']:3s} {t['status']:15s} {t['title'][:60]}")

except json.JSONDecodeError as e:
    print(f"Still broken: line {e.lineno}, col {e.colno}: {e.msg}")
    lines = text.split("\n")
    problem_line = lines[e.lineno - 1]
    start = max(0, e.colno - 30)
    end = min(len(problem_line), e.colno + 30)
    print(f"Context: {repr(problem_line[start:end])}")
