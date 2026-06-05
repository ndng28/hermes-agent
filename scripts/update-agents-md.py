#!/usr/bin/env python3
"""
Update LOC counts and test-file statistics in the AGENTS.md project-structure tree.

Does NOT regenerate the tree — the tree is hand-crafted and should stay that way.
This script only does targeted in-place updates:
  - LOC counts next to file names (e.g. `~12k LOC`)
  - Test count line (e.g. `~17k tests across ~900 files`)

Usage: scripts/update-agents-md.py

Safety:
  - Refuses to run if the working tree is dirty (uncommitted changes or untracked
    files we don't recognize). This prevents the script from clobbering in-progress
    work or silently committing mixed changes at 3 AM.
  - Bails on git pull/rebase failure instead of proceeding to commit+push.
  - Restores any AGENTS.md modifications from the rebase before exiting non-zero.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parent.parent
AGENTS_MD = REPO / "AGENTS.md"
BACKUP_MD = REPO / "AGENTS.md.agents-md-backup"

# Files whose LOC count we track
WATCHED_FILES = [
    "run_agent.py", "model_tools.py", "toolsets.py", "cli.py",
    "hermes_state.py", "hermes_constants.py", "hermes_logging.py",
    "batch_runner.py",
]


def run(cmd, **kw):
    """Run a subprocess and return (returncode, stdout, stderr). Never raises."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return result.returncode, result.stdout, result.stderr


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
        pattern = re.compile(
            rf'(──\s*{re.escape(fname)}.*?)(\(~\d+k?\s*LOC\))'
        )
        def replacer(m, label=label):
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


def working_tree_clean() -> tuple[bool, str]:
    """Return (clean, status_output). True if no uncommitted changes exist."""
    rc, out, _ = run(["git", "status", "--porcelain"], cwd=str(REPO))
    if rc != 0:
        return False, "git status failed"
    return (not out.strip()), out


def main():
    if not AGENTS_MD.exists():
        print(f"ERROR: {AGENTS_MD} not found", file=sys.stderr)
        return 1

    os.chdir(str(REPO))

    # Gate 1: working tree must be clean. This protects against:
    #   - in-progress edits getting clobbered by a stale rebase
    #   - AGENTS.md updates being lumped into an unrelated commit
    #   - untracked files from a debug session getting added to the repo
    clean, status_out = working_tree_clean()
    if not clean:
        print("SKIP: working tree is dirty — refusing to run to protect uncommitted work")
        print(f"  git status --porcelain:\n{status_out}")
        print("  Resolve uncommitted changes and re-run, or run with --force to override.")
        return 0

    # Read current state
    content = AGENTS_MD.read_text(encoding="utf-8")
    original = content

    # Do targeted in-place updates
    content = update_file_locs(content)
    content = update_test_count(content)

    if content == original:
        print("No LOC or test-count changes detected — nothing to update.")
        return 0

    # Back up the original so we can restore it on rebase failure
    shutil.copy2(AGENTS_MD, BACKUP_MD)
    try:
        AGENTS_MD.write_text(content, encoding="utf-8")
        print(f"Updated LOC/test-count annotations in {AGENTS_MD}")

        # Sync with origin first. If rebase conflicts, we bail before committing.
        rc, out, err = run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=str(REPO),
        )
        if rc != 0:
            print(f"ERROR: git pull --rebase failed (rc={rc})", file=sys.stderr)
            print(f"  stderr: {err}", file=sys.stderr)
            print("  Aborting rebase and restoring AGENTS.md from backup.")
            run(["git", "rebase", "--abort"], cwd=str(REPO))
            shutil.copy2(BACKUP_MD, AGENTS_MD)
            return 1

        # Stage the change
        run(["git", "add", "AGENTS.md"], cwd=str(REPO))

        rc, staged_out, _ = run(
            ["git", "diff", "--cached", "--stat"],
            cwd=str(REPO),
        )
        if not staged_out.strip():
            print("No changes to AGENTS.md after rebase — nothing to commit")
            return 0

        # Commit
        rc, out, err = run(
            ["git", "commit", "-m", "chore: update LOC/test counts in AGENTS.md tree"],
            cwd=str(REPO),
        )
        if rc != 0:
            print(f"ERROR: git commit failed (rc={rc}): {err}", file=sys.stderr)
            print("  Restoring AGENTS.md from backup.")
            shutil.copy2(BACKUP_MD, AGENTS_MD)
            return 1
        print(out)

        # Push
        rc, out, err = run(
            ["git", "push", "origin", "main"],
            cwd=str(REPO),
        )
        if rc != 0:
            print(f"ERROR: git push failed (rc={rc}): {err}", file=sys.stderr)
            print("  Commit is local only. AGENTS.md restored from backup to keep tree clean.")
            run(["git", "reset", "--soft", "HEAD~1"], cwd=str(REPO))
            shutil.copy2(BACKUP_MD, AGENTS_MD)
            return 1
        print(out)
        print("Done.")
        return 0
    finally:
        # Always clean up the backup file
        if BACKUP_MD.exists():
            BACKUP_MD.unlink()


if __name__ == "__main__":
    if "--force" in sys.argv:
        sys.argv.remove("--force")
        # Force mode: skip the dirty-tree check
        import builtins
        original_clean = working_tree_clean
        working_tree_clean = lambda: (True, "")
    sys.exit(main())