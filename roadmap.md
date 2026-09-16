# raindrop-cli roadmap

Newest phases at the bottom. Tick boxes when shipped.

## Phase 0: barebones prototype (pre-framework)

- [x] Initial `requests`-based `api.py` + `cli.py` (list/add/edit/rm,
      collections, tags, highlights). No tests, no docs.

## Phase 1: framework rebuild (v0.1.0)

The current release. Made it correct, dependency-free, and conformant to the
portfolio conventions.

- [x] Port to stdlib `urllib`; drop `requests` and `python-dotenv` (zero
      runtime deps).
- [x] `RaindropClient` core: single `_request`, request timeouts, boolean-param
      lowercasing, typed errors carrying the API `errorMessage`.
- [x] Rate-limit (`429`) and `5xx` retry with bounded backoff.
- [x] Token/config resolution: env, `config.toml`, `.env`; `rd config`.
      Removed the hard-coded personal `.env` path.
- [x] Full API coverage: raindrops (single + batch + suggest + upload + export),
      collections (tree/merge/clean/empty-trash/reorder), tags (rename/merge/rm),
      highlights (list/add/edit/rm), user, stats, filters, import-dedup, backups.
- [x] Pagination generators + `--all`.
- [x] TTY-aware ANSI output (colour off when piped, `NO_COLOR`/`--no-color`),
      tree and aligned-column renderers.
- [x] `--json` works in any position; consistent JSON contract.
- [x] Grouped command surface with hidden back-compat aliases.
- [x] pytest suite over a fake urllib transport (no network); ruff configured.
- [x] Docs: `CLAUDE.md` (API + codebase), `spec.md`, `README.md`, `logo.svg`,
      `VERSION`, this roadmap, patchnotes.
- [x] Bulk/reorg commands (pulled forward after mining prior-art CLIs):
      `mv`, multi-id/scope `rm` (`--permanent`), `tag` (add/remove/clear),
      `add --file/--stdin`, `collections reorder`. Grounded in an empirically
      verified batch-scope quirk (id-lists loop single-item endpoints; scope
      mode uses the batch endpoints; see `CLAUDE.md`).
- [x] `--dry-run` (log method + payload, skip the call) on every write.
- [x] Extra endpoints: raindrop/collection cover upload, icon/cover search,
      HTML-file import (`rd import`), and user-settings edit (`rd user set`).

## Phase 2: authentication and convenience (planned)

