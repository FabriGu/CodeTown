"""What an agent did in a repository: the files it read and changed, the commands it ran.

    python3 session.py PATH [TRANSCRIPT]

Reads the newest Claude Code or Cursor transcript for PATH, or the one given,
with its subagents. Only paths and the first line of each command are kept,
never file contents or edit text. The steps are saved as session.json next to
the survey, never inside the repository.
"""

import argparse
import glob
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime

from repo import Repo

READ, EDIT, WRITE, DELETE, COMMAND = "read", "edit", "write", "delete", "command"
CHANGES = (EDIT, WRITE, DELETE)
TOOLS = {"Read": READ, "Edit": EDIT, "MultiEdit": EDIT, "StrReplace": EDIT,
         "NotebookEdit": EDIT, "EditNotebook": EDIT, "Write": WRITE, "Delete": DELETE,
         "Bash": COMMAND, "Shell": COMMAND}
PATH_KEYS = ("file_path", "path", "notebook_path", "target_notebook")
COMMAND_CHARS = 200
# A command started by the last tool call can still be writing after it.
SETTLE_SECONDS = 300
REPORT_LIMIT = 10


@dataclass
class Step:
    kind: str
    tool: str
    path: str | None = None
    command: str | None = None
    at: str | None = None
    failed: bool = False
    agent: str = "main"


def _n(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def transcripts(root, home="~"):
    """Every transcript for the repository, oldest first."""
    home = os.path.expanduser(home)
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(root))
    found = glob.glob(os.path.join(home, ".claude", "projects", slug, "*.jsonl"))
    found += glob.glob(os.path.join(home, ".cursor", "projects", slug.lstrip("-"),
                                    "agent-transcripts", "*", "*.jsonl"))
    return sorted(found, key=os.path.getmtime)


def _relative(raw, root):
    import towncode  # towncode imports the renderer, which imports focus and so this module

    full = os.path.realpath(os.path.join(root, raw))
    return os.path.relpath(full, root) if towncode._inside(full, root) else full


