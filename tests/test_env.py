"""Tests for fincli.core.env — .env parsing, ProjectEnv, EnvVar/EnvSpec, as_bool."""

from __future__ import annotations

import pytest

from fincli.core.env import (
    EnvSpec,
    EnvVar,
    ProjectEnv,
    as_bool,
    parse_env_file,
)
from fincli.core.errors import FinError


# --------------------------------------------------------------------------- #
# parse_env_file
# --------------------------------------------------------------------------- #
def test_parse_env_file_missing_returns_empty(tmp_path):
    assert parse_env_file(tmp_path / "nope.env") == {}


def test_parse_env_file_basic_pairs(tmp_path):
    p = tmp_path / ".env"
    p.write_text("FIN_SITE=app.localhost\nDB_DATABASE=mydb\n")
    parsed = parse_env_file(p)
    assert parsed == {"FIN_SITE": "app.localhost", "DB_DATABASE": "mydb"}


def test_parse_env_file_comments_blank_and_export(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# a comment\n\n   \nexport FIN_APP=laravel\nFIN_PLUGS=mysql,redis\n")
    parsed = parse_env_file(p)
    assert parsed == {"FIN_APP": "laravel", "FIN_PLUGS": "mysql,redis"}


def test_parse_env_file_strips_matching_quotes(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        'A="double"\n'
        "B='single'\n"
        "C=\"mismatch'\n"  # not matching → kept verbatim
        "D=no_quotes\n"
        'E=""\n'  # empty quoted → empty string
    )
    parsed = parse_env_file(p)
    assert parsed["A"] == "double"
    assert parsed["B"] == "single"
    assert parsed["C"] == "\"mismatch'"
    assert parsed["D"] == "no_quotes"
    assert parsed["E"] == ""


def test_parse_env_file_value_with_equals(tmp_path):
    p = tmp_path / ".env"
    p.write_text("URL=postgres://u:p@host:5432/db?x=1\n")
    parsed = parse_env_file(p)
    assert parsed["URL"] == "postgres://u:p@host:5432/db?x=1"


def test_parse_env_file_line_without_equals_skipped(tmp_path):
    p = tmp_path / ".env"
    p.write_text("JUSTAKEY\nFIN_SITE=ok\n")
    parsed = parse_env_file(p)
    assert parsed == {"FIN_SITE": "ok"}


def test_parse_env_file_empty_key_skipped(tmp_path):
    p = tmp_path / ".env"
    p.write_text("=value\n")
    assert parse_env_file(p) == {}


# --------------------------------------------------------------------------- #
# ProjectEnv.load + os.environ precedence + FIN_/DB_/REDIS_ extraction
# --------------------------------------------------------------------------- #
def test_load_reads_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("FIN_SITE=app.localhost\n")
    # Ensure no stray FIN_/DB_/REDIS_ env vars from the host interfere.
    for k in list(__import__("os").environ):
        if k.startswith(("FIN_", "DB_", "REDIS_")):
            monkeypatch.delenv(k, raising=False)
    env = ProjectEnv.load(cwd=tmp_path)
    assert env.cwd == tmp_path.resolve()
    assert env.get("FIN_SITE") == "app.localhost"


def test_load_os_environ_overrides_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("FIN_SITE=fromfile.localhost\n")
    monkeypatch.setenv("FIN_SITE", "fromenv.localhost")
    env = ProjectEnv.load(cwd=tmp_path)
    assert env.get("FIN_SITE") == "fromenv.localhost"


def test_load_only_extracts_prefixed_env_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("FIN_APP", "laravel")
    monkeypatch.setenv("DB_DATABASE", "mydb")
    monkeypatch.setenv("REDIS_HOST", "redis")
    monkeypatch.setenv("UNRELATED_VAR", "nope")
    env = ProjectEnv.load(cwd=tmp_path)
    assert env.get("FIN_APP") == "laravel"
    assert env.get("DB_DATABASE") == "mydb"
    assert env.get("REDIS_HOST") == "redis"
    assert env.get("UNRELATED_VAR") is None


# --------------------------------------------------------------------------- #
# accessors: get / require / fin_vars
# --------------------------------------------------------------------------- #
def test_get_default():
    env = ProjectEnv(cwd=__import__("pathlib").Path("/tmp"), values={})
    assert env.get("MISSING", "fallback") == "fallback"
    assert env.get("MISSING") is None


def test_require_returns_value():
    env = ProjectEnv(cwd=__import__("pathlib").Path("/tmp"), values={"FIN_SITE": "x"})
    assert env.require("FIN_SITE") == "x"


def test_require_raises_on_missing():
    env = ProjectEnv(cwd=__import__("pathlib").Path("/tmp"), values={})
    with pytest.raises(FinError):
        env.require("FIN_SITE")


def test_require_raises_on_empty_string():
    env = ProjectEnv(cwd=__import__("pathlib").Path("/tmp"), values={"FIN_SITE": ""})
    with pytest.raises(FinError):
        env.require("FIN_SITE")


def test_fin_vars_filters_prefix():
    env = ProjectEnv(
        cwd=__import__("pathlib").Path("/tmp"),
        values={"FIN_SITE": "x", "FIN_APP": "laravel", "DB_DATABASE": "db"},
    )
    assert env.fin_vars() == {"FIN_SITE": "x", "FIN_APP": "laravel"}


# --------------------------------------------------------------------------- #
# project_name
# --------------------------------------------------------------------------- #
def test_project_name_from_cwd_basename(tmp_path):
    d = tmp_path / "My Project"
    d.mkdir()
    env = ProjectEnv(cwd=d, values={})
    assert env.project_name == "my-project"


def test_project_name_override(tmp_path):
    env = ProjectEnv(cwd=tmp_path, values={"FIN_CONTAINER_NAME": "Custom Name"})
    assert env.project_name == "custom-name"


# --------------------------------------------------------------------------- #
# plugs / app_plug
# --------------------------------------------------------------------------- #
def test_plugs_parsing_and_whitespace():
    env = ProjectEnv(
        cwd=__import__("pathlib").Path("/x"), values={"FIN_PLUGS": " mysql , redis ,, "}
    )
    assert env.plugs == ["mysql", "redis"]


def test_plugs_empty():
    env = ProjectEnv(cwd=__import__("pathlib").Path("/x"), values={})
    assert env.plugs == []


def test_app_plug_prefers_fin_app():
    env = ProjectEnv(
        cwd=__import__("pathlib").Path("/x"),
        values={"FIN_APP": "laravel", "FIN_PLUG": "other"},
    )
    assert env.app_plug == "laravel"


def test_app_plug_falls_back_to_fin_plug():
    env = ProjectEnv(
        cwd=__import__("pathlib").Path("/x"), values={"FIN_PLUG": "django"}
    )
    assert env.app_plug == "django"


def test_app_plug_none():
    env = ProjectEnv(cwd=__import__("pathlib").Path("/x"), values={})
    assert env.app_plug is None


def test_additional_hosts_parsing_and_whitespace():
    env = ProjectEnv(
        cwd=__import__("pathlib").Path("/x"),
        values={"FIN_ADDITIONAL_HOSTS": " app2.localhost , app3.test ,, "},
    )
    assert env.additional_hosts == ["app2.localhost", "app3.test"]


def test_additional_hosts_empty():
    env = ProjectEnv(cwd=__import__("pathlib").Path("/x"), values={})
    assert env.additional_hosts == []


# --------------------------------------------------------------------------- #
# as_bool
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", " on "])
def test_as_bool_truthy(raw):
    assert as_bool(raw) is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "anything", ""])
