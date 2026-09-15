"""Command handlers. Each ``cmd_*`` function takes ``(client, args)`` and returns
a process exit code. ``cfg_*`` handlers operate on local config and ignore the
client (which may be ``None``). ``cli.py`` wires these to argparse subcommands.
"""

from __future__ import annotations

import mimetypes
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any

from . import config, output, sync
from .client import RaindropClient
from .pinboard import PinboardClient

# -- confirmation -------------------------------------------------------------


def _assume_yes(args: Any) -> bool:
    """True when the user has pre-agreed, via ``--yes`` or ``RD_ASSUME_YES``.

    The env var exists for cron and scripts, which cannot answer a prompt but
    also should not have to thread ``--yes`` through every call site.
    """
    if getattr(args, "yes", False):
        return True
    return os.environ.get("RD_ASSUME_YES", "").strip().lower() in ("1", "true", "yes")


def _confirmed(args: Any, question: str) -> str | None:
    """Gate a destructive operation behind a confirmation.

    Returns ``None`` when the operation may proceed, otherwise the refusal
    reason, ready to hand to :func:`_fail`. ``--dry-run`` passes straight
    through: it performs no writes, and its whole point is to show what would
    happen without an interrogation first. In ``--json`` mode the refusal is
    the run's single stdout document, so it is captured here instead of
    printed to stderr.
    """
    if getattr(args, "dry_run", False):
        return None
    if args.json:
        refused: list[str] = []
        ok = output.confirm(question, assume_yes=_assume_yes(args), emit=refused.append)
        if ok:
            return None
        return refused[0] if refused else "aborted"
    if not output.confirm(question, assume_yes=_assume_yes(args)):
        return "aborted"
    return None


def _scope_count(client: RaindropClient, collection: int, search: str, nested: bool):
    """Best-effort count of the raindrops a scope operation would touch.

    The list endpoint is not documented to return a total, so treat a missing
    ``count`` as unknown and let the caller word the prompt without a number
    rather than assert a wrong one.
    """
    try:
        envelope = client.get_raindrops(
            collection, search=search, nested=nested, perpage=1
        )
    except Exception:
        return None
    count = envelope.get("count") if isinstance(envelope, dict) else None
    return count if isinstance(count, int) else None


def _scope_phrase(count, noun: str = "raindrop") -> str:
    if count is None:
        return f"every {noun}"
    return f"{count} {noun}" + ("" if count == 1 else "s")


# -- --json dispatch chokepoints -----------------------------------------------
#
# Every command decides its output mode in exactly one of these helpers, so the
# single-document JSON contract has a handful of enforcement points instead of
# sixty scattered branches. The genuinely bespoke human renders (user, stats,
# filters, sync, open, config show, pb get, pb suggest, pb notes view, exists)
# keep an explicit ``if args.json:`` branch instead of bending through a
# helper; the StubClient tests pin both output modes per command.


def _fail(args: Any, message: str) -> int:
    """Emit a handled error in the active mode and return 1.

    ``--json`` mode gets ``{"error": ...}`` on stdout — a script parsing the
    run must never see an empty stdout on a handled failure, which is exactly
    what the old human-only ``output.error`` paths produced. Humans get the
    stderr line as before."""
    if args.json:
        output.emit_json({"error": message})
    else:
        output.error(message)
    return 1


def _out(args: Any, payload: Any, human: str, *, ok: bool = True, err: str = "") -> int:
    """Write-shaped commands: JSON mode emits exactly the payload document;
    human mode prints the message (or ``err`` as an error when ``ok`` is
    false). ``ok`` decides the exit code in both modes, so a false result
    exits 1 even in human output, per the spec's exit-code table."""
    if args.json:
        output.emit_json(payload)
    elif ok:
        output.success(human)
    else:
        output.error(err or human)
    return 0 if ok else 1


def _rendered(
    args: Any, items: Any, render, *, empty: str | None = None, empty_code: int = 0
) -> int:
    """Read/list-shaped commands: JSON mode emits the raw API payload; human
    mode prints the rendered rows, or the empty-state message when there is
    nothing (exiting ``empty_code``). A missing object exits ``empty_code`` in
    both modes, so ``rd view --json`` on a dead id exits 1 like the human
    mode (and like ``pb get``) instead of drifting to 0."""
    if args.json:
        output.emit_json(items)
        return 0 if items else empty_code
    if not items and empty is not None:
        output.error(empty)
        return empty_code
    print(render())
    return 0


# -- raindrops ----------------------------------------------------------------


def cmd_list(client: RaindropClient, args: Any) -> int:
    if getattr(args, "all", False):
        items = list(
            client.iter_raindrops(
                args.collection,
                search=args.search,
                sort=args.sort,
                nested=args.nested,
                perpage=args.perpage,
            )
        )
    else:
        items = client.get_raindrops(
            args.collection,
            search=args.search,
            sort=args.sort,
            page=args.page,
            perpage=args.perpage,
            nested=args.nested,
        ).get("items", [])
    return _rendered(
        args,
        items,
        lambda: "\n".join(
            output.format_raindrop_line(item, detailed=args.detailed) for item in items
        ),
        empty="no raindrops found",
    )


