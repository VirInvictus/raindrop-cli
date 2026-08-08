from __future__ import annotations

import pytest

from rd_cli import cli


class StubClient:
    """Records method calls and returns canned data."""

    def __init__(self, **canned):
        self.canned = canned
        self.calls = []

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self.canned.get(name, {})

        return method


@pytest.fixture
def run(monkeypatch, capsys):
    """Run the CLI with a stubbed client and token, returning (exit, stdout, stub)."""

    def _run(argv, **canned):
        stub = StubClient(**canned)
        monkeypatch.setattr(cli.config, "resolve_token", lambda: "tok")
        monkeypatch.setattr(cli, "RaindropClient", lambda *a, **k: stub)
        code = cli.main(argv)
        out = capsys.readouterr()
        return code, out.out, stub

    return _run


# -- parsing ------------------------------------------------------------------


def test_no_args_prints_help_and_returns_zero(capsys):
    assert cli.main([]) == 0
    assert "usage: rd" in capsys.readouterr().out


def test_json_flag_works_after_subcommand(run):
    code, out, stub = run(["list", "--json"], get_raindrops={"items": [{"_id": 1}]})
    assert code == 0
    assert '"_id": 1' in out


def test_json_flag_works_before_subcommand(run):
    code, out, stub = run(["--json", "list"], get_raindrops={"items": [{"_id": 2}]})
    assert code == 0
    assert '"_id": 2' in out


# -- dispatch -----------------------------------------------------------------


def test_list_calls_get_raindrops(run):
    code, out, stub = run(
        ["list", "-c", "5", "-s", "python"],
        get_raindrops={"items": []},
    )
    assert code == 0
    name, args, kwargs = stub.calls[0]
    assert name == "get_raindrops"
    assert args[0] == 5
    assert kwargs["search"] == "python"


def test_list_all_uses_iterator(run):
    code, out, stub = run(["list", "--all"], iter_raindrops=[])
    assert stub.calls[0][0] == "iter_raindrops"


def test_add_passes_please_parse_by_default(run):
    code, out, stub = run(["add", "https://x.com"], create_raindrop={"_id": 9})
    name, args, kwargs = stub.calls[0]
    assert name == "create_raindrop"
    assert kwargs["please_parse"] is True


def test_add_no_parse_flag(run):
    code, out, stub = run(
        ["add", "https://x.com", "--no-parse"], create_raindrop={"_id": 9}
    )
    assert stub.calls[0][2]["please_parse"] is False


def test_edit_important_tristate(run):
    code, out, stub = run(["edit", "1", "--not-important"], update_raindrop={"_id": 1})
    assert stub.calls[0][2]["important"] is False


def test_rm_returns_nonzero_on_failure(run):
    code, out, stub = run(["rm", "1"], delete_raindrop=False)
    assert code == 1


def test_search_positional(run):
    code, out, stub = run(["search", "term"], get_raindrops={"items": []})
    assert stub.calls[0][2]["search"] == "term"


# -- grouped + aliases --------------------------------------------------------


def test_collections_tree_dispatch(run):
    code, out, stub = run(
        ["collections", "tree"], get_collections=[], get_child_collections=[]
    )
    names = [c[0] for c in stub.calls]
    assert "get_collections" in names
    assert "get_child_collections" in names


def test_backcompat_c_list_alias(run):
    code, out, stub = run(["c-list"], get_collections=[])
    assert stub.calls[0][0] == "get_collections"


def test_backcompat_t_list_alias(run):
    code, out, stub = run(["t-list"], get_tags=[])
    assert stub.calls[0][0] == "get_tags"


def test_backcompat_h_list_alias(run):
    code, out, stub = run(["h-list"], get_all_highlights=[])
    assert stub.calls[0][0] == "get_all_highlights"


def test_collections_short_alias(run):
    code, out, stub = run(["c", "list"], get_collections=[])
    assert stub.calls[0][0] == "get_collections"


# -- config (no client) -------------------------------------------------------


