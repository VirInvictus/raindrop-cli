# raindrop-cli Patch Notes

Newest at the top.

## v0.6.1 (2026-09-13)

**The token fix that 0.6.0 never shipped, the config path the rename broke,
and the sync contract repairs.** 0.6.0's token-precedence fix (commit
339baa9) never reached PyPI; this release carries it, repairs a real hole it
still had, and restores the author's own installed copy to working order.

*   **Fixed: the token-precedence fix now holds in dual-token processes.**
    `rd sync` resolves the Raindrop and Pinboard tokens in one process, and
    `load_env_files` only reported the keys it injected on the *current*
    call, so the second resolver took the first call's `.env` injections for
    real environment variables. A stale `./.env` Pinboard token silently beat
    `rd config set-pinboard-token` (the exact bug 339baa9 claimed to fix).
    The injected-keys registry is now module-level and matches by exact
    value, so `.env` sourcing survives across resolutions in any order while
    a genuinely re-exported env var still wins.
*   **Fixed: the September 2026 rename stopped reading your config.** The
    package moved its config directory from `~/.config/rd-cli/` to
    `~/.config/raindrop-cli/` without a migration, so every install that
    predates the rename (including the author's) lost its token source.
    The old path is now a read fallback when the new one has no config; the
    first `rd config set-*` writes the new path and carries every legacy key
    across, and `rd config path` prints the file actually in effect.
*   **Fixed: `rd sync --json` again prints exactly one JSON document.** The
    human plan summary lines printed before the document on a real run
    (only `--json --dry-run` was clean). The plan lines are now guarded off
    in JSON mode: `--dry-run` emits the plan document, a real run emits the
    applied counts.
*   **Fixed: sync merges keep the Pinboard post's date.** A merge re-adds the
    post without `dt`, re-dating it to now and contradicting the documented
    timestamp behavior. The original save time rides along, as edits and
    pushes already did. A push also no longer hardcodes `shared: true`
    (which made every pushed bookmark public): the flag is omitted so your
    Pinboard account default applies, and merges keep the post's own value.
*   **Fixed: socket timeouts join the retry core.** On Python 3.10+ a read
    that times out raises bare `TimeoutError` instead of a `URLError`, so it
    escaped the retry loop in both clients as a traceback. It now retries
    with the same backoff and surfaces as a typed `APIError` when exhausted.
*   **Fixed: explicit ids combined with `--from` are rejected.** The batch
    endpoints scope to the path collection and ignore an id list, so
    `rd rm 5 --from 111` trashed all of collection 111 and never touched
    id 5. `rd rm`, `rd mv`, and `rd tag` now refuse the combination.
*   **`rd backups create` supports `--json`** (emits `{"requested": true}`),
    and `rd config set-token` / `set-pinboard-token` emit
    `{"path": ...}` under `--json` instead of human text.
*   **Exit codes unified.** A false result now exits 1 in human mode too
    (`rd tags rename` and a few others used to exit 0 on failure), matching
    the spec's exit-code table.
*   **Docs re-synced with reality.** `spec.md` was still the 0.3.0 contract:
    its non-goals banned two shipped features (confirmation prompts and the
    permanent-copy endpoint), `open` was missing from the verb list, and
    `--yes`/`RD_ASSUME_YES` were not in the contract. The OAuth2 "planned"
    wording is replaced by the retirement decision in spec, README, and
    CLAUDE.md; the README's `config show --json` "raw tokens" claim is
    corrected (tokens are masked in both modes). CLAUDE.md's module tree now
    lists `pinboard.py`/`sync.py`/`completion.py`.
*   **Internals: the `--json` dispatch debt is paid.** The ~57 scattered
    `if args.json:` branches collapsed into two chokepoints in
    `commands.py` (`_out` for write-shaped commands, `_rendered` for
    list-shaped ones); genuinely bespoke renders keep an explicit branch.
    CI now tests the declared 3.11 floor alongside 3.14.

Two audit findings investigated and closed without a change: the
back-compat aliases are already absent from `rd --help` (unhelped subparsers
are unlisted on 3.11 and 3.14, and `help=argparse.SUPPRESS` would backfire
on 3.14 by rendering the sentinel literally); a regression test now pins
that behavior.

Suite: 170 passed, 1 skipped (was 144 passed, 1 skipped).

## v0.6.0 (2026-09-04)

**Phase 7 robustness sweep: the seven verified bugs, plus safe config
writes.** Every fix regression-tested against the FakeOpener transport:

*   **`rd filters` no longer crashes on bare-integer counts.** The API
    documents counts as `{"count": N}` objects but some responses carry the
    bare integer; both print now.
*   **Pinboard timestamps survive edits and syncs.** `edit_post` preserves the
    original save time (`dt=current.get("time")`), and raindrops pushed to
    Pinboard carry their `created` timestamp as `dt`, so re-syncs never
    re-date anything to now.
*   **Highlight markers are colored.** Raindrop's highlight color names
    (yellow, blue, green, ...) now map onto the CLI palette via
    `_HL_CODES`; unknown names fall back to muted instead of printing the
    raw name as a lookup key and losing the color entirely.
*   **`toread` round-trips through sync.** `pinboard_to_raindrop` already
    preserved unread state as a "toread" tag; `raindrop_to_pinboard` now
    honors that tag instead of hardcoding `toread: False`.
*   **Malformed records are skipped, not fatal.** A raindrop without a link
    or a Pinboard post without an href no longer raises KeyError in
    `plan_sync`; the record is skipped and the rest of the sync proceeds.
*   **Cover searches encode slashes.** `search_covers` passes `safe=""` so
    `a/b c` becomes `a%2Fb%20c` instead of breaking the URL path.
*   **`rd open --json` no longer launches a browser.** JSON is the
    agent/script surface; a browser launch is a side effect those callers
    never asked for. Human mode and `--print` behave as before.
*   **Config writes are atomic and escaped.** `config.toml` (which holds the
    API tokens) is now written via temp-file + `os.replace`, chmod 0600
    before the swap, and TOML values escape quotes and backslashes properly.

Two Phase 7 boxes closed as already-shipped after code verification:
human-mode exit codes (failure paths return 1 throughout commands.py) and
multi-level completion (completion.py recurses into nested subcommands,
test-pinned). The `.env` docstring-vs-roadmap conflict is resolved as
documented behavior: `load_env_files` reads the first existing file on
purpose.

Suite: 144 passed, 1 skipped (was 127).

## v0.5.2 (2026-08-24)

- **Build:** Replaced unittest with pytest in the CI workflow, restoring test coverage execution.
## v0.5.1 (2026-08-23)

- **Build:** build: add GitHub Actions CI workflow

## 0.5.0

### Added

- `rd completion bash|zsh|fish` prints a shell completion script. It is
  generated by walking `build_parser()`, so the parser stays the single source
  of truth and the completion cannot drift from the commands a build actually
  has. Completes commands, nested subcommands, flags, and fixed positional
  choices (`rd completion <TAB>` offers the three shells).

  Install:

  ```sh
  rd completion bash > ~/.local/share/bash-completion/completions/rd
  rd completion zsh  > "${fpath[1]}/_rd"
  rd completion fish > ~/.config/fish/completions/rd.fish
  ```

  Still zero dependencies: argcomplete would have been one, so the emitters are
  hand-rolled. The cost is reading argparse's private structures, which is
  contained by a guard test that names exactly what is relied on and fails with
  a pointed message if a Python release moves any of it.

  The generated bash and zsh scripts are checked in CI by the shells' own
  parsers, and the bash one is additionally sourced and driven to confirm it
  really completes. The fish check skips where fish is not installed rather than
  pretending to pass.

## 0.4.0

### Added

- **`rd open <id>...` opens raindrops in your browser.** Takes any number of
  ids. `--cache` (alias `--permanent`) opens the archived permanent copy
  instead of the original link: that endpoint answers `307` with the storage
  URL in a header, so the client asks for it with redirects suppressed and
  reads `Location` rather than following it and downloading the copy. The
  archive is a PRO feature and only some links are stored, so a missing copy
  reports that plainly instead of opening the wrong thing. `--print` emits the
  URL and launches nothing, which is what you want over SSH or in a pipe.
- **Confirmation prompts on destructive operations.** The guard used to be
  `--dry-run` and nothing else, which only helps if you remember to type it
  first. Prompts are gated on blast radius rather than on every write, so the
  common path stays quiet:
  - **Unbounded:** scope mode on `rd rm`, `rd mv`, and `rd tag --clear`, where
    `--from` can match any number of raindrops. The prompt counts them first
    and names the number.
  - **Irreversible:** `rd rm --permanent`, `rd collections empty-trash`, and
    `rd tags rm`. `rd collections rm` also asks, because deleting a collection
    takes its contents along with it.
  - **Not prompted:** removing by id to Trash (recoverable), and appending tags
    in scope mode (additive).
- `-y`/`--yes` skips the prompts, and `RD_ASSUME_YES=1` does the same for cron
  and scripts that cannot answer one. `--dry-run` bypasses confirmation
  entirely, since it performs no writes and its whole purpose is to show you
  what would happen.

### Notes

- A non-interactive stdin **refuses** rather than prompting. Blocking on a read
  no one can answer would hang a script forever, and assuming yes would delete
  things nobody agreed to.
- The prompt is written to stderr, so confirming does not contaminate a
  redirected stdout.
- The affected-item count is read opportunistically. The list endpoint is not
  documented to return a total, so a missing count produces "every raindrop in
  collection X" rather than a confidently wrong number.

## 0.3.0

### Added

- **`rd sync`: two-way additive sync between Raindrop and Pinboard.** Matches
  bookmarks across the two services by a *normalized* URL (scheme/`www`/fragment
  folded, tracking params like `utm_*`/`fbclid` stripped, meaningful query kept),
  which doubles as the cross-service dedup key. It only ever adds and merges,
  never deletes, so the two libraries converge to their union with no data loss.
- The model gap is bridged reversibly in tags: a Raindrop collection becomes a
  slugged Pinboard tag, Pinboard's `toread` and Raindrop's `important` ride along
  as tags, and a Pinboard tag that matches a collection routes the item back into
  that collection. Highlights stay Raindrop-only. On a URL that exists on both
  sides, tags are unioned and notes are merged idempotently (no duplication on
  repeat runs).
- **Scoping** so you never have to union everything at once: `--direction
  both|to-pinboard|to-raindrop`, and `--collection`/`--rd-tag`/`--pb-tag` to
  restrict which items are pushed. Scope narrows what is *written*, but matching
  always uses the full sets, so an out-of-scope item that already exists on the
  other side is never re-imported as a duplicate.
- `--dry-run` prints the plan (counts per direction, near-dupes collapsed) and
  writes nothing. The planning half (`sync.plan_sync` and the mapping helpers)
  is pure and covered by unit tests independent of the network.

## 0.2.0

### Added

- **Pinboard as a second bookmarking backend**, alongside Raindrop. A new `rd
  pinboard` (alias `pb`) command group speaks Pinboard's flat model natively
  (bookmarks keyed by URL, tags, notes, and the `toread`/`shared` flags) instead
  of pretending it has Raindrop's collections: `pinboard list|get|add|rm|edit|
  tag|suggest`, `pinboard tags list|rename|rm`, and `pinboard notes list|view`.
- `PinboardClient`, a stdlib sibling of `RaindropClient`: auth through the
  `auth_token` query param, `format=json` on every call, a minimum inter-request
  pacer for Pinboard's strict rate limit (about one call every three seconds) on
  top of the usual `429` backoff, and the shared typed-error family plus
  `--dry-run` and `--json` behavior. Pinboard writes are all GETs, so they are
  flagged explicitly rather than inferred from the HTTP method.
- Pinboard token resolution mirrors Raindrop: `PINBOARD_TOKEN` (or
  `PINBOARD_API_TOKEN`) env var, `pinboard_token` in `config.toml`, or a `.env`
  file; `rd config set-pinboard-token <token>` writes it (0600). Both service
  tokens coexist in the one config file without clobbering each other.
- Pinboard has no update endpoint, so `edit` and `tag` are a read-modify-write:
  fetch the bookmark, merge the change, and re-save with `replace=yes`, leaving
  untouched fields intact.

## 0.1.1

### Fixed

- `--dry-run` no longer mislabels a bodyless request as `<multipart>`. A plain
  DELETE or PUT with no body now previews as `<no body>`, JSON writes preview as
  their JSON (unchanged), and multipart uploads preview as
  `<multipart ... files=[...]>` without dumping the raw file bytes. Extracted the
  logic into `_dry_run_preview` with direct unit coverage.

## 0.1.0

The framework rebuild. The barebones prototype became a dependency-free,
tested, fully documented CLI.

### Added

- Complete API coverage: raindrops (single, batch, suggest, file/cover upload,
  export), collections (list, tree, view, add, edit, remove, merge, clean,
  empty-trash, reorder, cover, cover search), tags (list, rename, merge,
  remove), highlights (list, add, edit, remove), plus `user` (show + `set`),
  `stats`, `filters`, `suggest`, `exists` (import dedup), HTML-file import, and
  `backups` (list, create, download).
- Bulk/reorganization commands: `rd mv`, multi-id and scope `rd rm`
  (`--permanent`), `rd tag` (add/remove/clear), and `rd add --file/--stdin` for
  batch create. Explicit ids loop the single-item endpoints; `--from
  <collection>` uses the batch endpoints for whole-collection scope. (Grounded
  in an empirically verified quirk: the batch endpoints only touch raindrops
  actually in the path collection, so a naive id-based batch move silently
  no-ops. Two other CLIs surveyed carry exactly that latent bug.)
- `--dry-run`: previews every write (logs method + payload to stderr) without
  calling the API; reads still run so a plan can be built first.
- Grouped command surface (`rd collections tree`, `rd tags rename`,
  `rd highlights add`, ...) with `c`/`t`/`h` short aliases, keeping the original
  flat commands (`c-list`, `t-list`, `h-list`, ...) working as hidden aliases.
- `--all` to auto-paginate list and highlight reads.
- `rd config path|show|set-token`; token also resolvable from
  `~/.config/raindrop-cli/config.toml` and `.env`, with `RAINDROP_TOKEN` as the
  primary env var (`RAINDROP_TEST_TOKEN` still honored).
- TTY-aware ANSI output (Kanagawa-ish palette): colour on a terminal, plain when
  piped, `NO_COLOR` and `--no-color` respected. Nested collection tree view and
  aligned tag/collection columns.
- `--version`, and `--json` now works before or after the subcommand.
- pytest suite exercising the client, config, output, and CLI against a fake
  urllib transport (no network); ruff lint/format configured.
- Framework docs: comprehensive `CLAUDE.md` (Raindrop API + codebase), `spec.md`,
  `roadmap.md`, `logo.svg`, single-source `VERSION`.

### Changed

- Ported the whole client from `requests` to stdlib `urllib`; removed the
  `requests` and `python-dotenv` dependencies (zero runtime deps now).
- Split the two-file prototype into a package: `errors`, `config`, `client`,
  `output`, `commands`, `cli`.
- `add` now auto-parses page metadata by default (title, cover, type) unless
  `--no-parse`; default target collection is Unsorted.

### Fixed

- Requests now use a timeout (previously could hang forever).
- Boolean query params are sent lowercase (`nested=true`); the API rejected the
  previous `True`/`False`.
- API error messages surface to the user (the `errorMessage` from the response)
  instead of a bare HTTP status.
- Rate-limit (`429`) and transient `5xx` responses retry with backoff instead of
  failing immediately (`Retry-After` parsed as seconds or an HTTP-date).
- `rm --permanent` uses the documented two-step delete; the undocumented
  `?permanent=true` query param was tested and does not one-shot a live
  raindrop.
- Removed a hard-coded personal `.env` path that leaked into the repo.
