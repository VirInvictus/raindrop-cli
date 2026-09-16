from __future__ import annotations

import os
import stat

import pytest

from rd_cli import config
from rd_cli.errors import ConfigError


def test_parse_env_handles_comments_quotes_and_export():
    text = (
        "# a comment\n"
        "\n"
        "RAINDROP_TOKEN=plain\n"
        'export QUOTED="with spaces"\n'
        "SINGLE='sq'\n"
        "NOEQ line without equals\n"
    )
    parsed = config.parse_env(text)
    assert parsed == {
        "RAINDROP_TOKEN": "plain",
        "QUOTED": "with spaces",
        "SINGLE": "sq",
    }


def test_resolve_token_prefers_primary_env(monkeypatch):
    monkeypatch.setenv("RAINDROP_TOKEN", "primary")
    monkeypatch.setenv("RAINDROP_TEST_TOKEN", "alias")
    assert config.resolve_token() == "primary"


def test_resolve_token_falls_back_to_alias(monkeypatch):
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    monkeypatch.setenv("RAINDROP_TEST_TOKEN", "alias")
    assert config.resolve_token() == "alias"


def test_resolve_token_reads_config_file(monkeypatch, tmp_path):
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    monkeypatch.delenv("RAINDROP_TEST_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # avoid picking up a stray ./.env
    cfg_dir = tmp_path / "raindrop-cli"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('token = "from-file"\n')
    assert config.resolve_token() == "from-file"


def test_resolve_token_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    monkeypatch.delenv("RAINDROP_TEST_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        config.resolve_token()


def test_resolve_token_config_beats_dotenv(monkeypatch, tmp_path):
    # The documented order is env, config.toml, .env: rotating the token
    # via `rd config set-token` must win over a stale ./.env.
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    monkeypatch.delenv("RAINDROP_TEST_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("RAINDROP_TOKEN=stale\n")
    cfg_dir = tmp_path / "raindrop-cli"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('token = "rotated"\n')
    assert config.resolve_token() == "rotated"


def test_resolve_token_dotenv_still_works_without_config(monkeypatch, tmp_path):
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    monkeypatch.delenv("RAINDROP_TEST_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("RAINDROP_TOKEN=fromfile\n")
    assert config.resolve_token() == "fromfile"


def test_resolve_pinboard_token_config_beats_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("PINBOARD_TOKEN", raising=False)
    monkeypatch.delenv("PINBOARD_API_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PINBOARD_TOKEN=stale:OLD\n")
    cfg_dir = tmp_path / "raindrop-cli"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('pinboard_token = "fresh:NEW"\n')
    assert config.resolve_pinboard_token() == "fresh:NEW"


def test_dual_token_resolution_config_beats_dotenv_for_both(monkeypatch, tmp_path):
    # cmd_sync resolves both tokens in ONE process. The 0.6.0 regression: the
    # first resolver's load_env_files injected PINBOARD_TOKEN into os.environ,
    # and the second resolver then took it for a real env var, so a stale
    # ./.env beat `rd config set-pinboard-token`. The injected-keys registry
    # must persist across the two calls in both orders.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("RAINDROP_TOKEN=stale-rd\nPINBOARD_TOKEN=stale:PB\n")
    cfg_dir = tmp_path / "raindrop-cli"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        'token = "fresh-rd"\npinboard_token = "fresh:PB"\n'
    )
    assert config.resolve_token() == "fresh-rd"
    assert config.resolve_pinboard_token() == "fresh:PB"
    # And the other resolution order (a fresh process where sync resolves the
    # Pinboard token first): scrub the injections and the registry together,
    # which is exactly the state a fresh interpreter starts in. The pops are
    # deliberately untracked (the values were injected untracked too); the
    # autouse fixture guarantees they cannot leak past this test.
    monkeypatch.setattr(config, "_injected", {})
    for var in (*config.ENV_VARS, *config.PINBOARD_ENV_VARS):
        os.environ.pop(var, None)
    assert config.resolve_pinboard_token() == "fresh:PB"
    assert config.resolve_token() == "fresh-rd"


def test_dotenv_still_feeds_both_resolvers_when_config_lacks_a_key(
    monkeypatch, tmp_path
):
    # The registry must only mask the env round, not the .env value itself:
    # config without a pinboard_token still resolves it from ./.env even after
    # the Raindrop resolver ran first in the same process.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PINBOARD_TOKEN=fromfile:PB\n")
    cfg_dir = tmp_path / "raindrop-cli"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('token = "rd-only"\n')
    assert config.resolve_token() == "rd-only"
    assert config.resolve_pinboard_token() == "fromfile:PB"


def test_env_file_does_not_clobber_real_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RAINDROP_TOKEN", "real")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("RAINDROP_TOKEN=fromfile\n")
    config.load_env_files()
    assert config.resolve_token() == "real"


def test_write_token_roundtrip_and_permissions(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = config.write_token("secret-token")
    assert path.exists()
    assert config.read_config()["token"] == "secret-token"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_write_token_rejects_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(ConfigError):
        config.write_token("   ")


def test_pinboard_token_resolution_and_coexistence(monkeypatch, tmp_path):
    # Both tokens live in one config.toml; writing one must not drop the other.
    monkeypatch.delenv("PINBOARD_TOKEN", raising=False)
    monkeypatch.delenv("PINBOARD_API_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config.write_token("raindrop-tok")
    config.write_pinboard_token("user:HEX")
    data = config.read_config()
    assert data["token"] == "raindrop-tok"
    assert data["pinboard_token"] == "user:HEX"
    assert config.resolve_pinboard_token() == "user:HEX"


def test_pinboard_token_prefers_env(monkeypatch):
    monkeypatch.setenv("PINBOARD_TOKEN", "env:TOK")
    assert config.resolve_pinboard_token() == "env:TOK"


def test_config_show_masks_both_tokens(monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace

    from rd_cli import commands, output

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.write_token("raindrop-secret-abcdef")
    config.write_pinboard_token("user:PINBOARDSECRETXYZ")
    output.configure(no_color=True)
    commands.cfg_show(None, SimpleNamespace(json=False))
    out = capsys.readouterr().out
    assert "raindrop-secret-abcdef" not in out
    assert "PINBOARDSECRETXYZ" not in out
    assert "…" in out  # both rendered through the mask


def test_pinboard_token_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("PINBOARD_TOKEN", raising=False)
    monkeypatch.delenv("PINBOARD_API_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        config.resolve_pinboard_token()


def test_write_config_escapes_quotes_and_backslashes(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config._write_config_key("pinboard_token", 'has "quote" and \\ back')
    text = (tmp_path / "raindrop-cli" / "config.toml").read_text()
    import tomllib

    parsed = tomllib.loads(text)
    assert parsed["pinboard_token"] == 'has "quote" and \\ back'


def test_write_config_is_atomic_and_private(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = config._write_config_key("pinboard_token", "TOK")
    # No temp file survives the swap, and the config is owner-only.
    assert not (path.parent / (path.name + ".tmp")).exists()
    assert (stat.S_IMODE(path.stat().st_mode) & 0o777) == 0o600


def test_write_config_skips_non_scalar_keys_with_warning(monkeypatch, tmp_path, capsys):
    # A hand-edited TOML table has no representation in the flat writer; it is
    # skipped with a warning instead of repr-flattened into a corrupt string.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # avoid picking up a stray ./.env
    cfg_dir = tmp_path / "raindrop-cli"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('token = "keep"\n[table]\nx = 1\n')
    path = config._write_config_key("pinboard_token", "TOK")
    err = capsys.readouterr().err
    assert "not a plain value" in err
    import tomllib

    parsed = tomllib.loads(path.read_text())
    assert parsed["pinboard_token"] == "TOK"
    assert parsed["token"] == "keep"
    assert "table" not in parsed


# -- pre-rename config directory (rd-cli -> raindrop-cli, no migration) --------


def test_legacy_config_dir_is_used_as_fallback(monkeypatch, tmp_path):
    # Installs from before the September 2026 rename keep their tokens in
    # rd-cli/; the rename shipped without a migration, so the old path stays
    # readable or the installed tool has no token source at all.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "rd-cli"
    legacy.mkdir()
    (legacy / "config.toml").write_text(
        'token = "legacy-rd"\npinboard_token = "legacy:PB"\n'
    )
    assert config.resolve_token() == "legacy-rd"
    assert config.resolve_pinboard_token() == "legacy:PB"
    assert config.effective_config_path() == legacy / "config.toml"


def test_current_config_beats_legacy(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rd-cli").mkdir()
    (tmp_path / "rd-cli" / "config.toml").write_text('token = "legacy-rd"\n')
    cfg_dir = tmp_path / "raindrop-cli"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('token = "current-rd"\n')
    assert config.resolve_token() == "current-rd"
    assert config.effective_config_path() == cfg_dir / "config.toml"


def test_legacy_dotenv_is_last_candidate(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "rd-cli"
    legacy.mkdir()
    (legacy / ".env").write_text("RAINDROP_TOKEN=legacy-env\n")
    assert config.resolve_token() == "legacy-env"


def test_write_repatriates_legacy_keys(monkeypatch, tmp_path):
    # The writer preserves every key it read, so the first set-* on a
    # legacy-only install copies the whole file to the current path.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "rd-cli"
    legacy.mkdir()
    (legacy / "config.toml").write_text('token = "legacy-rd"\n')
    path = config.write_pinboard_token("new:PB")
    assert path == tmp_path / "raindrop-cli" / "config.toml"
    data = config.read_config()
    assert data["token"] == "legacy-rd"
    assert data["pinboard_token"] == "new:PB"
    assert config.resolve_token() == "legacy-rd"


def test_no_config_anywhere_reports_current_path(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert config.read_config() == {}
    assert config.effective_config_path() == tmp_path / "raindrop-cli" / "config.toml"