def cmd_view(client: RaindropClient, args: Any) -> int:
    item = client.get_raindrop(args.id)
    return _rendered(
        args,
        item,
        lambda: output.format_raindrop_detail(item),
        empty=f"raindrop {args.id} not found",
        empty_code=1,
    )


def cmd_open(client: RaindropClient, args: Any) -> int:
    """Open one or more raindrops in the browser (or print their URLs)."""
    resolved: list[dict] = []
    failed = False
    for rid in args.ids:
        item = client.get_raindrop(rid)
        if not item:
            output.error(f"raindrop {rid} not found")
            failed = True
            continue
        if args.cache:
            url = client.get_permanent_copy_url(rid)
            if not url:
                output.error(
                    f"raindrop {rid} has no permanent copy "
                    "(the archive is a PRO feature, and only some links are stored)"
                )
                failed = True
                continue
        else:
            url = item.get("link")
            if not url:
                output.error(f"raindrop {rid} has no link")
                failed = True
                continue
        resolved.append({"id": rid, "url": url, "title": item.get("title") or ""})

    if args.json:
        output.emit_json(resolved)
    elif args.print_url:
        for entry in resolved:
            print(entry["url"])

    # --json is the agent/script surface: resolving the URLs is the job, and
    # a browser launch is a side effect those callers never asked for.
    if not args.json and not args.print_url:
        for entry in resolved:
            # Failing to launch is not fatal: on a headless box there may be no
            # browser at all, and the URL is still worth surfacing.
            if not webbrowser.open(entry["url"]):
                output.error(f"could not launch a browser for {entry['url']}")
                failed = True

    return 1 if failed else 0


def cmd_add(client: RaindropClient, args: Any) -> int:
    urls = _collect_urls(args)
    if urls is not None:
        return _add_many(client, args, urls)
    if not args.url:
        return _fail(args, "provide a URL, or --file/--stdin to add many")
    item = client.create_raindrop(
        args.url,
        title=args.title,
        collection_id=args.collection,
        tags=args.tags,
        excerpt=args.excerpt,
        note=args.note,
        important=args.important or None,
        please_parse=not args.no_parse,
    )
    return _out(
        args, item, f"added [{item.get('_id')}] {item.get('title') or args.url}"
    )


def _collect_urls(args: Any) -> list[str] | None:
    """URLs for batch add from ``--file`` / ``--stdin``, or ``None`` for single."""
    if getattr(args, "stdin", False):
        text = sys.stdin.read()
    elif getattr(args, "file", None):
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        return None
    return [line.strip() for line in text.splitlines() if line.strip()]


def _add_many(client: RaindropClient, args: Any, urls: list[str]) -> int:
    created: list[dict] = []
    for chunk in _chunks(urls, 100):  # API caps a batch at 100 items
        items = [
            {"link": url, "collection": {"$id": args.collection}, "pleaseParse": {}}
            for url in chunk
        ]
        created.extend(client.create_raindrops(items))
    return _out(args, created, f"added {len(created)} raindrop(s)")


def cmd_edit(client: RaindropClient, args: Any) -> int:
    item = client.update_raindrop(
        args.id,
        title=args.title,
        tags=args.tags,
        collection_id=args.collection,
        note=args.note,
        excerpt=args.excerpt,
        important=_tristate(args.important, args.not_important),
    )
    return _out(
        args, item, f"edited [{item.get('_id')}] {item.get('title') or ''}".rstrip()
    )


