#!/usr/bin/env python3
"""
Update LOC counts and test-file statistics in the AGENTS.md project-structure tree.

Does NOT regenerate the tree — the tree is hand-crafted and should stay that way.
This script only does targeted in-place updates:
  - LOC counts next to file names (e.g. `~12k LOC`)
  - Test count line (e.g. `~17k tests across ~900 files`)

Usage: scripts/update-agents-md.py
"""

import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parent.parent
AGENTS_MD = REPO / "AGENTS.md"

# Files whose LOC count we track
WATCHED_FILES = [
    "run_agent.py", "model_tools.py", "toolsets.py", "cli.py",
    "hermes_state.py", "hermes_constants.py", "hermes_logging.py",
    "batch_runner.py",
]


def loc_label(path: Path) -> str:
    """Return ~12k LOC or ~923 LOC style label."""
    try:
        count = sum(1 for _ in open(path, "rb"))
        if count >= 1000:
            return f"~{count // 1000}k LOC"
        return f"~{count} LOC"
    except Exception:
        return ""


def update_file_locs(content: str) -> str:
    """Update any (~Xk LOC) annotation after a watched filename in the tree."""
    for fname in WATCHED_FILES:
        fpath = REPO / fname
        if not fpath.exists():
            continue
        label = loc_label(fpath)
        # Match the filename followed by optional text then (~X LOC) or (~Xk LOC)
        # This works with both spaced and column-aligned formatting
        pattern = re.compile(
            rf'(──\s*{re.escape(fname)}.*?)(\(~\d+k?\s*LOC\))'
        )
        def replacer(m):
            # Preserve everything before the old LOC label
            before = m.group(1)
            return f"{before}({label})"
        content = pattern.sub(replacer, content)
    return content


def update_test_count(content: str) -> str:
    """Update the test count annotation on the tests/ line."""
    test_files = list(REPO.glob("tests/**/test_*.py"))
    test_count = len(test_files)
    test_fn_count = 0
    for tf in test_files:
        try:
            text = tf.read_text(errors="replace")
            test_fn_count += len(re.findall(r'^async def test_\w+|^def test_\w+', text, re.MULTILINE))
        except Exception:
            pass
    new_label = f"# Pytest suite (~{test_fn_count // 1000}k individual tests across ~{test_count} files as of May 2026)"
    content = re.sub(
        r'└── tests/\s+#.*$',
        lambda m: f'└── tests/                {new_label}',
        content,
        flags=re.MULTILINE
    )
    return content


def main():
    if not AGENTS_MD.exists():
        print(f"ERROR: {AGENTS_MD} not found", file=sys.stderr)
        return 1

    content = AGENTS_MD.read_text(encoding="utf-8")
    original = content

    # Do targeted in-place updates only
    content = update_file_locs(content)
    content = update_test_count(content)

    if content == original:
        print("No LOC or test-count changes detected — nothing to update.")
        return 0

    AGENTS_MD.write_text(content, encoding="utf-8")
    print(f"Updated LOC/test-count annotations in {AGENTS_MD}")

    # Git: pull, commit, push
    os.chdir(str(REPO))
    subprocess.run(
        ["git", "pull", "--rebase", "origin", "main"],
        capture_output=True, text=True
    )

    result = subprocess.run(
        ["git", "diff", "--stat"],
        capture_output=True, text=True
    )
    print(result.stdout)

    subprocess.run(["git", "add", "AGENTS.md"], capture_output=True, text=True)

    result = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        print("No changes to AGENTS.md — nothing to commit")
        return 0

    result = subprocess.run(
        ["git", "commit", "-m", "chore: update LOC/test counts in AGENTS.md tree"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"git commit error: {result.stderr}", file=sys.stderr)
        return 1
    print(result.stdout)

    result = subprocess.run(
        ["git", "push", "origin", "main"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"git push error: {result.stderr}", file=sys.stderr)
        return 1
    print(result.stdout)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