- [x] OAuth2 3-legged flow (`rd auth login`): local redirect catcher, code
      exchange, token + refresh_token stored in `config.toml`.
  *(RETIRED 2026-09-12 (Brandon): the auth trio retires and the spec's non-goal stands; the non-expiring token makes the refresh machinery moot.)*
- [ ] ~~Automatic token refresh on `401` when a refresh token is present.~~
      *(RETIRED 2026-09-12 (Brandon): rides on the OAuth2 retirement; there
      will be no refresh token. The spec's non-goal now states this.)*
- [x] Optional secret storage via the Secret Service (`oo7`/keyring) instead of
      plaintext `config.toml` (ask before adding the dep).
  *(DECLINED 2026-09-12 (Brandon): config.toml stays the hardened plaintext store; the zero-dependency stance holds.)*
- [x] `rd open <id>` to launch a raindrop (or its permanent copy) in the browser.
      Takes several ids, `--cache` for the permanent copy (read off the `307`
      `Location`, PRO only), and `--print` to emit the URL instead of launching.

## Phase 3: batch and power features (mostly shipped in Phase 1)

- [x] CLI batch commands (`rd mv`, `rd tag`, multi-id `rm`) mapped to the client
      batch methods, plus `--dry-run` as the safety guard.
- [x] `rd import <file>` (Netscape/Pocket/Instapaper) via `POST /import/file`.
- [x] Collection cover upload / icon search commands.
- [x] Interactive confirmation prompt for large destructive scope operations.
      Gated on unbounded or irreversible blast radius, not on every write: any
      scope mode (`rm`/`mv`/`tag --clear --from`), `rm --permanent`,
      `collections rm`, `collections empty-trash`, and `tags rm`. Removing to
      Trash by id stays unprompted because it is recoverable. `-y`/`--yes` and
      `RD_ASSUME_YES` are the escape hatches, `--dry-run` bypasses (it writes
      nothing), and a non-interactive stdin refuses rather than hanging.
- [ ] `--fields` projection for `--json` output; `--format` templates for human
      output.
- [ ] A `rd context`/`--schema` dump (whole tree + data-model schema) as an
      agent affordance (seen in kyoji2/raindrip).

## Phase 4: ergonomics (planned)

- [x] Shell completion (bash/zsh/fish) generated from the parser. (0.5.0 —
      `rd completion <shell>`, walked off `build_parser()` so it cannot drift.)
- [ ] Config profiles (multiple accounts/tokens).
- [ ] Optional interactive picker (fzf-style) behind a flag, still dependency-free.

## Phase 5: a second backend, Pinboard (v0.2.0)

Turned raindrop-cli from a Raindrop client into a two-service bookmark CLI, reusing
the existing HTTP/output/config machinery.

- [x] `PinboardClient`: stdlib `urllib`, `auth_token` query-param auth,
      `format=json`, a minimum inter-request pacer for Pinboard's rate limit
      (~1 call / 3s), `429`/`5xx` backoff, and the shared typed errors.
- [x] `rd pinboard` (alias `pb`) command group honest to Pinboard's flat model
      (URL as key, no collections): `list`, `get`, `add`, `rm`, `edit`, `tag`,
      `suggest`, `tags list|rename|rm`, `notes list|view`.
- [x] Read-modify-write `edit`/`tag` (Pinboard has no update endpoint).
- [x] Pinboard token resolution + `rd config set-pinboard-token`; both service
      tokens coexist in `config.toml`.
- [x] `--dry-run` and `--json` across the Pinboard surface; pytest coverage
      against the fake transport (auth params, pacing, retry, read-modify-write).
- [x] Cross-service sync landed in Phase 6 (below).

## Phase 6: cross-service sync (v0.3.0)

`rd sync` between Raindrop and Pinboard, built additive-first for safety.

- [x] URL normalization as the match + dedup key (fold scheme/`www`/fragment,
      strip tracking params, keep meaningful query).
- [x] Two-way **additive** sync (adds + merges, never deletes); the two
      libraries converge to their union.
- [x] Reversible model-gap encoding in tags (collection <-> slug tag, `toread`,
      `important`); notes merged idempotently; tags unioned on a shared URL.
- [x] Scoping: `--direction`, `--collection`, `--rd-tag`, `--pb-tag`. Scope
      narrows what is written; matching uses the full sets (no re-import of an
      out-of-scope item that already exists on the other side).
- [x] `--dry-run` plan preview; pure, unit-tested planner.
- [ ] ~~Delete propagation + conflict resolution via a persistent manifest~~
  *(CONFIRMED DEFERRED 2026-09-12 (Brandon): additive-first sync is the standing
  design; Pinboard deletes are permanent. The box was wrongly ticked in the
  meantime; unticked 2026-09-15 per the final audit, the feature is unbuilt.)*
      (three-way diff). Deferred: it needs stored sync state and carries real
      data-loss risk (Pinboard deletes are permanent).
- [ ] A `--reconcile-dupes` pass that merges near-duplicate URLs *within* a
      single service, not just across the two. *(Partially served 2026-09-15:
      `rd dupes` ships as the read-only report of what would collapse; the
      merge remains deliberately unbuilt.)*

## Considered, not committed

- A TUI (would pull a dependency or a lot of stdlib curses; low value over the
  Raindrop web app).
- Sharing/collaborator commands (little personal value; the web UI covers it).
- Library extraction of `client.py` into a standalone `raindrop` package
  (a post-1.0 call once the surface is stable and a second consumer exists).

## Phase 7: Robustness & CLI Bug Sweep (2026-08-23)
*Context: Identified CLI crashes, cross-service data loss, and documentation inaccuracies during codebase sweep.*

### Bugs to Fix
- [x] **Context Count Crash:** Fix `cmd_filters` raising `AttributeError` when Raindrop API returns raw integer counts instead of dicts. *(Fixed 0.6.0: int-or-dict handling.)*
- [x] **False Positives in Human Mode:** Ensure human output mode checks the `ok` variable and returns exit code `1` on failure, matching the JSON mode behavior. *(Verified already-shipped 2026-09-04: failure paths return 1 throughout commands.py; box closed, no change needed. Corrective note 0.6.1: that verification missed the human-mode false-result paths in `tags rename`/`merge`/`collections merge`/`reorder`, which exited 0; the `_out` chokepoint now enforces one exit-code rule for both modes.)*
- [x] **Timestamp Loss on Pinboard / Sync:** Ensure `PinboardClient.edit_post` and cross-service sync operations preserve the original bookmark creation time (`dt=current.get("time")`) instead of overwriting with the current date. *(Fixed 0.6.0: edit_post preserves current time; sync carries the raindrop's created stamp as dt.)*
- [x] **Highlight ANSI Colors:** Map Raindrop highlight colors (`yellow`, `blue`, etc.) to standard ANSI color codes in `output.py` so the `▍` marker isn't completely colorless. *(Fixed 0.6.0: _HL_CODES maps Raindrop names onto the palette; unknown names fall back to muted.)*
- [x] **`toread` Flag Drop:** Fix `raindrop_to_pinboard` dropping the unread status during cross-service pushes to Pinboard. *(Fixed 0.6.0: raindrop_to_pinboard honors the "toread" tag that pinboard_to_raindrop already writes.)*
- [x] **KeyError on Malformed Raindrops:** Use `.get("link")` in `plan_sync` to avoid crashing on uploaded files/documents that lack a URL. *(Fixed 0.6.0: plan_sync skips records with no URL on either side.)*
- [x] **Percent-Encoding Slashes:** Pass `safe=""` to `urllib.parse.quote` in `search_covers` so slashes inside cover search terms don't break the URL path. *(Fixed 0.6.0: safe="" in search_covers.)*
- [x] **`.env` Loading Skip:** Remove the early `return` in `load_env_files` to ensure both local and global configuration files are read. *(Resolved 0.6.0 as documented behavior: load_env_files reads the first existing file on purpose; docstring and code agree, the roadmap's bug framing loses. Corrective note 0.6.1: the 0.6.0 "documented behavior" verdict was half wrong, since the env-over-config order itself was broken until 339baa9; the module-level injected-keys registry now keeps the documented order true across resolvers in one process.)*
- [x] **Browser Launch in Headless:** Prevent `cmd_open` from calling `webbrowser.open()` when `--json` is specified to prevent headless system errors. *(Fixed 0.6.0: --json never launches a browser.)*

### Refactoring & Growth
- [x] **Standardize Command Dispatch:** Extract boilerplate `if args.json: emit(...) else: success(...)` branching into a single helper method. *(Shipped 0.6.1: two chokepoints in commands.py, `_out` for write-shaped and `_rendered` for list-shaped commands, replacing ~57 scattered branches; bespoke renders (user, stats, filters, sync, open, config show, pb get, exists) keep an explicit branch rather than bend through a helper. Both output modes are pinned per command by the StubClient tests.)*
- [x] **Safe File Writing:** Use atomic `os.open` and proper TOML escaping in `config.py` to prevent temporary permission exposure of tokens. *(Fixed 0.6.0: temp-file + os.replace, chmod 0600 before the swap, TOML quote/backslash escaping.)*
- [x] **Multi-Level Completion:** Expand bash/zsh/fish generators to correctly autocomplete nested subcommands (e.g., `rd pinboard tags list <TAB>`). *(Verified already-shipped 2026-09-04: completion.py recurses into nested subcommands, test-pinned.)*
- [x] **Docs Sync:** Update `CLAUDE.md` and `spec.md` to reflect that `rd sync`, `rd open`, and interactive prompts are now implemented. *(Shipped 0.6.1: spec.md re-synced (Status line, non-goals corrected, `open` in the verb list, `--yes`/`RD_ASSUME_YES` in the contract, the sync JSON shape); CLAUDE.md tree lists pinboard/sync/completion and no longer calls sync "not built"; OAuth2 retirement wording applied across spec/README/CLAUDE/roadmap.)*

## Recorded 2026-09-12 (Brandon)

rd.json disposition: the file was deleted (never tracked) and `rd.json` now sits in .gitignore as insurance against recurrence. The landmine note closes.

## New findings 2026-09-12 (six-lens full audit; detail: audit/FULL-AUDIT-2026-09-12.md, Wave 19)

- [x] **HIGH: the token-resolution fix (339baa9) breaks in dual-token
      processes.** load_env_files mutates os.environ and reports only keys
      injected this call; in cmd_sync, resolve_token() runs first, so
      resolve_pinboard_token() then sees the .env value as a real env var
      and a stale ./.env token beats rd config set-pinboard-token - the
      exact bug the commit claims to fix. Persist the injected-keys
      registry across calls (module-level), and add a both-resolvers
      regression test. *(Shipped 0.6.1: module-level `_injected` registry
      matched by exact value; regression test covers both resolution
      orders plus the "config lacks one key" case.)*
- [x] **HIGH: rd sync --json prints human plan lines before the JSON
      document** (only --json --dry-run is clean). Guard the plan lines on
      not args.json; add cmd_sync CLI tests (none exist). *(Shipped 0.6.1:
      plan lines guarded on `not args.json`; four cmd_sync CLI tests added
      via a run_sync fixture, plus a merge-date test.)*
- [x] **0.6.1 lane (go-granted, now precise):** the dispatch helper (57
      if-args.json branches -> one emit chokepoint), the spec.md docs sync
      (Status 0.3.0; non-goals list shipped features; open missing from
      the verb list; the OAuth2 retirement wording x3 + the orphaned
      refresh box), the token fix + both HIGHs, the merge-branch dt fix
      (sync re-dates Pinboard posts today), then cut and publish.
      *(Shipped 0.6.1, tag v0.6.1 published to PyPI by the workflow.)*
- [x] **More code findings (shipped half):** merge-branch re-dating and
      shared:true (both fixed in sync, see above); TimeoutError escapes the
      retry core on 3.11+ (both clients catch it now); explicit ids + --from
      silently ignores the ids (rejected as a usage error in rm/mv/tag);
      aliases visible in --help (investigated 0.6.1: not reproducible -
      unhelped subparsers are unlisted on 3.11 and 3.14, and
      help=argparse.SUPPRESS backfires on 3.14 by rendering the sentinel
      literally; a regression test pins the hidden behavior); config show
      --json masks tokens while README said raw (README corrected, masking
      kept); backups create gained --json.
- [ ] **Remaining code findings (unchanged):** iter_* truncate at
  perpage>50; batch add silently ignores six flags incl. --no-parse doing
  the opposite; NO_COLOR empty-string deviation; CJK width math;
  _toml_line corrupts nested config values; BrokenPipe stderr noise. Full
  list in the ledger.
- [x] **The rename broke Brandon's own config path:**
  ~/.config/rd-cli/config.toml holds both tokens; config_dir() now
  returns ~/.config/raindrop-cli (renamed Sep 3) - no migration ran, so
  the installed rd has no token source. A one-time migration (or reading
  the old path as fallback) belongs in 0.6.1. *(Shipped 0.6.1: the old
  config.toml is a read fallback, the old .env is the last .env candidate,
  the first set-* write repatriates every key, `config path` reports the
  file in effect. Verified live: ~/.config/rd-cli/config.toml exists on
  this machine and raindrop-cli/ did not.)*
- [ ] **Blitz candidates:** highlights -c + source titles
  (get_collection_highlights: zero callers); Pinboard date filters +
  last_update() sync fast-path (built, unwired); backups download
  --latest; --reconcile-dupes stays deliberately deferred.
- [x] **GitHub presentation (workspace batch):** description omits
  Pinboard + sync (the differentiators; replacement drafted); homepage
  404s (codex renamed - /codex/raindrop-cli/ is 200); Releases for
  v0.6.0; topics add pinboard/sync, drop the python triplication; wiki
  off. *(Applied 2026-09-13 with the v0.6.1 cut: description now names
  Pinboard + sync, homepage points at the renamed codex page (verified
  200; the old /codex/rd-cli/ path confirmed 404), topics gained
  pinboard/sync and lost the python3/python-311 duplicates, the first
  GitHub Release (v0.6.1, verbatim patchnotes body) exists, and the
  empty wiki is off.)*

### Final audit 2026-09-13 (THE FINAL AUDIT: NEW findings, one line each; full detail in audit-final/raindrop-cli/FINAL-REPORT.md)
- [x] MED — normalize_url crashes rd sync on a malformed/out-of-range port (urlsplit().port raises ValueError; one junk bookmark in either library = raw traceback; main() catches only RaindropError). Try/except, fall back to the raw URL as the match key.
- [x] MED — The retry family is incomplete: ConnectionResetError and http.client.IncompleteRead escape both retry cores AND main()'s handler (contradicts the spec's retry promise). Broaden to OSError + HTTPException — ideally inside the extracted shared transport core.
- [x] MED — The --json contract cluster: export/completion/config path silently ignore --json and emit non-JSON (plus bare `rd --json` prints human help); pre-flight guards and confirm-aborts emit human stderr with EMPTY stdout in JSON mode (realistic: agents run non-interactive); JSON-mode missing-object exits 0 vs human 1; id-mode rm emits a per-id map vs the spec's {"result": bool}. Emit documents, carve out export/completion, route errors JSON-aware, honor empty_code, fix the shape.
- [x] MED — Batch add silently ignores six single-add flags and --no-parse does the opposite (pleaseParse always {}). Honor per item or reject in batch mode; document whichever.
- [x] MED — perpage>50 silently truncates the iterators after page 1 (unclamped comparison vs the clamped fetch); clamp inside iter_raindrops/iter_highlights (fixes the doc advice too). Currently masked by CLI defaults.
- [x] MED — Release/publish automation: pin the floating pytest/ruff on the publish path and in CI (floors-only today); create the missing v0.5.2/v0.6.0 Releases (verbatim extraction; do NOT backfill pre-0.5.2); append a --notes-from-tag release step to publish.yml so future tags can't end up bare; bind the pypi environment to v* tags.
- [x] MED — pyproject/PyPI metadata: description and keywords omit pinboard + sync; classifiers empty; [project.urls] Homepage-only (add Changelog). Next release propagates.
- [x] LOW — Sync semantics: auto-retry on non-idempotent writes can double-create; in-scope duplicate of an out-of-scope-first URL never pushed; Pinboard ignores Retry-After (Raindrop honors); Raindrop's ISO-millis created passed verbatim as Pinboard's dt (silent re-date risk — normalize); --from 0 not rejected locally; saves carry the seed twice... (that last is Haveli) — raindrop: config tmp file world-readable for a moment vs its own comment.
- [x] LOW — Output polish: format_raindrop_detail passes raw API color names to color() so rd view highlight markers render colorless (route through _HL_CODES — also contradicts the "Fixed 0.6.0" tick, which landed in one of two paths); NO_COLOR="" disables colour (spec says unset); CJK width; multipart escaping; BrokenPipe shutdown noise; id-mode tag --clear unprompted; --perpage silently ignored with --all. *(Shipped 0.7.0.)*
- [x] LOW — Comment truth: the dispatch-chokepoint comment undercounts the --json bypass map by five (11 sites in 10 commands); cli header omits --dry-run/--yes; last_update "(cheap, for sync)" unwired; pinboard docstring overstates the pacer; the duplicated retry comment (applied twice = the drift cost); apply_plan's vestigial dry_run; cmd_completion's why-line; dead re-check branch; iterator docstrings' perpage bound; _write_config_key scope. *(Shipped 0.7.0 except the dead re-check branch, a gated removal; see the Final blitz section.)*
- [x] LOW — Docs: 11 em-dashes against CLAUDE.md:121 (8 in the spec verb list — line 109 already models the colon fix; 2 CLAUDE; 1 historical roadmap); roadmap.md:114 ticked-but-CONFIRMED-DEFERRED box (untick); the auth table omits the legacy .env candidate; the exit-code paragraph omits code 2; spec omits rd completion; CLAUDE.md:8 cites the retired ~/.claude path + "Guidance for Claude Code" phrasing; CLAUDE.md:33's residual OAuth2 "yet"; patchnotes heading-style normalization; Contents skips Behavior notes; lowercase ### support; oceanstrip listed among living siblings; --version position claim; python -m rd_cli checkout claim; "same flags as list" nit; pb --tag max-3 unenforced; BrE/AmE mix. *(Shipped 0.7.0 except the BrE/AmE normalization, declined as a cosmetic sweep with high churn; see the Final blitz section.)*
- [ ] LOW — Hygiene: .gitignore is the unpruned GitHub template (.env listed twice; latent lib//target//downloads traps) — prune to what can fire; tag_message.txt residue (delete; write scratch outside the repo); no .python-version (pin 3.11); no_sleep fixture orphaned; _CODES bold/dim dead; optional SECURITY.md. *(Not executed this window: every removal sub-item is a gated removal and the ask went unanswered, and SECURITY.md is gated; the .python-version pin was attempted and reverted because no 3.11 interpreter is installed locally and uv's Python downloads are manual, so the pin broke every `uv run`; the 3.11 floor is exercised by the CI matrix instead. See the Final blitz section.)*
- [x] Feature candidates logged (FINAL-REPORT L4, ranked): rd config check (attacks the thrice-shipped token-resolution failure class); highlights lane (list -c + source titles + markdown export sharing one join); sync fast-path via last_update + pb date filters (cron-grade sync); rd dupes (read-only); sync --limit N; backups download --latest; --collection accepts titles; apply_plan progress output; rd exists --exit-code; pinboard batch adds; rd context/--schema; --fields/--format (Phase 3 filler); config profiles (L, spec non-goal, parked); fzf picker (last). *(Shipped 0.7.0: config check, the highlights lane, the pb date filters, dupes; the sync fast-path is recorded as design-blocked and the rest are parked with boxes; see the Final blitz section.)*
- [x] Ledger decisions for Brandon: the unwired client methods are deliberate library-graduation surface (record the ledger or schedule wiring); dependabot opt-in; SECURITY.md; confirm SORTS' "-sort" against the live API docs. *(Asked 2026-09-15; the asks went unanswered at the gate, so the status quo is preserved and every item is listed as a reopen condition in the Final blitz section and project.done. The SORTS suspicion is additionally confirmed against the local official docs mirror: "-sort" appears in no documented sort value.)*

**CONFIRMED-prior (final-audit verification):** perpage truncation, the retry family minus TimeoutError, batch-flag ignoring, _toml_line, NO_COLOR empty, CJK width, multipart escaping, BrokenPipe noise, the dead re-check, the ledger box, the OAuth2 partial. SUPERSEDED (verified fixed with tests): the sync --json HIGH, the dual-token HIGH, merge re-dating, hardcoded shared:true, ids+--from rejection, TimeoutError as such, the 0.6.1 docs sync, the alias closure. Audit-side corrections: the sheet's "3.14-only CI" and "142+ tests" are stale (3.11+3.14 matrix; 165 defs/171 collected). Slop-reader verdict: reads human end to end; 11 em-dashes confirmed exactly (10 live — the spec verb list already models its own fix at line 109); the BrE/AmE mix and the Contents gap are the stray notes.

## Final blitz 2026-09-15 (executing the Final audit worklist; window closes 2026-09-20)

### Shipped

- [x] normalize_url crash guard: a malformed or out-of-range port falls back
      to the raw URL as the match key; one junk bookmark no longer crashes
      `rd sync` with a traceback. Regression-tested.
- [x] Shared transport core (`_transport.py`): the retry loop, the
      transient-error family (broadened to OSError + HTTPException so
      ConnectionResetError and IncompleteRead retry), the Retry-After logic
      (Pinboard now honors it too), and the error mapping live in one place.
      Writes are never retried on transport failures (a timed-out POST can
      double-create; it fails loudly instead).
- [x] The --json contract cluster: export --json requires `-o` and emits a
      metadata document; completion --json refuses; config path emits a
      document; guards and confirm refusals emit `{"error"}` on stdout in
      JSON mode; empty_code is honored in JSON mode; id-mode `rm` emits the
      spec's `{"result": bool}`; main() catches OSError/JSONDecodeError at
      the command boundary.
- [x] Batch add rejects the five per-item value flags and honors --no-parse
      (which used to do the opposite of its name in batch mode).
- [x] perpage clamp inside iter_raindrops/iter_highlights; `--perpage` is now
      honored with `--all`.
- [x] Release/publish automation: pytest/ruff pinned in CI and publish;
      publish.yml cuts the GitHub Release from the tag (--notes-from-tag,
      contents:write scoped); the pypi environment is bound to `v*` tags;
      Releases created for v0.5.2 and v0.6.0 (verbatim tag messages; nothing
      pre-0.5.2 backfilled).
- [x] pyproject metadata: description and keywords name Pinboard + sync;
      classifiers added; Changelog URL added. Propagates to PyPI on the next
      publish.
- [x] `rd config check [--ping]`: which config file is in effect, which tier
      each token resolves from (never the value), optional live ping.
- [x] The highlights lane: `highlights list -c <collection>` (wires the idle
      get_collection_highlights), source titles on highlight lines, and
      `highlights export` (markdown grouped by source; --json = grouped doc).
- [x] `rd pinboard list --from/--to` (Pinboard date filters on --all reads;
      refused without --all since posts/recent has no date parameters).
- [x] `rd dupes`: read-only per-service duplicate report (the planner's
      collapse groups, with ids and titles).
- [x] Sync semantics smalls: an in-scope duplicate is preferred as the
      representative (an out-of-scope first sighting no longer blocks the
      push); created stamps normalize to Pinboard's dt shape (millis
      stripped, UTC Z); `--from 0` rejected locally; cmd_sync passes
      --dry-run into both clients.
- [x] Output polish: `rd view` highlight markers route through _HL_CODES
      (they rendered colorless before); `NO_COLOR=""` counts as unset; CJK
      wide characters count two columns; multipart filenames escape quotes
      and line breaks; BrokenPipe shutdown is silent; id-mode `tag --clear`
      now prompts like scope mode.
- [x] Comment/docs truth batch: the chokepoint comment enumerates the
      bespoke --json branches; the cli header lists all four common flags;
      the pacer docstring no longer overclaims; apply_plan's dry-run claim
      made true; completion's lazy import explained; the config writer skips
      non-scalar keys with a warning (and creates the temp at 0600 from the
      first byte); the em-dash sweep finished; the README/spec/CLAUDE doc
      smalls (legacy .env row, exit code 2, completion in the verb list,
      --version position, PYTHONPATH=src form, search-flags nit, pb --tag
      wording, Contents and Support heading fixes, oceanstrip dropped, the
      retired-path citation repointed); the Phase 6 wrongly-ticked box
      unticked.

### Parked (recorded; not built this window)

- [ ] `rd sync --limit N`: gated (the flag's exact semantics are Brandon's
      call). Leaned plan: N caps total applied writes across to_pinboard →
      to_raindrop → merges in that order, plan order preserved.
- [ ] Sync fast-path via last_update(): design-blocked. A safe fast-path
      needs change detection on both sides plus stored state (the deferred
      manifest); Pinboard date filters alone would narrow the READ set and
      violate the no-re-import guarantee. Revisit only with the manifest.
- [ ] `--collection` accepts titles: gated (flag shapes), recorded.
- [ ] Feature backlog in recorded order: backups download --latest;
      --collection titles; apply_plan progress output; rd exists
      --exit-code; pinboard add --file/--stdin; rd context/--schema;
      --fields/--format; config profiles (spec non-goal, parked); fzf
      picker (parked).
- [ ] SORTS cleanup: the official docs mirror (developer-site/v1) documents
      `-created, created, score, n, title, -title, domain, -domain`; "-sort"
      in cli.SORTS is confirmed bogus (likely a "-score" typo) but removing
      it is gated on Brandon's live-docs confirm. The undocumented `n` (by
      order) is also a candidate.
- [ ] Ledger decisions (asked, awaiting answers): the unwired client methods
      (expand_collections, get_user_by_name, parse_url, featured_covers,
      upload_file, delete_collections, last_update) as deliberate
      graduation surface vs wiring; dependabot opt-in; SECURITY.md; the
      removal batch (tag_message.txt, the .gitignore prune, the no_sleep
      fixture, the dead _CODES bold/dim entries, the dead re-check branch
      in plan_sync). Status quo preserved until answered.
