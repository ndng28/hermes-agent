# Built-in Skills

These skills are **active by default** — they're bundled with the agent and
available to every session without explicit installation. They cover common
workflows: git, code review, debugging, email, creative tools, and more.

## For Users

Skills in this directory are loaded automatically. You can also load them
explicitly with `skill_view()` in tools or `/<skill-name>` in the CLI.

## For Contributors

When to put a skill here:
- It covers a common task most users will want (e.g., git workflows, GitHub PRs)
- It has minimal external dependencies (standard tools only)
- It's lightweight enough to bundle with every install

If your skill has heavy external dependencies (GPU, large models, niche APIs)
or niche use cases (blockchain, bioinformatics), add it to `optional-skills/`
instead — users install those explicitly via `hermes skills install`.

## Related

- `optional-skills/` — heavier/niche skills installed on demand
- `hermes_cli/skills_hub.py` — skill installation and management
- Website docs: https://hermes-agent.nousresearch.com/docs