def cmd_rm(client: RaindropClient, args: Any) -> int:
    if not args.ids and args.from_collection is None:
        return _fail(
            args, "provide raindrop id(s), or --from <collection> for scope mode"
        )
    # Scope mode: delete everything in a source collection (optionally filtered
    # by search) in one batch call. The batch endpoint's path is a scope, so a
    # real source collection is required (0 is unsupported for remove-many).
    if getattr(args, "from_collection", None) is not None:
        if args.ids:
            return _fail(
                args,
                "--from is scope mode and ignores explicit ids; pass ids or "
                "--from, not both",
            )
        if args.from_collection == 0:
            # The batch endpoints reject 0 server-side (and a silent no-op is
            # worse than a loud error): catch it before the call.
            return _fail(
                args,
                "the batch endpoints do not support collection 0; "
                "pass a real collection id (or -1/-99)",
            )
        count = _scope_count(
            client, args.from_collection, args.search or "", args.nested
        )
        where = f"collection {args.from_collection}"
        if args.search:
            where += f" matching {args.search!r}"
        refused = _confirmed(args, f"Remove {_scope_phrase(count)} in {where}?")
        if refused:
            return _fail(args, refused)
        n = client.delete_raindrops(
            args.from_collection, search=args.search or "", nested=args.nested
        )
        return _out(
            args,
            {"modified": n},
            f"removed {n} raindrop(s) from collection {args.from_collection}",
        )

    # Id mode: loop the single-item endpoint (always correct regardless of which
    # collection each raindrop lives in). Only the permanent path asks: a plain
    # remove lands in Trash and is undoable, so a prompt there is just noise.
    if args.permanent:
        refused = _confirmed(
            args,
            f"Permanently delete {len(args.ids)} raindrop(s)? This cannot be undone.",
        )
        if refused:
            return _fail(args, refused)
    results = {
        rid: client.delete_raindrop(rid, permanent=args.permanent) for rid in args.ids
    }
    ok = sum(1 for v in results.values() if v)
    verb = "permanently deleted" if args.permanent else "moved to trash"
    # The payload is the spec's boolean-result shape; the human line carries
    # the per-run counts.
    return _out(
        args,
        {"result": ok == len(results)},
        f"{verb} {ok}/{len(results)} raindrop(s)",
        ok=ok == len(results),
    )


def cmd_export(client: RaindropClient, args: Any) -> int:
    if args.json and not args.output:
        # The export payload is raw CSV/HTML/ZIP bytes; they cannot ride in the
        # single JSON document. Refuse instead of silently ignoring --json,
        # and point at -o (mirroring `backups download`'s metadata document).
        return _fail(
            args,
            "export writes raw bytes; in --json mode pass -o to name a file",
        )
    data = client.export(
        args.collection, fmt=args.format, sort=args.sort, search=args.search
    )
    if args.output:
        with open(args.output, "wb") as fh:
            fh.write(data)
        return _out(
            args,
            {"path": args.output, "bytes": len(data), "format": args.format},
            f"wrote {len(data)} bytes to {args.output}",
        )
    sys.stdout.buffer.write(data)
    return 0


def cmd_mv(client: RaindropClient, args: Any) -> int:
    dest = args.collection
    if not args.ids and args.from_collection is None:
        return _fail(
            args, "provide raindrop id(s), or --from <collection> for scope mode"
        )
    # Scope mode: move everything in a source collection (optional search) at once.
    if getattr(args, "from_collection", None) is not None:
        if args.ids:
            return _fail(
                args,
                "--from is scope mode and ignores explicit ids; pass ids or "
                "--from, not both",
            )
        if args.from_collection == 0:
            return _fail(
                args,
                "the batch endpoints do not support collection 0; "
                "pass a real collection id (or -1/-99)",
            )
        count = _scope_count(
            client, args.from_collection, args.search or "", args.nested
        )
        where = f"collection {args.from_collection}"
        if args.search:
            where += f" matching {args.search!r}"
        refused = _confirmed(
            args, f"Move {_scope_phrase(count)} from {where} into collection {dest}?"
        )
        if refused:
            return _fail(args, refused)
        n = client.update_raindrops(
            args.from_collection,
            search=args.search or "",
            nested=args.nested,
            move_to=dest,
        )
        return _out(
            args, {"modified": n}, f"moved {n} raindrop(s) to collection {dest}"
        )

    # Id mode: loop single-item updates (correct across heterogeneous sources).
    moved = 0
    for rid in args.ids:
        client.update_raindrop(rid, collection_id=dest)
        moved += 1
    return _out(
        args,
        {"moved": moved, "collection": dest},
        f"moved {moved} raindrop(s) to collection {dest}",
    )


def cmd_tag(client: RaindropClient, args: Any) -> int:
    add = args.add or []
    remove = set(args.remove or [])
    if not (add or remove or args.clear):
        return _fail(args, "nothing to do: pass --add, --remove, or --clear")

    # Scope mode: append tags (or clear all) across a whole collection/search.
    if getattr(args, "from_collection", None) is not None:
        if args.ids:
            return _fail(
                args,
                "--from is scope mode and ignores explicit ids; pass ids or "
                "--from, not both",
            )
        if args.from_collection == 0:
            return _fail(
                args,
                "the batch endpoints do not support collection 0; "
                "pass a real collection id (or -1/-99)",
            )
        if remove:
            return _fail(
                args,
                "--remove is not supported in scope mode; use ids, or "
                "`tags rm <tag>` to strip a tag from every raindrop",
            )
        new_tags: list[str] = [] if args.clear else add
        count = _scope_count(
            client, args.from_collection, args.search or "", args.nested
        )
        where = f"collection {args.from_collection}"
        if args.search:
            where += f" matching {args.search!r}"
        # Appending tags is additive and cheap to undo; --clear destroys every
        # tag in scope, so only that branch asks.
        if args.clear:
            refused = _confirmed(
                args, f"Clear all tags from {_scope_phrase(count)} in {where}?"
            )
            if refused:
                return _fail(args, refused)
        n = client.update_raindrops(
            args.from_collection,
            search=args.search or "",
            nested=args.nested,
            tags=new_tags,
        )
        return _out(args, {"modified": n}, f"updated tags on {n} raindrop(s)")

    # Id mode: compute the new tag set per raindrop (add/remove/clear precisely).
    # --clear destroys every tag on the item with no undo, so it asks just like
    # scope mode does (there is no record of the prior tags to restore from).
    if args.clear:
        refused = _confirmed(
            args,
            f"Clear all tags from {len(args.ids)} raindrop(s)? This cannot be undone.",
        )
        if refused:
            return _fail(args, refused)
    changed = 0
    for rid in args.ids:
        current = [] if args.clear else list(client.get_raindrop(rid).get("tags") or [])
        merged = [t for t in current if t not in remove]
        for t in add:
            if t not in merged:
                merged.append(t)
        client.update_raindrop(rid, tags=merged)
        changed += 1
    return _out(args, {"updated": changed}, f"updated tags on {changed} raindrop(s)")