def test_as_bool_falsey(raw):
    assert as_bool(raw) is False


def test_as_bool_none_uses_default():
    assert as_bool(None) is False
    assert as_bool(None, default=True) is True


# --------------------------------------------------------------------------- #
# EnvVar.check
# --------------------------------------------------------------------------- #
def test_envvar_required_missing():
    v = EnvVar("FIN_SITE", required=True, description="the host")
    err = v.check(None)
    assert err is not None and "FIN_SITE" in err and "required" in err
    assert "the host" in err


def test_envvar_required_empty():
    v = EnvVar("FIN_SITE", required=True)
    assert v.check("") is not None


def test_envvar_optional_missing_ok():
    v = EnvVar("FIN_X", required=False)
    assert v.check(None) is None


def test_envvar_choices_valid():
    v = EnvVar("FIN_COMPOSER_VERSION", choices=("1", "2"))
    assert v.check("2") is None


def test_envvar_choices_invalid():
    v = EnvVar("FIN_COMPOSER_VERSION", choices=("1", "2"))
    err = v.check("3")
    assert err is not None and "invalid" in err and "1, 2" in err


def test_envvar_int_valid():
    v = EnvVar("FIN_PORT", value_type=int)
    assert v.check("8080") is None


def test_envvar_int_invalid():
    v = EnvVar("FIN_PORT", value_type=int)
    err = v.check("notanint")
    assert err is not None and "integer" in err


