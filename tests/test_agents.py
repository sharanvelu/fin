"""Tests for agent-instruction generation (`fincli.agents` + `fin agents`)."""

from __future__ import annotations

import os

import pytest

from fincli.agents import DEFAULT_TARGETS, TARGETS, build_content, install_files
from fincli.agents.installer import BEGIN_MARK, END_MARK, merge_managed
from fincli.app import EXIT_OK, EXIT_USER
from fincli.commands.agents_cmd import agents
from fincli.config import Config
from fincli.core.env import ProjectEnv

COMMANDS_BODY = '''
    def commands(self):
        def _run(ctx, args):
            return 0

        return {
            "composer": PlugCommand(
                name="composer", handler=_run,
                help="Run Composer inside the app container.",
            ),
            "artisan": PlugCommand(
                name="artisan", handler=_run,
                help="Run php artisan inside the app container.",
            ),
        }
'''


@pytest.fixture
def project(tmp_path, monkeypatch, plug_factory):
    """A Fin project dir with a demo APP plug providing composer/artisan."""
    plugs_dir = tmp_path / "plugs"
    plug_factory(
        plugs_dir,
        type_sub="App",
        name="demo",
        class_name="DemoPlug",
        plug_type="APP",
        body_extra=COMMANDS_BODY,
    )
    monkeypatch.setattr(Config, "PLUGS_DIR", plugs_dir)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".env").write_text("FIN_APP=demo\nFIN_SITE=demo.dockr.site\n")
    # Real FIN_*/DB_*/REDIS_* process env would leak into ProjectEnv.load().
    for key in list(os.environ):
        if key.startswith(("FIN_", "DB_", "REDIS_")):
            monkeypatch.delenv(key)
    return proj


# --------------------------------------------------------------------------- #
# Content generation
# --------------------------------------------------------------------------- #
def test_build_content_collects_plug_commands(project):
    content = build_content(ProjectEnv.load(cwd=project))
    names = [d.name for d in content.commands]
    assert names == ["composer", "artisan"]
    assert "`fin composer …`" in content.body
    assert "Run Composer inside the app container." in content.body
    # Host-equivalent example rows appear only for commands the plug provides.
    assert "`composer install` | `fin composer install`" in content.body
    assert "npm install" not in content.body
    # Core reserved commands are documented from the live registry.
    assert "fin up" in content.body
    assert "composer, artisan" in content.description


def test_body_documents_detection_and_up_workflow(project):
    content = build_content(ProjectEnv.load(cwd=project))
    # Detection: FIN_* in .env, FIN_APP/FIN_PLUG identifies the plug.
    assert "`FIN_*`" in content.body
    assert "`FIN_APP` (alias `FIN_PLUG`)" in content.body
    # Recovery: check with `fin ps`, start with `fin up` and wait, then run.
    assert "run `fin ps`" in content.body
    assert "run `fin up` and wait for it to complete" in content.body.replace("\n", " ")
    assert "FIN_*" in content.description and "'fin up' first" in content.description


def test_build_content_without_app_plug(project):
    (project / ".env").write_text("FIN_SITE=demo.dockr.site\n")
    content = build_content(ProjectEnv.load(cwd=project))
    assert content.commands == []
    assert "Instead of host commands" not in content.body
    assert "fin exec" in content.body  # generic fallback still documented


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def test_claude_skill_render(project):
    content = build_content(ProjectEnv.load(cwd=project))
    [gf] = TARGETS["claude"].render(content)
    assert gf.path == ".claude/skills/fin-commands/SKILL.md"
    assert not gf.managed_block
    assert gf.content.startswith("---\nname: fin-commands\n")
    assert "allowed-tools: Bash(fin:*)" in gf.content
    assert "`fin composer install`" in gf.content


def test_cursor_rule_render(project):
    content = build_content(ProjectEnv.load(cwd=project))
    [gf] = TARGETS["cursor"].render(content)
    assert gf.path == ".cursor/rules/fin-commands.mdc"
    assert "alwaysApply: true" in gf.content


def test_shared_files_are_managed_blocks(project):
    content = build_content(ProjectEnv.load(cwd=project))
    for name in ("codex", "copilot", "gemini"):
        [gf] = TARGETS[name].render(content)
        assert gf.managed_block, name


def test_agents_md_native_tools_share_one_file(project):
    content = build_content(ProjectEnv.load(cwd=project))
    for name in ("codex", "opencode", "kilocode", "kimi", "antigravity", "copilot-cli"):
        [gf] = TARGETS[name].render(content)
        assert gf.path == "AGENTS.md", name
        assert gf.managed_block, name