# -- collections --------------------------------------------------------------


def cmd_collections_list(client: RaindropClient, args: Any) -> int:
    items = client.get_collections()
    return _rendered(args, items, lambda: output.format_collections_flat(items))


def cmd_collections_tree(client: RaindropClient, args: Any) -> int:
    roots = client.get_collections()
    children = client.get_child_collections()
    return _rendered(
        args,
        {"roots": roots, "children": children},
        lambda: output.format_collection_tree(roots, children),
    )


def cmd_collections_view(client: RaindropClient, args: Any) -> int:
    item = client.get_collection(args.id)
    return _rendered(
        args,
        item,
        lambda: output.format_collections_flat([item]),
        empty=f"collection {args.id} not found",
        empty_code=1,
    )


def cmd_collections_add(client: RaindropClient, args: Any) -> int:
    item = client.create_collection(
        args.title,
        view=args.view,
        public=args.public or None,
        parent_id=args.parent,
    )
    return _out(
        args, item, f"created collection [{item.get('_id')}] {item.get('title')}"
    )


def cmd_collections_edit(client: RaindropClient, args: Any) -> int:
    item = client.update_collection(
        args.id,
        title=args.title,
        view=args.view,
        public=_tristate(args.public, args.private),
        parent_id=args.parent,
    )
    return _out(
        args, item, f"edited collection [{item.get('_id')}] {item.get('title')}"
    )


def cmd_collections_rm(client: RaindropClient, args: Any) -> int:
    # Deleting a collection takes its raindrops with it (they go to Trash), so
    # the blast radius is everything inside, not the one id typed.
    refused = _confirmed(
        args,
        f"Delete collection {args.id} and move its raindrops to Trash?",
    )
    if refused:
        return _fail(args, refused)
    ok = client.delete_collection(args.id)
    return _out(
        args,
        {"result": ok},
        f"deleted collection {args.id}",
        ok=ok,
        err=f"failed to delete collection {args.id}",
    )


def cmd_collections_merge(client: RaindropClient, args: Any) -> int:
    ok = client.merge_collections(args.to, args.ids)
    return _out(
        args,
        {"result": ok},
        f"merged {len(args.ids)} collection(s) into {args.to}",
        ok=ok,
        err=f"failed to merge into collection {args.to}",
    )


def cmd_collections_clean(client: RaindropClient, args: Any) -> int:
    count = client.clean_collections()
    return _out(args, {"removed": count}, f"removed {count} empty collection(s)")


def cmd_collections_empty_trash(client: RaindropClient, args: Any) -> int:
    refused = _confirmed(
        args,
        "Permanently delete everything in Trash? This cannot be undone.",
    )
    if refused:
        return _fail(args, refused)
    ok = client.empty_trash()
    return _out(
        args, {"result": ok}, "emptied trash", ok=ok, err="failed to empty trash"
    )


def cmd_collections_reorder(client: RaindropClient, args: Any) -> int:
    ok = client.reorder_collections(args.by)
    return _out(
        args,
        {"result": ok},
        f"reordered all collections by {args.by}",
        ok=ok,
        err=f"failed to reorder collections by {args.by}",
    )


def cmd_collections_cover(client: RaindropClient, args: Any) -> int:
    name, content, mime = _read_file(args.file)
    item = client.upload_collection_cover(args.id, name, content, mime)
    return _out(args, item, f"set cover on collection {args.id}")


def cmd_collections_covers(client: RaindropClient, args: Any) -> int:
    groups = client.search_covers(args.text)

    def render() -> str:
        lines: list[str] = []
        for group in groups:
            lines.append(output.color(group.get("title", "?"), "title"))
            for icon in group.get("icons", []):
                url = icon.get("svg") or icon.get("png")
                if url:
                    lines.append(f"  {url}")
        return "\n".join(lines)

    return _rendered(args, groups, render)