def test_envvar_bool_valid():
    v = EnvVar("FIN_FLAG", value_type=bool)
    assert v.check("true") is None
    assert v.check("0") is None


def test_envvar_bool_invalid():
    v = EnvVar("FIN_FLAG", value_type=bool)
    err = v.check("maybe")
    assert err is not None and "boolean" in err


# --------------------------------------------------------------------------- #
# EnvSpec.validate / resolved
# --------------------------------------------------------------------------- #
def test_envspec_validate_collects_all_problems():
    spec = EnvSpec.of(
        [
            EnvVar("FIN_SITE", required=True),
            EnvVar("FIN_COMPOSER_VERSION", choices=("1", "2")),
            EnvVar("FIN_PORT", value_type=int),
        ]
    )
    with pytest.raises(FinError) as exc:
        spec.validate({"FIN_COMPOSER_VERSION": "3", "FIN_PORT": "abc"})
    msg = exc.value.message
    assert "FIN_SITE" in msg
    assert "FIN_COMPOSER_VERSION" in msg
    assert "FIN_PORT" in msg
    assert exc.value.title == "Invalid Configuration"


def test_envspec_validate_ok_no_raise():
    spec = EnvSpec.of([EnvVar("FIN_SITE", required=True)])
    spec.validate({"FIN_SITE": "app.localhost"})  # no exception


def test_envspec_validate_accepts_projectenv():
    spec = EnvSpec.of([EnvVar("FIN_SITE", required=True)])
    env = ProjectEnv(cwd=__import__("pathlib").Path("/x"), values={"FIN_SITE": "ok"})
    spec.validate(env)  # no raise


def test_envspec_resolved_applies_defaults():
    spec = EnvSpec.of(
        [
            EnvVar("FIN_PHP_VERSION", default="latest"),
            EnvVar("FIN_COMPOSER_VERSION", default="2"),
            EnvVar("FIN_SITE", required=True),
        ]
    )
    out = spec.resolved({"FIN_SITE": "app.localhost"})
    assert out["FIN_PHP_VERSION"] == "latest"
    assert out["FIN_COMPOSER_VERSION"] == "2"
    assert out["FIN_SITE"] == "app.localhost"


def test_envspec_resolved_existing_value_wins_over_default():
    spec = EnvSpec.of([EnvVar("FIN_PHP_VERSION", default="latest")])
    out = spec.resolved({"FIN_PHP_VERSION": "8.3"})
    assert out["FIN_PHP_VERSION"] == "8.3"


def test_envspec_resolved_omits_unset_without_default():
    spec = EnvSpec.of([EnvVar("FIN_OPTIONAL")])
    out = spec.resolved({})
    assert "FIN_OPTIONAL" not in out


def test_envspec_add_chaining():
    spec = EnvSpec().add(EnvVar("A")).add(EnvVar("B"), EnvVar("C"))
    assert [v.name for v in spec.variables] == ["A", "B", "C"]
