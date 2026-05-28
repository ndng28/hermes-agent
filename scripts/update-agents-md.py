#!/usr/bin/env python3
"""
Auto-update the project structure tree in AGENTS.md for the Hermes Agent repo.

Scans ~/.hermes/hermes-agent, generates a current tree, preserves existing
annotations for directories that still exist, and updates test/file-size stats.
Commits the change with a descriptive message.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Auto-detect repo path: this script lives at <repo>/scripts/update-agents-md.py
SCRIPT = Path(__file__).resolve()
REPO = SCRIPT.parent.parent  # scripts/ parent = repo root
AGENTS_MD = REPO / "AGENTS.md"

# Directories to skip in the tree
IGNORE_DIRS = {
    ".git", "__pycache__", ".venv", "node_modules", ".pytest_cache",
    ".tox", "*.egg-info", ".github", "web_dist", "dashboard_auth",
    "nix", "locales", "packaging", "datagen-config-examples",
    "docker", "hermes_agent.egg-info", "optional-mcps", "infographic",
    "proxy", "assets", "web",
}

# Top-level files to show in the tree (with their descriptions)
KNOWN_TOP_FILES = {
    "run_agent.py": "AIAgent class — core conversation loop",
    "model_tools.py": "Tool orchestration, discover_builtin_tools(), handle_function_call()",
    "toolsets.py": "Toolset definitions, _HERMES_CORE_TOOLS list",
    "cli.py": "HermesCLI class — interactive CLI orchestrator",
    "hermes_state.py": "SessionDB — SQLite session store (FTS5 search)",
    "hermes_constants.py": "get_hermes_home(), display_hermes_home() — profile-aware paths",
    "hermes_logging.py": "setup_logging() — agent.log / errors.log / gateway.log (profile-aware)",
    "batch_runner.py": "Parallel batch processing",
}


def get_file_size_label(path):
    """Return a human-readable line count label."""
    try:
        count = sum(1 for _ in open(path, "rb"))
        if count < 1000:
            return f"~{count} LOC"
        else:
            return f"~{count // 1000}k LOC"
    except Exception:
        return ""


def get_annotation_from_current(name, current_annotations):
    """Look up existing annotation for a path entry."""
    return current_annotations.get(name, "")


def build_current_annotations(content):
    """Extract existing {path_name: annotation} from the tree section."""
    annotations = {}
    # Look for lines like: ├── name.py   # comment
    # or: ├── dir/                # comment
    tree_section = False
    for line in content.splitlines():
        if line.strip().startswith("## Project Structure"):
            tree_section = True
            continue
        if tree_section and line.strip().startswith("## "):
            break
        if not tree_section:
            continue
        if "```" in line:
            continue
        # Match lines with annotations: anything with a # comment after the name
        m = re.match(r'^[│├└─\s]*(──\s*)?(\S+?/?)\s+# (.*)', line)
        if m:
            name = m.group(2)
            annotations[name] = m.group(3)
        # Also catch multi-line annotations (indented continuation)
    return annotations


def generate_tree(repo_path, current_annotations, max_depth=2):
    """Generate a tree representation as a list of strings."""
    lines = []
    lines.append("```")
    lines.append("hermes-agent/")

    # Collect top-level entries: files in KNOWN_TOP_FILES + directories
    top_entries = []
    seen_dirs = set()

    # Add known files first in order
    for fname in ["run_agent.py", "model_tools.py", "toolsets.py", "cli.py",
                  "hermes_state.py", "hermes_constants.py", "hermes_logging.py",
                  "batch_runner.py"]:
        fpath = repo_path / fname
        if fpath.exists():
            size_label = get_file_size_label(fpath)
            annotation = current_annotations.get(fname, KNOWN_TOP_FILES.get(fname, ""))
            if size_label:
                annotation = f"{annotation} ({size_label})"
            top_entries.append((fname, annotation, "file"))
            seen_dirs.add(fname)

    # Collect directories
    dirs = sorted([
        d.name for d in repo_path.iterdir()
        if d.is_dir() and d.name not in IGNORE_DIRS and not d.name.startswith(".")
    ])
    for dname in dirs:
        annotation = current_annotations.get(dname + "/", "")
        # For known directories, provide default annotations
        known_defaults = {
            "agent": "Agent internals (provider adapters, memory, caching, compression, etc.)",
            "hermes_cli": "CLI subcommands, setup wizard, plugins loader, skin engine",
            "tools": "Tool implementations — auto-discovered via tools/registry.py",
            "gateway": "Messaging gateway — run.py + session.py + platforms/",
            "plugins": "Plugin system (see \"Plugins\" section below)",
            "ui-tui": "Ink (React) terminal UI — `hermes --tui`",
            "tui_gateway": "Python JSON-RPC backend for the TUI",
            "acp_adapter": "ACP server (VS Code / Zed / JetBrains integration)",
            "cron": "Scheduler — jobs.py, scheduler.py",
            "scripts": "run_tests.sh, release.py, auxiliary scripts",
            "website": "Docusaurus docs site",
            "tests": "Pytest suite",
            "optional-skills": "Heavier/niche skills shipped but NOT active by default",
            "skills": "Built-in skills bundled with the repo",
            "providers": "Provider adapters (separate from plugins/model-providers)",
            "acp_registry": "ACP registry for tool registration",
            "docs": "Documentation and plans",
            "web": "Web frontend (dashboard, etc.)",
        }
        if not annotation and dname in known_defaults:
            annotation = known_defaults[dname]
        top_entries.append((dname + "/", annotation, "dir"))

    # Render top-level entries
    n = len(top_entries)
    for i, (name, annotation, etype) in enumerate(top_entries):
        is_last = (i == n - 1)
        connector = "└── " if is_last else "├── "
        annotation_str = f"  # {annotation}" if annotation else ""
        lines.append(f"{connector}{name}{annotation_str}")

        # For directories at depth 1, show their immediate children at depth 2
        if etype == "dir" and max_depth >= 2:
            dir_path = repo_path / name.rstrip("/")
            if dir_path.exists() and dir_path.is_dir():
                # Determine the child indentation prefix
                child_indent = "    " if is_last else "│   "

                known_subdirs = {
                    "gateway": [("platforms/", "Adapter per platform (telegram, discord, slack, …)"),
                                ("builtin_hooks/", "Extension point for always-registered gateway hooks")],
                    "tools": [("environments/", "Terminal backends (local, docker, ssh, modal, …)"),
                              ("computer_use/", ""),
                              ("neutts_samples/", "")],
                    "plugins": [("memory/", "Memory-provider plugins"),
                                ("context_engine/", "Context-engine plugins"),
                                ("model-providers/", "Inference backend plugins"),
                                ("kanban/", "Multi-agent board dispatcher + worker plugin"),
                                ("web/", ""),
                                ("browser/", ""),
                                ("image_gen/", "Image-generation providers"),
                                ("video_gen/", ""),
                                ("spotify/", ""),
                                ("platforms/", ""),
                                ("security-guidance/", ""),
                                ("hermes-achievements/", "Gamified achievement tracking"),
                                ("observability/", "Metrics / traces / logs plugin"),
                                ("teams_pipeline/", ""),
                                ("google_meet/", ""),
                                ("disk-cleanup/", ""),
                                ("example-dashboard/", "")],
                    "ui-tui": [("src/", "entry.tsx, app.tsx, + app/components/hooks/lib"),
                               ("packages/", ""),
                               ("scripts/", "")],
                    "scripts": [("lib/", ""),
                                ("tests/", ""),
                                ("whatsapp-bridge/", "")],
                    "tests": [("agent/", ""), ("tools/", ""), ("gateway/", ""),
                              ("hermes_cli/", ""), ("cli/", ""), ("cron/", ""),
                              ("plugins/", ""), ("integration/", ""), ("e2e/", ""),
                              ("fakes/", ""), ("scripts/", ""), ("skills/", ""),
                              ("stress/", ""), ("providers/", ""), ("run_agent/", ""),
                              ("website/", ""), ("honcho_plugin/", ""),
                              ("openviking_plugin/", ""), ("tui_gateway/", ""),
                              ("acp/", ""), ("acp_adapter/", ""),
                              ("hermes_state/", ""), ("docker/", "")],
                    "agent": [("lsp/", ""), ("secret_sources/", ""), ("transports/", "")],
                    "website": [("docs/", ""), ("i18n/", ""), ("scripts/", ""), ("src/", ""), ("static/", "")],
                    "docs": [("plans/", ""), ("releases/", "")],
                    "skills": [("autonomous-ai-agents/", ""), ("creative/", ""), ("devops/", ""),
                               ("software-development/", ""), ("dogfood/", ""), ("github/", ""),
                               ("research/", ""), ("data-science/", ""), ("media/", ""),
                               ("mlops/", ""), ("note-taking/", ""), ("productivity/", ""),
                               ("social-media/", ""), ("email/", ""), ("gaming/", ""),
                               ("mcp/", ""), ("smart-home/", ""), ("red-teaming/", ""),
                               ("domain/", ""), ("inference-sh/", ""), ("gifs/", ""),
                               ("index-cache/", ""), ("apple/", ""), ("diagramming/", ""),
                               ("yuanbao/", ""), ("music/", "")],
                }
                if name.rstrip("/") in known_subdirs:
                    child_list = known_subdirs[name.rstrip("/")]
                    nc = len(child_list)
                    for j, (cname, cann) in enumerate(child_list):
                        # Verify child dir still exists
                        cpath = dir_path / cname.rstrip("/")
                        if not cpath.exists():
                            continue
                        # Check if this is the last existing child
                        is_last_child = (j == nc - 1)
                        cprefix = f"{child_indent}└── " if is_last_child else f"{child_indent}├── "
                        cann_str = f"  # {cann}" if cann else ""
                        lines.append(f"{cprefix}{cname}{cann_str}")

    lines.append("```")
    return lines


def update_stats(content):
    """Update the test count and file size annotations in the content."""
    repo = REPO

    # Update test count line
    test_files = list(repo.glob("tests/**/test_*.py"))
    test_count = len(test_files)
    # Count pytest-style test functions
    test_fn_count = 0
    for tf in test_files:
        try:
            text = tf.read_text(errors="replace")
            test_fn_count += len(re.findall(r'^async def test_\w+|^def test_\w+', text, re.MULTILINE))
        except Exception:
            pass
    test_label = f"# Pytest suite (~{test_fn_count // 1000}k individual tests across ~{test_count} files as of May 2026)"
    content = re.sub(
        r'└── tests/\s+#.*$',
        f'└── tests/                {test_label}',
        content,
        flags=re.MULTILINE
    )

    # Update LOC labels for top-level files
    for fname in ["run_agent.py", "cli.py", "model_tools.py", "toolsets.py",
                  "hermes_state.py", "hermes_constants.py", "hermes_logging.py",
                  "batch_runner.py"]:
        fpath = repo / fname
        if fpath.exists():
            loc = sum(1 for _ in open(fpath, "rb"))
            loc_label = f"~{loc // 1000}k LOC" if loc >= 1000 else f"~{loc} LOC"
            # Update the annotation
            def update_loc(m):
                existing = m.group(2) if m.lastindex and m.group(2) else ""
                # Remove old loc label
                existing = re.sub(r'\s*\(~?\d+k?\s*LOC\)', '', existing).strip()
                new_ann = f"{existing} ({loc_label})" if existing else loc_label
                return f"{m.group(1)}  # {new_ann}"
            # Match the file line: prefix + filename + opt annotation
            content = re.sub(
                rf'^([│├└─\s]*──\s*{re.escape(fname)})\s*(?:#\s*(.*))?$',
                lambda m, fn=fname, ll=loc_label: update_loc(m),
                content,
                flags=re.MULTILINE
            )

    return content


def main():
    repo = REPO
    if not AGENTS_MD.exists():
        print(f"ERROR: {AGENTS_MD} not found", file=sys.stderr)
        return 1

    content = AGENTS_MD.read_text(encoding="utf-8")

    # Extract current annotations
    current_annotations = build_current_annotations(content)

    # Find the project structure section boundaries
    section_start = re.search(r'^## Project Structure\n', content, re.MULTILINE)
    section_end = re.search(r'\n## ', content[section_start.end():], re.MULTILINE)

    if not section_start:
        print("ERROR: Could not find ## Project Structure section", file=sys.stderr)
        return 1

    start_idx = section_start.start()
    if section_end:
        end_idx = section_start.end() + section_end.start()
    else:
        end_idx = len(content)

    # Generate new tree
    tree_lines = generate_tree(repo, current_annotations, max_depth=2)

    # Build the new section
    after_header = content[section_start.end():end_idx]
    after_header_first_line = after_header.split('\n', 1)[0] if '\n' in after_header else ""
    
    # Keep the intro text between the header and the code block
    intro_match = re.match(r'(\n.*?\n)```', after_header, re.DOTALL)
    if intro_match:
        intro = intro_match.group(1)
    else:
        intro = "\n\nFile counts shift constantly — don't treat the tree below as exhaustive.\nThe canonical source is the filesystem. The notes call out the load-bearing\nentry points you'll actually edit.\n\n"

    new_section = f"## Project Structure{intro}" + "\n".join(tree_lines) + "\n"

    # Replace the section
    new_content = content[:start_idx] + new_section + content[end_idx:]

    # Update stats
    new_content = update_stats(new_content)

    # Write
    AGENTS_MD.write_text(new_content, encoding="utf-8")
    print(f"Updated {AGENTS_MD}")

    # Git: pull latest from upstream first to avoid conflicts
    os.chdir(str(repo))
    subprocess.run(
        ["git", "pull", "--rebase", "origin", "main"],
        capture_output=True, text=True
    )

    result = subprocess.run(
        ["git", "diff", "--stat"],
        capture_output=True, text=True
    )
    print(result.stdout)

    result = subprocess.run(
        ["git", "add", "AGENTS.md"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"git add error: {result.stderr}", file=sys.stderr)
        return 1

    # Check if there's actually a diff
    result = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        print("No changes to AGENTS.md — nothing to commit")
        return 0

    result = subprocess.run(
        ["git", "commit", "-m", "chore: auto-update AGENTS.md project structure tree"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"git commit error: {result.stderr}", file=sys.stderr)
        return 1
    print(result.stdout)

    # Push to origin
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"git push error: {result.stderr}", file=sys.stderr)
        return 1
    print(result.stdout)
    print("Committed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