# -- tags ---------------------------------------------------------------------


def cmd_tags_list(client: RaindropClient, args: Any) -> int:
    items = client.get_tags(args.collection)
    return _rendered(
        args, items, lambda: output.format_tags(items), empty="no tags found"
    )


def cmd_tags_rename(client: RaindropClient, args: Any) -> int:
    ok = client.rename_tag(args.old, args.new, args.collection)
    return _out(
        args,
        {"result": ok},
        f"renamed #{args.old} to #{args.new}",
        ok=ok,
        err=f"failed to rename #{args.old} to #{args.new}",
    )


def cmd_tags_merge(client: RaindropClient, args: Any) -> int:
    ok = client.merge_tags(args.tags, args.into, args.collection)
    merged = ", ".join("#" + t for t in args.tags)
    return _out(
        args,
        {"result": ok},
        f"merged {merged} into #{args.into}",
        ok=ok,
        err=f"failed to merge {merged} into #{args.into}",
    )


def cmd_tags_rm(client: RaindropClient, args: Any) -> int:
    # Strips the tag from every raindrop carrying it; there is no undo and no
    # way to enumerate what was touched afterwards.
    scope = (
        f" in collection {args.collection}"
        if args.collection is not None
        else " everywhere"
    )
    listed = ", ".join("#" + t for t in args.tags)
    refused = _confirmed(args, f"Delete {listed}{scope}? This cannot be undone.")
    if refused:
        return _fail(args, refused)
    ok = client.delete_tags(args.tags, args.collection)
    return _out(
        args,
        {"result": ok},
        f"deleted tag(s): {listed}",
        ok=ok,
        err=f"failed to delete tag(s): {listed}",
    )


# -- highlights ---------------------------------------------------------------


def cmd_highlights_list(client: RaindropClient, args: Any) -> int:
    if args.raindrop:
        items = client.get_raindrop_highlights(args.raindrop)
    elif getattr(args, "all", False):
        items = list(client.iter_highlights(perpage=args.perpage))
    else:
        items = client.get_all_highlights(page=args.page, perpage=args.perpage)
    return _rendered(
        args,
        items,
        lambda: "\n".join(output.format_highlight_line(hl) for hl in items),
        empty="no highlights found",
    )


def cmd_highlights_add(client: RaindropClient, args: Any) -> int:
    highlights = client.add_highlight(
        args.raindrop, args.text, color=args.color, note=args.note
    )
    return _out(args, highlights, f"added highlight to raindrop {args.raindrop}")


def cmd_highlights_edit(client: RaindropClient, args: Any) -> int:
    highlights = client.update_highlight(
        args.raindrop,
        args.highlight,
        text=args.text,
        color=args.color,
        note=args.note,
    )
    return _out(args, highlights, f"updated highlight {args.highlight}")


def cmd_highlights_rm(client: RaindropClient, args: Any) -> int:
    remaining = client.delete_highlight(args.raindrop, args.highlight)
    return _out(args, remaining, f"deleted highlight {args.highlight}")


# -- user / filters / suggest / exists ---------------------------------------


def cmd_user(client: RaindropClient, args: Any) -> int:
    user = client.get_user()
    if args.json:
        output.emit_json(user)
        return 0
    pro = "PRO" if user.get("pro") else "free"
    print(output.color(user.get("fullName") or "(unknown)", "title"))
    print(f"  {output.color('id:', 'muted')} {user.get('_id')}")
    print(f"  {output.color('email:', 'muted')} {user.get('email')}")
    print(f"  {output.color('plan:', 'muted')} {pro}")
    files = user.get("files") or {}
    if files:
        used = files.get("used", 0)
        size = files.get("size", 0)
        print(f"  {output.color('files:', 'muted')} {used} / {size} bytes")
    return 0


def cmd_user_set(client: RaindropClient, args: Any) -> int:
    config_updates: dict[str, str] = {}
    for pair in args.config or []:
        key, sep, value = pair.partition("=")
        if not sep:
            return _fail(args, f"bad --config entry (want key=value): {pair}")
        config_updates[key.strip()] = value.strip()
    user = client.update_user(
        fullName=args.name,
        email=args.email,
        newpassword=args.new_password,
        oldpassword=args.old_password,
        config=config_updates or None,
    )
    return _out(args, user, "updated user settings")


def cmd_cover(client: RaindropClient, args: Any) -> int:
    name, content, mime = _read_file(args.file)
    item = client.upload_cover(args.id, name, content, mime)
    return _out(args, item, f"set cover on raindrop {args.id}")


