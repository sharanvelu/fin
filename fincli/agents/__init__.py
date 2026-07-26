"""Agent-instruction generation — teach AI coding agents to use ``fin``.

Fin projects run their app inside containers, so AI coding agents working in
the repo must run project commands through ``fin`` (``fin composer install``,
not ``composer install``). This package generates per-agent instruction files
(a Claude Code skill, a Cursor rule, the cross-agent ``AGENTS.md`` block, …)
from one canonical markdown body, tailored to the project's installed plugs:
the command tables come from each plug's ``commands()`` metadata, so a Laravel
project documents artisan/composer while a Django project documents manage.

Only this package (and the ``agents`` reserved command) knows about agent file
layouts. Plugs stay declarative and contribute nothing agent-specific.
"""

from __future__ import annotations

from fincli.agents.content import AgentContent, CommandDoc, build_content, project_commands
from fincli.agents.installer import install_files, merge_managed
from fincli.agents.targets import DEFAULT_TARGETS, TARGETS, AgentTarget, GeneratedFile

__all__ = [
    "AgentContent",
    "AgentTarget",
    "CommandDoc",
    "DEFAULT_TARGETS",
    "GeneratedFile",
    "TARGETS",
    "build_content",
    "install_files",
    "merge_managed",
    "project_commands",
]