def test_codebuddy_rule_render(project):
    content = build_content(ProjectEnv.load(cwd=project))
    [gf] = TARGETS["codebuddy"].render(content)
    assert gf.path == ".codebuddy/rules/fin-commands.md"
    assert not gf.managed_block
    assert gf.content.startswith("---\nenabled: true\nalwaysApply: true\n---\n")


def test_aider_renders_conventions_and_conf(project):
    content = build_content(ProjectEnv.load(cwd=project))
    conventions, conf = TARGETS["aider"].render(content)
    assert conventions.path == "CONVENTIONS.md"
    assert conventions.managed_block
    assert conf.path == ".aider.conf.yml"
    assert conf.create_only
    assert "read: CONVENTIONS.md" in conf.content


# --------------------------------------------------------------------------- #
# Installer / managed-block merging
# --------------------------------------------------------------------------- #
def test_install_creates_files_then_reports_unchanged(project):
    content = build_content(ProjectEnv.load(cwd=project))
    files = [gf for n in DEFAULT_TARGETS for gf in TARGETS[n].render(content)]

    first = install_files(project, files)
    assert [action for _, action in first] == ["created"] * len(files)
    assert (project / ".claude/skills/fin-commands/SKILL.md").exists()
    agents_md = (project / "AGENTS.md").read_text()
    assert agents_md.startswith(BEGIN_MARK)
    assert END_MARK in agents_md

    second = install_files(project, files)
    assert [action for _, action in second] == ["unchanged"] * len(files)


def test_agents_md_merge_preserves_hand_written_content(project):
    (project / "AGENTS.md").write_text("# My notes\n\nKeep me.\n")
    content = build_content(ProjectEnv.load(cwd=project))
    install_files(project, TARGETS["codex"].render(content))

    text = (project / "AGENTS.md").read_text()
    assert text.startswith("# My notes")
    assert "Keep me." in text
    assert BEGIN_MARK in text and END_MARK in text


def test_merge_managed_replaces_only_the_block():
    existing = merge_managed("# Notes\n\ntop\n", "old body")
    existing += "\ntrailing hand-written text\n"
    merged = merge_managed(existing, "new body")
    assert "old body" not in merged
    assert "new body" in merged
    assert merged.startswith("# Notes")
    assert merged.rstrip().endswith("trailing hand-written text")
    assert merged.count(BEGIN_MARK) == 1 and merged.count(END_MARK) == 1


# --------------------------------------------------------------------------- #
# The reserved command
# --------------------------------------------------------------------------- #
def test_agents_install_defaults(project, monkeypatch):
    monkeypatch.chdir(project)
    assert agents(["install"]) == EXIT_OK
    assert (project / ".claude/skills/fin-commands/SKILL.md").exists()
    assert (project / ".cursor/rules/fin-commands.mdc").exists()
    assert (project / "AGENTS.md").exists()
    assert not (project / ".github/copilot-instructions.md").exists()


def test_agents_install_all_includes_copilot(project, monkeypatch):
    monkeypatch.chdir(project)
    assert agents(["install", "all"]) == EXIT_OK
    assert (project / ".github/copilot-instructions.md").exists()
    assert (project / "GEMINI.md").exists()
    assert (project / ".codebuddy/rules/fin-commands.md").exists()
    assert (project / "CONVENTIONS.md").exists()
    assert (project / ".aider.conf.yml").exists()


def test_agents_install_dedupes_shared_agents_md(project, monkeypatch):
    monkeypatch.chdir(project)
    assert agents(["install", "codex", "opencode", "kimi", "antigravity"]) == EXIT_OK
    text = (project / "AGENTS.md").read_text()
    assert text.count(BEGIN_MARK) == 1 and text.count(END_MARK) == 1


def test_agents_install_aider_never_touches_existing_conf(project, monkeypatch):
    monkeypatch.chdir(project)
    (project / ".aider.conf.yml").write_text("model: gpt-5\n")
    assert agents(["install", "aider"]) == EXIT_OK
    assert (project / "CONVENTIONS.md").exists()
    assert (project / ".aider.conf.yml").read_text() == "model: gpt-5\n"


def test_agents_install_rejects_unknown_agent(project, monkeypatch):
    monkeypatch.chdir(project)
    assert agents(["install", "nope"]) == EXIT_USER


def test_agents_install_requires_fin_project(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    for key in list(os.environ):
        if key.startswith(("FIN_", "DB_", "REDIS_")):
            monkeypatch.delenv(key)
    assert agents(["install"]) == EXIT_USER
    assert list(empty.iterdir()) == []


def test_agents_list_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert agents([]) == EXIT_OK
    assert agents(["bogus"]) == EXIT_USER