def cmd_import(client: RaindropClient, args: Any) -> int:
    name, content, mime = _read_file(args.file)
    groups = client.parse_import_file(name, content, mime)
    bookmarks = _flatten_bookmarks(groups)
    if not args.create:
        return _out(
            args,
            groups,
            f"parsed {len(bookmarks)} bookmark(s) across {len(groups)} group(s)\n"
            "re-run with --create -c <collection> to import them",
        )
    created: list[dict] = []
    for chunk in _chunks(bookmarks, 100):
        items = [
            {
                "link": b["link"],
                "title": b.get("title", ""),
                "excerpt": b.get("excerpt", ""),
                "tags": b.get("tags", []),
                "collection": {"$id": args.collection},
            }
            for b in chunk
            if b.get("link")
        ]
        created.extend(client.create_raindrops(items))
    return _out(
        args,
        created,
        f"imported {len(created)} bookmark(s) into collection {args.collection}",
    )


def cmd_stats(client: RaindropClient, args: Any) -> int:
    stats = client.get_stats()
    if args.json:
        output.emit_json(stats)
        return 0
    names = {0: "All", -1: "Unsorted", -99: "Trash"}
    for entry in stats.get("items", []):
        name = names.get(entry.get("_id"), str(entry.get("_id")))
        print(f"  {output.color(name + ':', 'muted')} {entry.get('count', 0)}")
    meta = stats.get("meta") or {}
    if meta:
        dups = (meta.get("duplicates") or {}).get("count", 0)
        broken = (meta.get("broken") or {}).get("count", 0)
        print(f"  {output.color('duplicates:', 'muted')} {dups}")
        print(f"  {output.color('broken:', 'muted')} {broken}")
    return 0


def cmd_filters(client: RaindropClient, args: Any) -> int:
    filters = client.get_filters(
        args.collection, tags_sort=args.tags_sort, search=args.search
    )
    if args.json:
        output.emit_json(filters)
        return 0
    for key in ("broken", "duplicates", "important", "notag"):
        raw = filters.get(key)
        # The API documents these as {"count": N} objects, but some responses
        # carry the bare integer; both are fine to print.
        count = raw.get("count") if isinstance(raw, dict) else raw
        if count is not None:
            print(f"  {output.color(key + ':', 'muted')} {count}")
    types = filters.get("types") or []
    if types:
        print(output.color("types:", "muted"))
        for t in types:
            print(f"    {t.get('_id')}: {t.get('count', 0)}")
    tags = filters.get("tags") or []
    if tags:
        print(output.color("top tags:", "muted"))
        for t in tags[:20]:
            print(f"    #{t.get('_id')}: {t.get('count', 0)}")
    return 0


def cmd_suggest(client: RaindropClient, args: Any) -> int:
    if args.id is not None:
        item = client.suggest_existing(args.id)
    else:
        item = client.suggest_new(args.url)
    if args.json:
        output.emit_json(item)
        return 0
    collections = [c.get("$id") for c in item.get("collections", [])]
    tags = item.get("tags", [])
    print(output.color("collections:", "muted"), ", ".join(map(str, collections)))
    print(output.color("tags:", "muted"), " ".join(f"#{t}" for t in tags))
    return 0


def cmd_exists(client: RaindropClient, args: Any) -> int:
    result = client.check_urls_exist(args.urls)
    if args.json:
        output.emit_json(result)
        return 0
    ids = result.get("ids", [])
    if ids:
        output.success(f"already saved (ids: {', '.join(map(str, ids))})")
    else:
        print("not saved")
    return 0


# -- backups ------------------------------------------------------------------


def cmd_backups_list(client: RaindropClient, args: Any) -> int:
    items = client.get_backups()

    def render() -> str:
        return "\n".join(
            f"{output.color(b.get('_id'), 'id')}  {b.get('created')}" for b in items
        )

    return _rendered(args, items, render, empty="no backups found")


def cmd_backups_create(client: RaindropClient, args: Any) -> int:
    client.generate_backup()
    return _out(
        args,
        {"requested": True},
        "backup requested; Raindrop will email the export when ready",
    )


def cmd_backups_download(client: RaindropClient, args: Any) -> int:
    data = client.download_backup(args.id, args.format)
    path = args.output or f"raindrop-backup-{args.id}.{args.format}"
    with open(path, "wb") as fh:
        fh.write(data)
    return _out(
        args, {"path": path, "bytes": len(data)}, f"wrote {len(data)} bytes to {path}"
    )


# -- pinboard -----------------------------------------------------------------


def cmd_pb_list(client: PinboardClient, args: Any) -> int:
    tags = args.tag or None
    if getattr(args, "all", False):
        items = client.get_all(tags=tags)
    else:
        items = client.get_recent(tags=tags, count=args.count)
    if args.toread:
        items = [p for p in items if p.get("toread") == "yes"]
    return _rendered(
        args,
        items,
        lambda: "\n".join(
            output.format_pinboard_post(post, detailed=args.detailed) for post in items
        ),
        empty="no bookmarks found",
    )