def read_steps(path, root, agent="main"):
    root = os.path.realpath(root)
    steps, by_id = [], {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            content = (entry.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else ():
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result" and block.get("is_error"):
                    if block.get("tool_use_id") in by_id:
                        by_id[block["tool_use_id"]].failed = True
                kind = TOOLS.get(block.get("name")) if block.get("type") == "tool_use" else None
                if kind is None:
                    continue
                args = block.get("input") or {}
                if not isinstance(args, dict):
                    continue
                step = Step(kind, block["name"], at=entry.get("timestamp"), agent=agent)
                if kind == COMMAND:
                    lines = (args.get("command") or "").strip().splitlines()
                    step.command = lines[0][:COMMAND_CHARS] if lines else ""
                else:
                    raw = next((args[k] for k in PATH_KEYS if args.get(k)), None)
                    if raw is None:
                        continue
                    step.path = _relative(raw, root)
                steps.append(step)
                if block.get("id"):
                    by_id[block["id"]] = step
    return steps


def load(transcript, root):
    """Steps from a transcript and its subagents, in time order when the times are known.

    Cursor records no tool results, so an edit is only known to have failed when
    the file it edited does not exist: an edit cannot create one.
    """
    steps = read_steps(transcript, root)
    stem = os.path.splitext(transcript)[0]
    for folder in sorted({stem, os.path.dirname(transcript)}):
        for sub in sorted(glob.glob(os.path.join(folder, "subagents", "*.jsonl"))):
            steps += read_steps(sub, root, agent=os.path.splitext(os.path.basename(sub))[0])
    if all(s.at for s in steps):
        steps.sort(key=lambda s: s.at)
    for s in steps:
        if s.kind == EDIT and not os.path.lexists(os.path.join(root, s.path)):
            s.failed = True
    return steps


def _seconds(at):
    return datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()


def changed_outside_tools(root, steps):
    """Tracked files last modified while the session ran, but not by an edit tool.

    Modification times only show the last change, so a file edited again after
    the session is missed. Without times (Cursor) nothing can be said.
    """
    times = [_seconds(s.at) for s in steps if s.at]
    if not times:
        return None
    start, end = min(times), max(times) + SETTLE_SECONDS
    touched = {s.path for s in steps if s.kind in CHANGES and not s.failed}
    found = []
    for rel in Repo(root).files():
        try:
            mtime = os.lstat(os.path.join(root, rel)).st_mtime
        except OSError:
            continue
        if start <= mtime <= end and rel not in touched:
            found.append(rel)
    return found


def agent_name(transcript):
    return "Claude Code" if f"{os.sep}.claude{os.sep}" in transcript else "Cursor"


def report(repo_name, transcript, steps, stray):
    changed, read, blind, outside = {}, set(), [], {}
    for s in steps:
        if s.path is None or s.failed:
            continue
        if os.path.isabs(s.path):
            outside.setdefault(s.path, set()).add(s.kind)
        elif s.kind in CHANGES:
            if s.kind == EDIT and s.path not in read and s.path not in changed:
                blind.append(s.path)
            changed.setdefault(s.path, []).append(s.kind)
        elif s.kind == READ:
            read.add(s.path)
    commands = [s.command for s in steps if s.kind == COMMAND]
    failed = sum(1 for s in steps if s.failed and s.kind in CHANGES)
    agents = sorted({s.agent for s in steps} - {"main"})
    times = sorted(_seconds(s.at) for s in steps if s.at)
    when = ""
    if times:
        start, end = (f"{datetime.fromtimestamp(t):%Y-%m-%d %H:%M}" for t in (times[0], times[-1]))
        when = f", {start} to {end}"
    lines = [f"{repo_name}: {agent_name(transcript)} session "
             f"{os.path.basename(os.path.splitext(transcript)[0])[:8]}{when}"
             + (f", {_n(len(agents), 'subagent')}" if agents else ""),
             f"changed {_n(len(changed), 'file')}, read {len(read - set(changed))} more, "
             f"ran {_n(len(commands), 'command')}"
             + (f", {_n(failed, 'failed change')}" if failed else "")]

    def section(title, items):
        if items:
            lines.extend(["", title])
            lines.extend(f"  {item}" for item in items[:REPORT_LIMIT])
            if len(items) > REPORT_LIMIT:
                lines.append(f"  ... and {len(items) - REPORT_LIMIT} more")

    def tally(kinds):
        return ", ".join(k if n == 1 else f"{k} x{n}" for k, n in Counter(kinds).items())

    section("Changed:", [f"{p} ({tally(kinds)})" for p, kinds in sorted(changed.items())])
    section("Edited without reading it first:", blind)
    if stray is None:
        lines += ["", "No times in this transcript, so changes made by commands can't be checked."]
    else:
        section("Changed on disk while the session ran, not by an edit tool "
                "(a command, you, or something else):", stray)
    section("Outside the repository:", [f"{p} ({', '.join(sorted(k))})"
                                        for p, k in sorted(outside.items())])
    section(f"Commands, last {min(len(commands), REPORT_LIMIT)}:", commands[-REPORT_LIMIT:])
    return "\n".join(lines)


def main(argv=None):
    import towncode  # towncode imports the renderer, which imports focus and so this module

    parser = argparse.ArgumentParser(prog="session")
    parser.add_argument("path")
    parser.add_argument("transcript", nargs="?", help="default: the newest one for PATH")
    args = parser.parse_args(argv)
    root = os.path.realpath(args.path)
    towncode._require_repo(root)
    found = [args.transcript] if args.transcript else transcripts(root)
    if not found:
        raise SystemExit(f"no Claude Code or Cursor transcript found for {root}")
    transcript = found[-1]
    out = towncode.output_dir(root)
    if towncode._inside(out, root):
        raise SystemExit(f"refusing to write inside the surveyed repository: {out}")
    steps = load(transcript, root)
    stray = changed_outside_tools(root, steps)
    os.makedirs(out, exist_ok=True)
    saved = os.path.join(out, "session.json")
    with open(saved, "w", encoding="utf-8") as f:
        json.dump({"transcript": transcript, "agent": agent_name(transcript),
                   "steps": [asdict(s) for s in steps], "changed_outside_tools": stray},
                  f, indent=1, sort_keys=True)
    print(report(os.path.basename(root), transcript, steps, stray))
    print(f"\nsaved to {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
