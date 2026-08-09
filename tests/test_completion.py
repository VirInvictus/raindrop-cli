from __future__ import annotations

import shutil
import subprocess

import pytest

from rd_cli import cli, completion


@pytest.fixture
def run(monkeypatch, capsys):
    """Run the CLI and return (exit, stdout). Completion needs no client."""

    def _run(argv):
        monkeypatch.setattr(cli.config, "resolve_token", lambda: "tok")
        code = cli.main(argv)
        return code, capsys.readouterr().out

    return _run


# -- the private-API guard ----------------------------------------------------


def test_argparse_internals_are_where_we_think():
    """The whole point of this test module.

    Completion walks argparse's private structures. If a Python upgrade moves
    any of them, this fails with a pointed message rather than letting every
    generated script quietly come out empty.
    """
    completion.probe_argparse_internals()


# -- the model ----------------------------------------------------------------


def test_describe_finds_top_level_commands():
    tree = completion.describe(cli.build_parser())
    names = tree["subcommands"]
    for expected in ("list", "search", "add", "collections", "tags", "config"):
        assert expected in names, f"{expected} missing from the completion tree"


def test_describe_recurses_into_nested_subcommands():
    tree = completion.describe(cli.build_parser())
    assert "create" in tree["subcommands"]["backups"]["subcommands"]


def test_describe_collects_flags():
    tree = completion.describe(cli.build_parser())
    assert "--tags" in tree["subcommands"]["add"]["options"]


def test_describe_collects_positional_choices_not_subcommands():
    """`rd completion <TAB>` should offer the shells.

    Subparsers are positionals carrying `choices` too, so the walker has to keep
    the two apart or every command name would also be offered as a value.
    """
    tree = completion.describe(cli.build_parser())
    assert sorted(tree["subcommands"]["completion"]["values"]) == [
        "bash",
        "fish",
        "zsh",
    ]
    assert tree["values"] == [], "top-level commands leaked in as positional values"


# -- generated scripts --------------------------------------------------------


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_generate_mentions_a_known_command(shell):
    script = completion.generate(shell, cli.build_parser())
    assert script.strip()
    assert "collections" in script


def test_generate_rejects_an_unknown_shell():
    with pytest.raises(ValueError, match="unknown shell"):
        completion.generate("tcsh", cli.build_parser())


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_cli_prints_the_script(run, shell):
    code, out = run(["completion", shell])
    assert code == 0
    assert "collections" in out


def test_cli_rejects_an_unknown_shell(run):
    with pytest.raises(SystemExit):
        run(["completion", "tcsh"])


# -- the scripts are valid in the shells they target --------------------------
#
# Generating a plausible-looking string is not the same as generating something
# the shell will load. These run the real parser where it is available and skip
# honestly where it is not, rather than asserting on substrings and calling it
# verified.


@pytest.mark.parametrize(
    "shell,argv",
    [
        ("bash", ["bash", "-n"]),
        ("zsh", ["zsh", "-n"]),
        ("fish", ["fish", "--no-execute"]),
    ],
)
def test_generated_script_parses_in_its_own_shell(tmp_path, shell, argv):
    if shutil.which(argv[0]) is None:
        pytest.skip(f"{argv[0]} is not installed")
    path = tmp_path / f"rd.{shell}"
    path.write_text(completion.generate(shell, cli.build_parser()))
    proc = subprocess.run([*argv, str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_bash_completion_actually_completes(tmp_path):
    """Source the script in bash and drive the completion function."""
    if shutil.which("bash") is None:
        pytest.skip("bash is not installed")
    path = tmp_path / "rd.bash"
    path.write_text(completion.generate("bash", cli.build_parser()))
    reply = '"${COMPREPLY[*]}"'
    cases = [
        ("TOP", "(rd col)", 1),
        ("NESTED", "(rd backups '')", 2),
        ("VALUE", "(rd completion z)", 2),
    ]
    script = "\n".join(
        [f"source {path}"]
        + [
            f'COMP_WORDS={words}; COMP_CWORD={cw}; _rd_complete; echo "{tag}:"{reply}'
            for tag, words, cw in cases
        ]
    )
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "TOP:collections" in out
    assert "create" in out.split("NESTED:")[1]
    assert "VALUE:zsh" in out