def cmd_pb_get(client: PinboardClient, args: Any) -> int:
    post = client.get_post(args.url)
    # Missing URL is a failure in both modes; JSON still emits a document
    # (the empty object) so scripts can parse the answer either way.
    if args.json:
        output.emit_json(post or {})
        return 0 if post else 1
    if not post:
        output.error(f"not saved: {args.url}")
        return 1
    print(output.format_pinboard_post(post, detailed=True))
    return 0


def cmd_pb_add(client: PinboardClient, args: Any) -> int:
    client.add_post(
        args.url,
        args.title or args.url,
        extended=args.extended or "",
        tags=args.tags,
        dt=args.dt or "",
        replace=not args.no_replace,
        shared=_tristate(args.shared, args.private),
        toread=True if args.toread else None,
    )
    return _out(args, {"result": "done", "url": args.url}, f"added {args.url}")


def cmd_pb_rm(client: PinboardClient, args: Any) -> int:
    client.delete_post(args.url)
    return _out(args, {"result": "done", "url": args.url}, f"deleted {args.url}")


def cmd_pb_edit(client: PinboardClient, args: Any) -> int:
    client.edit_post(
        args.url,
        title=args.title,
        extended=args.extended,
        tags=args.tags,
        shared=_tristate(args.shared, args.private),
        toread=_tristate(args.toread, args.not_toread),
    )
    return _out(args, {"result": "done", "url": args.url}, f"edited {args.url}")


def cmd_pb_tag(client: PinboardClient, args: Any) -> int:
    add = args.add or []
    remove = set(args.remove or [])
    if not (add or remove or args.clear):
        return _fail(args, "nothing to do: pass --add, --remove, or --clear")
    post = client.get_post(args.url)
    if post is None:
        return _fail(args, f"not saved: {args.url}")
    current = [] if args.clear else (post.get("tags") or "").split()
    merged = [t for t in current if t not in remove]
    for t in add:
        if t not in merged:
            merged.append(t)
    client.edit_post(args.url, tags=merged)
    return _out(args, {"result": "done", "tags": merged}, f"updated tags on {args.url}")


def cmd_pb_suggest(client: PinboardClient, args: Any) -> int:
    suggestions = client.suggest_tags(args.url)
    if args.json:
        output.emit_json(suggestions)
        return 0
    print(
        output.color("popular:", "muted"),
        " ".join(f"#{t}" for t in suggestions.get("popular", [])),
    )
    print(
        output.color("recommended:", "muted"),
        " ".join(f"#{t}" for t in suggestions.get("recommended", [])),
    )
    return 0


def cmd_pb_tags_list(client: PinboardClient, args: Any) -> int:
    tags = client.get_tags()
    return _rendered(
        args, tags, lambda: output.format_pinboard_tags(tags), empty="no tags found"
    )


def cmd_pb_tags_rename(client: PinboardClient, args: Any) -> int:
    client.rename_tag(args.old, args.new)
    return _out(args, {"result": "done"}, f"renamed #{args.old} to #{args.new}")


def cmd_pb_tags_rm(client: PinboardClient, args: Any) -> int:
    for tag in args.tags:
        client.delete_tag(tag)
    return _out(
        args,
        {"result": "done"},
        f"deleted tag(s): {', '.join('#' + t for t in args.tags)}",
    )


def cmd_pb_notes_list(client: PinboardClient, args: Any) -> int:
    notes = client.list_notes()
    return _rendered(
        args,
        notes,
        lambda: "\n".join(output.format_note_line(note) for note in notes),
        empty="no notes found",
    )


def cmd_pb_notes_view(client: PinboardClient, args: Any) -> int:
    note = client.get_note(args.id)
    if args.json:
        output.emit_json(note)
        return 0
    print(output.color(note.get("title") or "(untitled)", "title"))
    print(note.get("text", ""))
    return 0


def cfg_set_pinboard_token(client: Any, args: Any) -> int:
    path = config.write_pinboard_token(args.token)
    return _out(args, {"path": str(path)}, f"pinboard token saved to {path}")


# -- sync (raindrop <-> pinboard) ---------------------------------------------