def test_config_set_token_needs_no_client(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def boom():
        raise AssertionError("resolve_token should not be called")

    monkeypatch.setattr(cli.config, "resolve_token", boom)
    code = cli.main(["config", "set-token", "abc123"])
    assert code == 0
    assert "saved" in capsys.readouterr().out


def test_config_path_no_client(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.config, "resolve_token", lambda: (_ for _ in ()).throw(AssertionError())
    )
    code = cli.main(["config", "path"])
    assert code == 0


# -- batch / bulk commands ----------------------------------------------------


def test_mv_id_mode_loops_single_updates(run):
    code, out, stub = run(["mv", "42", "1", "2", "3"], update_raindrop={"_id": 1})
    calls = [c for c in stub.calls if c[0] == "update_raindrop"]
    assert len(calls) == 3
    assert all(c[2]["collection_id"] == 42 for c in calls)


def test_mv_scope_mode_uses_batch(run):
    # -y because scope mode now confirms first; the count read precedes the write.
    code, out, stub = run(
        ["mv", "42", "--from", "5", "-y"],
        update_raindrops=2,
        get_raindrops={"count": 2, "items": []},
    )
    batch = [c for c in stub.calls if c[0] == "update_raindrops"][0]
    assert batch[1][0] == 5  # path scope = source
    assert batch[2]["move_to"] == 42


def test_mv_no_ids_no_scope_errors(run):
    code, out, stub = run(["mv", "42"])
    assert code == 1


def test_rm_multi_ids(run):
    code, out, stub = run(["rm", "1", "2", "3"], delete_raindrop=True)
    assert len([c for c in stub.calls if c[0] == "delete_raindrop"]) == 3


def test_rm_permanent_flag(run):
    code, out, stub = run(["rm", "1", "--permanent", "-y"], delete_raindrop=True)
    assert stub.calls[0][2]["permanent"] is True


def test_rm_scope_mode(run):
    code, out, stub = run(
        ["rm", "--from", "5", "-s", "x", "-y"],
        delete_raindrops=4,
        get_raindrops={"count": 4, "items": []},
    )
    batch = [c for c in stub.calls if c[0] == "delete_raindrops"][0]
    assert batch[1][0] == 5


# -- confirmation --------------------------------------------------------------


def test_rm_scope_aborts_without_confirmation(run):
    """A non-interactive stdin refuses rather than prompting, so nothing is written."""
    code, out, stub = run(
        ["rm", "--from", "5"],
        delete_raindrops=4,
        get_raindrops={"count": 4, "items": []},
    )
    assert code == 1
    assert not [c for c in stub.calls if c[0] == "delete_raindrops"]


def test_rm_permanent_aborts_without_confirmation(run):
    code, out, stub = run(["rm", "1", "--permanent"], delete_raindrop=True)
    assert code == 1
    assert not [c for c in stub.calls if c[0] == "delete_raindrop"]


def test_rm_to_trash_needs_no_confirmation(run):
    """Trash is recoverable, so the common case stays prompt-free."""
    code, out, stub = run(["rm", "1", "2"], delete_raindrop=True)
    assert code == 0
    assert len([c for c in stub.calls if c[0] == "delete_raindrop"]) == 2


def test_assume_yes_env_confirms(run, monkeypatch):
    monkeypatch.setenv("RD_ASSUME_YES", "1")
    code, out, stub = run(["rm", "1", "--permanent"], delete_raindrop=True)
    assert code == 0
    assert stub.calls[0][2]["permanent"] is True


def test_dry_run_skips_the_prompt(run):
    """--dry-run writes nothing, so interrogating the user first is pointless."""
    code, out, stub = run(
        ["rm", "--from", "5", "--dry-run"],
        delete_raindrops=0,
        get_raindrops={"count": 4, "items": []},
    )
    assert code == 0
    assert [c for c in stub.calls if c[0] == "delete_raindrops"]


def test_empty_trash_confirms(run):
    code, out, stub = run(["collections", "empty-trash"], empty_trash=True)
    assert code == 1
    assert not [c for c in stub.calls if c[0] == "empty_trash"]

    code, out, stub = run(["collections", "empty-trash", "-y"], empty_trash=True)
    assert code == 0
    assert [c for c in stub.calls if c[0] == "empty_trash"]


def test_tags_rm_confirms(run):
    code, out, stub = run(["tags", "rm", "junk"], delete_tags=True)
    assert code == 1
    assert not [c for c in stub.calls if c[0] == "delete_tags"]


def test_tag_scope_append_does_not_confirm(run):
    """Appending a tag is additive and reversible, so it stays unprompted."""
    code, out, stub = run(
        ["tag", "--from", "5", "--add", "x"],
        update_raindrops=3,
        get_raindrops={"count": 3, "items": []},
    )
    assert code == 0
    assert [c for c in stub.calls if c[0] == "update_raindrops"]


def test_tag_scope_clear_confirms(run):
    code, out, stub = run(
        ["tag", "--from", "5", "--clear"],
        update_raindrops=3,
        get_raindrops={"count": 3, "items": []},
    )
    assert code == 1
    assert not [c for c in stub.calls if c[0] == "update_raindrops"]


# -- open ----------------------------------------------------------------------


def test_open_launches_browser(run, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "rd_cli.commands.webbrowser.open", lambda url: opened.append(url) or True
    )
    code, out, stub = run(
        ["open", "7"], get_raindrop={"_id": 7, "link": "https://example.com/a"}
    )
    assert code == 0
    assert opened == ["https://example.com/a"]


def test_open_print_does_not_launch(run, monkeypatch):
    monkeypatch.setattr(
        "rd_cli.commands.webbrowser.open",
        lambda url: (_ for _ in ()).throw(AssertionError("should not launch")),
    )
    code, out, stub = run(
        ["open", "7", "--print"],
        get_raindrop={"_id": 7, "link": "https://example.com/a"},
    )
    assert code == 0
    assert out.strip() == "https://example.com/a"


def test_open_cache_uses_permanent_copy(run, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "rd_cli.commands.webbrowser.open", lambda url: opened.append(url) or True
    )
    code, out, stub = run(
        ["open", "7", "--cache"],
        get_raindrop={"_id": 7, "link": "https://example.com/a"},
        get_permanent_copy_url="https://s3.example/copy",
    )
    assert code == 0
    assert opened == ["https://s3.example/copy"]


def test_open_missing_permanent_copy_errors(run, monkeypatch):
    monkeypatch.setattr("rd_cli.commands.webbrowser.open", lambda url: True)
    code, out, stub = run(
        ["open", "7", "--cache"],
        get_raindrop={"_id": 7, "link": "https://example.com/a"},
        get_permanent_copy_url=None,
    )
    assert code == 1


def test_tag_add_id_mode_merges(run):
    code, out, stub = run(
        ["tag", "1", "--add", "new"],
        get_raindrop={"tags": ["existing"]},
        update_raindrop={},
    )
    upd = [c for c in stub.calls if c[0] == "update_raindrop"][0]
    assert set(upd[2]["tags"]) == {"existing", "new"}


def test_tag_remove_id_mode(run):
    code, out, stub = run(
        ["tag", "1", "--remove", "drop"],
        get_raindrop={"tags": ["keep", "drop"]},
        update_raindrop={},
    )
    upd = [c for c in stub.calls if c[0] == "update_raindrop"][0]
    assert upd[2]["tags"] == ["keep"]


def test_tag_scope_remove_is_rejected(run):
    code, out, stub = run(["tag", "--from", "5", "--remove", "x"])
    assert code == 1


def test_tag_nothing_to_do_errors(run):
    code, out, stub = run(["tag", "1"])
    assert code == 1


def test_add_many_from_file(run, tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("https://a.com\nhttps://b.com\n\n")
    code, out, stub = run(["add", "--file", str(f)], create_raindrops=[{"_id": 1}])
    assert stub.calls[0][0] == "create_raindrops"
    items = stub.calls[0][1][0]
    assert [i["link"] for i in items] == ["https://a.com", "https://b.com"]


def test_collections_reorder(run):
    code, out, stub = run(
        ["collections", "reorder", "--by=-count"], reorder_collections=True
    )
    assert stub.calls[0][0] == "reorder_collections"
    assert stub.calls[0][1][0] == "-count"


def test_user_bare_shows(run):
    code, out, stub = run(["user"], get_user={"fullName": "X"})
    assert stub.calls[0][0] == "get_user"


def test_user_set_updates(run):
    code, out, stub = run(
        ["user", "set", "--name", "New Name", "--config", "lang=en"],
        update_user={},
    )
    call = stub.calls[0]
    assert call[0] == "update_user"
    assert call[2]["fullName"] == "New Name"
    assert call[2]["config"] == {"lang": "en"}


def test_dry_run_passed_to_client(monkeypatch, capsys):
    captured = {}

    class C:
        def __init__(self, *a, **k):
            captured.update(k)

        def get_user(self):
            return {}

    monkeypatch.setattr(cli.config, "resolve_token", lambda: "tok")
    monkeypatch.setattr(cli, "RaindropClient", C)
    cli.main(["--dry-run", "user"])
    assert captured.get("dry_run") is True


# -- error handling -----------------------------------------------------------


def test_missing_token_reports_clean_error(monkeypatch, capsys):
    from rd_cli.errors import ConfigError

    def boom():
        raise ConfigError("no token")

    monkeypatch.setattr(cli.config, "resolve_token", boom)
    code = cli.main(["user"])
    assert code == 1
    assert "no token" in capsys.readouterr().err
