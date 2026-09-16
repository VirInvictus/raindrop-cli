"""Token and configuration resolution.

Resolution order for the access token (first hit wins):

1. ``RAINDROP_TOKEN`` environment variable.
2. ``RAINDROP_TEST_TOKEN`` environment variable (back-compat alias).
3. ``token`` key in ``$XDG_CONFIG_HOME/raindrop-cli/config.toml``.
4. ``RAINDROP_TOKEN`` / ``RAINDROP_TEST_TOKEN`` in a ``.env`` file, searched in
   the current directory, then ``$XDG_CONFIG_HOME/raindrop-cli/.env``, then the
   pre-rename ``rd-cli`` directory's ``.env``.

The ``.env`` reader is a deliberately tiny stdlib parser so we carry no
``python-dotenv`` dependency. It only loads keys that are not already in the
environment, matching python-dotenv's default and keeping real env vars
authoritative.

The package was named ``rd-cli`` until the September 2026 rename, and the
rename shipped without migrating anyone's config, so the old
``$XDG_CONFIG_HOME/rd-cli/config.toml`` stays a read fallback: when the
current path has no config yet, the legacy one is read. Writes always go to
the current path, and because the writer preserves every key it read, the
first ``rd config set-*`` repatriates the legacy file wholesale.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from .errors import ConfigError

ENV_VARS = ("RAINDROP_TOKEN", "RAINDROP_TEST_TOKEN")
PINBOARD_ENV_VARS = ("PINBOARD_TOKEN", "PINBOARD_API_TOKEN")

# Keys this process has loaded from a .env file, mapped to the exact value
# injected. Module-level on purpose: `rd sync` resolves the Raindrop and
# Pinboard tokens in one process, and a per-call registry let the second
# resolver mistake the first call's injections for real environment
# variables, so a stale ./.env token beat `rd config set-pinboard-token`.
_injected: dict[str, str] = {}


def _config_root() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) if base else Path.home() / ".config"


def config_dir() -> Path:
    """Return the raindrop-cli config directory (respects ``XDG_CONFIG_HOME``)."""
    return _config_root() / "raindrop-cli"


def config_path() -> Path:
    """Path to ``config.toml`` (may not exist)."""
    return config_dir() / "config.toml"


def legacy_config_dir() -> Path:
    """The pre-rename ``rd-cli`` config directory (read-only fallback)."""
    return _config_root() / "rd-cli"


def legacy_config_path() -> Path:
    """Path to the pre-rename ``config.toml`` (may not exist)."""
    return legacy_config_dir() / "config.toml"


def effective_config_path() -> Path:
    """The config file in effect: the current path when it exists, else the
    pre-rename path when that one does (the fallback read), else the current
    path (where ``rd config set-*`` writes)."""
    current = config_path()
    if current.is_file():
        return current
    legacy = legacy_config_path()
    return legacy if legacy.is_file() else current


def parse_env(text: str) -> dict[str, str]:
    """Parse ``.env`` text into a dict. Supports ``KEY=value``, ``export KEY=v``,
    ``#`` comments, blank lines, and single/double quoted values."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def env_file_in_effect(paths: list[Path] | None = None) -> Path | None:
    """The first ``.env`` candidate that exists: the file ``load_env_files``
    reads, and the one a token may be riding in on."""
    if paths is None:
        paths = [
            Path.cwd() / ".env",
            config_dir() / ".env",
            legacy_config_dir() / ".env",
        ]
    return next((p for p in paths if p.is_file()), None)


def load_env_files(paths: list[Path] | None = None) -> dict[str, str]:
    """Load the first existing ``.env`` file into ``os.environ`` (non-clobbering).

    Returns the keys this call injected. They are also recorded in the
    module-level ``_injected`` registry, so every resolver later in the same
    process can still tell ``.env``-sourced values from real environment
    variables; the documented resolution order (env, config.toml, .env) needs
    that distinction.
    """
    if paths is None:
        paths = [
            Path.cwd() / ".env",
            config_dir() / ".env",
            legacy_config_dir() / ".env",
        ]
    injected: dict[str, str] = {}
    path = env_file_in_effect(paths)
    if path is None:
        return injected
    for key, value in parse_env(path.read_text(encoding="utf-8")).items():
        if key not in os.environ:
            os.environ[key] = value
            injected[key] = value
            _injected[key] = value
    return injected