def cmd_sync(client: Any, args: Any) -> int:
    """Two-way additive sync. Reads both services, builds a plan, prints it, and
    (unless --dry-run) applies it. Needs both tokens."""
    rd = RaindropClient(config.resolve_token())
    pb = PinboardClient(config.resolve_pinboard_token())

    raindrops = list(rd.iter_raindrops(0))
    pb_posts = pb.get_all()
    colls = rd.get_collections() + rd.get_child_collections()
    title_by_id = {c["_id"]: c.get("title", "") for c in colls}
    id_by_slug = {sync._slug(c.get("title", "")): c["_id"] for c in colls}

    # Scope predicates: narrow WHAT is pushed; matching still uses the full sets.
    collections = set(args.collection or [])
    rd_tags = set(args.rd_tag or [])
    pb_tags = set(args.pb_tag or [])

    def rd_keep(r: dict) -> bool:
        if collections and (r.get("collection") or {}).get("$id") not in collections:
            return False
        if rd_tags and not (rd_tags & set(r.get("tags") or [])):
            return False
        return True

    def pb_keep(p: dict) -> bool:
        if pb_tags and not (pb_tags & set((p.get("tags") or "").split())):
            return False
        return True

    plan = sync.plan_sync(
        raindrops, pb_posts, title_by_id, id_by_slug, rd_keep=rd_keep, pb_keep=pb_keep
    )

    # Direction limits which side actually gets written.
    if args.direction == "to-pinboard":
        plan.to_raindrop = []
        for mrg in plan.merges:
            mrg["rd_changed"] = False
    elif args.direction == "to-raindrop":
        plan.to_pinboard = []
        for mrg in plan.merges:
            mrg["pb_changed"] = False
    plan.merges = [m for m in plan.merges if m["rd_changed"] or m["pb_changed"]]

    # --json is a single-document contract, so the human plan lines are
    # guarded off in JSON mode: --json --dry-run shows the plan as the
    # document itself, and a real --json run reports the applied counts.
    if args.json and args.dry_run:
        output.emit_json(
            {
                "to_pinboard": plan.to_pinboard,
                "to_raindrop": plan.to_raindrop,
                "merges": len(plan.merges),
                "rd_dupes": plan.rd_dupes,
                "pb_dupes": plan.pb_dupes,
            }
        )
        return 0

    if not args.json:
        m = output.color
        print(f"{m('raindrop -> pinboard (new):', 'muted')} {len(plan.to_pinboard)}")
        print(f"{m('pinboard -> raindrop (new):', 'muted')} {len(plan.to_raindrop)}")
        print(f"{m('already on both (merge):', 'muted')} {len(plan.merges)}")
        if plan.rd_dupes or plan.pb_dupes:
            print(
                f"{m('near-dupes collapsed:', 'muted')} "
                f"raindrop {plan.rd_dupes}, pinboard {plan.pb_dupes}"
            )
        if args.dry_run:
            output.success(f"dry run: {plan.total} change(s) planned, none applied")
            return 0

    counts = sync.apply_plan(plan, rd, pb)
    return _out(
        args,
        counts,
        f"synced: +{counts['added_pinboard']} to pinboard, "
        f"+{counts['added_raindrop']} to raindrop, {counts['merged']} merged",
    )


# -- config -------------------------------------------------------------------


def cmd_completion(client: Any, args: Any) -> int:
    """Print the completion script for a shell.

    Imported lazily and built from the live parser, so the output can never drift
    from the commands this build actually has. (Lazy because ``commands`` is
    imported by ``cli`` first: an eager import would close the
    cli -> commands -> cli cycle with a partial module.)
    """
    from . import cli, completion

    if args.json:
        # A completion script is shell code by definition; there is no JSON
        # document to emit, so refuse instead of silently ignoring --json.
        return _fail(args, "completion emits a shell script; --json is not supported")
    print(completion.generate(args.shell, cli.build_parser()), end="")
    return 0


def cfg_path(client: Any, args: Any) -> int:
    # The effective path: a pre-rename install still reading ~/.config/rd-cli
    # sees where its tokens actually live, not where the next write would go.
    path = str(config.effective_config_path())
    if args.json:
        output.emit_json({"path": path})
        return 0
    print(path)
    return 0


def cfg_show(client: Any, args: Any) -> int:
    data = dict(config.read_config())
    # Mask every secret, not just the Raindrop token (pinboard_token too).
    for key, value in data.items():
        if "token" in key and isinstance(value, str):
            data[key] = _mask(value)
    if args.json:
        output.emit_json(data)
        return 0
    if not data:
        print(f"(no config at {config.effective_config_path()})")
        return 0
    for key, value in data.items():
        print(f"{key} = {value}")
    return 0


def cfg_set_token(client: Any, args: Any) -> int:
    path = config.write_token(args.token)
    return _out(args, {"path": str(path)}, f"token saved to {path}")


# -- helpers ------------------------------------------------------------------


def _tristate(true_flag: bool, false_flag: bool) -> bool | None:
    """Map a pair of ``--x`` / ``--no-x`` flags to ``True``/``False``/``None``."""
    if true_flag:
        return True
    if false_flag:
        return False
    return None


def _mask(token: str) -> str:
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}…{token[-4:]}"


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _read_file(path: str) -> tuple[str, bytes, str]:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return p.name, p.read_bytes(), mime


def _flatten_bookmarks(groups: list[dict]) -> list[dict]:
    """Flatten the nested folders/bookmarks tree from ``parse_import_file``."""
    out: list[dict] = []

    def walk(node: dict) -> None:
        out.extend(node.get("bookmarks") or [])
        for folder in node.get("folders") or []:
            walk(folder)

    for group in groups:
        walk(group)
    return out