def read_config() -> dict:
    """Read ``config.toml`` as a dict; empty dict if it does not exist.

    Falls back to the pre-rename ``rd-cli`` directory when the current one has
    no config yet, so installs that predate the rename keep working.
    """
    for path in (config_path(), legacy_config_path()):
        if not path.is_file():
            continue
        try:
            with path.open("rb") as fh:
                return tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"Could not read {path}: {exc}") from exc
    return {}


def _locate_secret(
    env_vars: list[str], config_value: object
) -> tuple[str | None, dict]:
    """The documented precedence walk, paired with the tier it resolved from.

    The tier names where a token came from (and which env var) without ever
    carrying the value, which is what ``rd config check`` reports.

    A variable holding the exact value a ``.env`` file injected (per the
    module-level registry) skips the env round and only wins when config has
    nothing; a real environment variable still beats everything.
    """
    for var in env_vars:
        token = os.environ.get(var)
        if token and _injected.get(var) != token:
            return token, {"tier": "environment", "var": var}
    if isinstance(config_value, str) and config_value.strip():
        return config_value, {"tier": "config.toml"}
    for var in env_vars:
        token = os.environ.get(var)
        if token and _injected.get(var) == token:
            return token, {"tier": ".env", "var": var}
    return None, {"tier": None}


def _resolve_secret(env_vars: list[str], config_value: object) -> str | None:
    """Documented precedence: env var, then config.toml, then ``.env``."""
    return _locate_secret(env_vars, config_value)[0]


def locate_token(kind: str) -> tuple[str | None, dict]:
    """Resolve the Raindrop (``kind="raindrop"``) or Pinboard (``"pinboard"``)
    token, returning it paired with the tier it came from. Call
    :func:`load_env_files` first so ``.env`` values are visible. The tier
    never carries the value; that is the point of ``rd config check``."""
    if kind == "raindrop":
        return _locate_secret(ENV_VARS, read_config().get("token"))
    if kind == "pinboard":
        return _locate_secret(PINBOARD_ENV_VARS, read_config().get("pinboard_token"))
    raise ValueError(f"unknown token kind: {kind!r}")


def resolve_token() -> str:
    """Resolve the access token, or raise :class:`ConfigError` if none is found.

    Precedence is the documented one: environment variable, then
    ``config.toml``, then ``.env``. A ``.env`` value therefore loses to
    ``rd config set-token``, so rotating the token is never silently
    overridden by a stale ``.env``.
    """
    load_env_files()
    token = _resolve_secret(ENV_VARS, read_config().get("token"))
    if token:
        return token.strip()
    raise ConfigError(
        "No Raindrop token found. Set RAINDROP_TOKEN, add it to "
        f"{config_path()} via `rd config set-token <token>`, or put it in a "
        ".env file. Get a test token at "
        "https://app.raindrop.io/settings/integrations"
    )


def resolve_pinboard_token() -> str:
    """Resolve the Pinboard API token (format ``user:HEX``), or raise.

    Same precedence as :func:`resolve_token` but for the ``PINBOARD_TOKEN`` /
    ``PINBOARD_API_TOKEN`` env vars and the ``pinboard_token`` config key.
    """
    load_env_files()
    token = _resolve_secret(PINBOARD_ENV_VARS, read_config().get("pinboard_token"))
    if token:
        return token.strip()
    raise ConfigError(
        "No Pinboard token found. Set PINBOARD_TOKEN, add it to "
        f"{config_path()} via `rd config set-pinboard-token <token>`, or put it "
        "in a .env file. Your token (format user:HEX) is at "
        "https://pinboard.in/settings/password"
    )


def write_token(token: str) -> Path:
    """Persist the Raindrop ``token`` to ``config.toml`` (0600), keeping others."""
    return _write_config_key("token", token)


def write_pinboard_token(token: str) -> Path:
    """Persist ``pinboard_token`` to ``config.toml`` (0600), keeping others."""
    return _write_config_key("pinboard_token", token)


def _write_config_key(key: str, value: str) -> Path:
    """Set one string key in ``config.toml`` (0600), preserving every other key.
    The written key is emitted first; order is cosmetic."""
    value = value.strip()
    if not value:
        raise ConfigError(f"Refusing to write an empty {key}.")
    data = read_config()
    data[key] = value
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_toml_line(key, value)]
    for other, val in data.items():
        if other == key:
            continue
        lines.append(_toml_line(other, val))
    # Atomic write: a crash mid-write must not truncate the config (the API
    # tokens live here). chmod the temp before the swap so the file is never
    # readable by anyone else, even for a moment.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp, path)
    return path


def _toml_line(key: str, value: object) -> str:
    if isinstance(value, bool):
        return f"{key} = {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"{key} = {value}"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'{key} = "{escaped}"'
