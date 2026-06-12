#!/usr/bin/env python3
# Corpus Keeper core. License: Apache-2.0 (see LICENSE in the public
# repository). The assistant adapter layer (Claude skill, ChatGPT
# setup, AGENTS.md, the --engine switcher) is part of the paid kit:
# https://forgedculture.com
"""Corpus Keeper core: keep a knowledge corpus correct, navigable, honest.

A standalone auditor and scaffolder for any folder of documents that an
AI agent (or a human) treats as ground truth. No dependencies beyond the
Python 3.8+ standard library.

Commands:
  init  [path]   Scaffold base governance files into a folder.
  audit [path]   Run mechanical hygiene checks and report findings.

Exit codes: 0 = clean, 1 = findings, 2 = usage or runtime error.
"""

import argparse
import fnmatch
import json
import os
import re
import sys

CONFIG_NAME = ".corpuskeeper.json"

DEFAULT_CONFIG = {
    "index": "CORPUS_INDEX.md",
    "ascii": True,
    "exclude": [".git", ".obsidian", ".claude", "node_modules",
                "__pycache__", "*.zip", ".DS_Store", "demo_corpus"],
    "doc_extensions": [".md", ".pdf", ".csv", ".tsv", ".docx", ".xlsx"],
}

# A document is "marked stale" only when the marker is the point of the
# line: an uppercase line-start tag, a heading, or a Status field.
# Prose that merely mentions the convention is not flagged.
STALE_LINESTART = re.compile(
    r"^\s*\**\s*(SUPERSEDED|DEPRECATED|OUTDATED|OBSOLETE)\b")
STALE_CONTEXT = re.compile(
    r"^\s*(?:#+\s*.*|status\s*[:=]\s*.*)"
    r"\b(superseded|deprecated|outdated|obsolete)\b",
    re.IGNORECASE)


def marked_stale(line):
    return bool(STALE_LINESTART.match(line) or STALE_CONTEXT.match(line))


INFO_MARKERS = re.compile(r"\b(TODO|TBD|FIXME)\b")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)#?\s]+)[^)]*\)")
TICK_PATH = re.compile(r"`([^`\n]+)`")


def load_config(root):
    cfg = dict(DEFAULT_CONFIG)
    path = os.path.join(root, CONFIG_NAME)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                user = json.load(fh)
            for key in DEFAULT_CONFIG:
                if key in user:
                    cfg[key] = user[key]
        except (OSError, ValueError) as exc:
            sys.stderr.write("warning: could not read %s (%s); "
                             "using defaults\n" % (CONFIG_NAME, exc))
    return cfg


def excluded(rel_path, patterns):
    parts = rel_path.replace(os.sep, "/").split("/")
    for pat in patterns:
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
        if fnmatch.fnmatch(rel_path.replace(os.sep, "/"), pat):
            return True
    return False


def walk_files(root, cfg):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
        dirnames[:] = [d for d in dirnames
                       if not excluded(os.path.join(rel_dir, d), cfg["exclude"])]
        for name in filenames:
            rel = os.path.join(rel_dir, name) if rel_dir else name
            if not excluded(rel, cfg["exclude"]):
                yield rel


def looks_like_path(text, doc_exts):
    if text.startswith(("http://", "https://", "mailto:")):
        return False
    if "/" not in text and not text.endswith(tuple(doc_exts)):
        return False
    if any(ch in text for ch in " <>|"):
        return False
    return text.endswith(tuple(doc_exts)) or text.endswith("/")


def check_links(root, md_files, cfg, findings):
    for rel in md_files:
        full = os.path.join(root, rel)
        try:
            text = open(full, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            findings.append({"check": "links", "file": rel,
                             "detail": "unreadable: %s" % exc})
            continue
        base = os.path.dirname(full)
        candidates = set(MD_LINK.findall(text))
        for tick in TICK_PATH.findall(text):
            if looks_like_path(tick, cfg["doc_extensions"]):
                candidates.add(tick)
        for cand in sorted(candidates):
            if cand.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = os.path.normpath(os.path.join(base, cand))
            if not os.path.exists(target):
                findings.append({"check": "links", "file": rel,
                                 "detail": "broken link -> %s" % cand})


def check_ascii(root, md_files, findings):
    for rel in md_files:
        try:
            raw = open(os.path.join(root, rel), "rb").read()
            raw.decode("ascii")
        except UnicodeDecodeError as exc:
            findings.append({"check": "ascii", "file": rel,
                             "detail": "non-ASCII byte at offset %d" % exc.start})
        except OSError as exc:
            findings.append({"check": "ascii", "file": rel,
                             "detail": "unreadable: %s" % exc})


def check_index(root, all_files, cfg, findings):
    index_rel = cfg["index"]
    index_full = os.path.join(root, index_rel)
    if not os.path.exists(index_full):
        findings.append({"check": "index", "file": index_rel,
                         "detail": "index file missing; run init or create it"})
        return
    text = open(index_full, encoding="utf-8", errors="replace").read()
    mentioned = set(MD_LINK.findall(text)) | set(TICK_PATH.findall(text))
    mentioned = {m.strip("./") for m in mentioned}
    base = os.path.dirname(index_full)
    for m in sorted(mentioned):
        if m.startswith(("http://", "https://")) or not m:
            continue
        if not looks_like_path(m, cfg["doc_extensions"]):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(base, m))):
            findings.append({"check": "index", "file": index_rel,
                             "detail": "index entry has no file -> %s" % m})
    doc_exts = tuple(cfg["doc_extensions"])
    for rel in sorted(all_files):
        if not rel.endswith(doc_exts) or rel == index_rel:
            continue
        norm = rel.replace(os.sep, "/")
        if norm not in mentioned and os.path.basename(norm) not in \
                {os.path.basename(m) for m in mentioned}:
            findings.append({"check": "index", "file": norm,
                             "detail": "file not listed in %s" % index_rel})


def check_stale(root, md_files, findings, infos):
    for rel in md_files:
        try:
            lines = open(os.path.join(root, rel), encoding="utf-8",
                         errors="replace").read().splitlines()
        except OSError:
            continue
        for num, line in enumerate(lines, 1):
            if marked_stale(line) and not MD_LINK.search(line):
                findings.append({"check": "stale", "file": rel,
                                 "detail": "line %d marked stale with no "
                                           "pointer to current truth" % num})
            if INFO_MARKERS.search(line):
                infos.append({"check": "stale", "file": rel,
                              "detail": "line %d has open marker (%s)"
                                        % (num, INFO_MARKERS.search(line).group(1))})


def cmd_audit(args):
    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        sys.stderr.write("error: %s is not a directory\n" % root)
        return 2
    cfg = load_config(root)
    if args.no_ascii:
        cfg["ascii"] = False
    if args.exclude:
        cfg["exclude"] = list(cfg["exclude"]) + args.exclude
    all_files = list(walk_files(root, cfg))
    md_files = [f for f in all_files if f.endswith(".md")]
    findings, infos = [], []
    check_links(root, md_files, cfg, findings)
    if cfg["ascii"]:
        check_ascii(root, md_files, findings)
    check_index(root, all_files, cfg, findings)
    check_stale(root, md_files, findings, infos)
    if args.as_json:
        print(json.dumps({"root": root, "files_scanned": len(all_files),
                          "findings": findings, "info": infos}, indent=2))
    else:
        for f in findings:
            print("FINDING [%s] %s: %s" % (f["check"], f["file"], f["detail"]))
        for i in infos:
            print("info    [%s] %s: %s" % (i["check"], i["file"], i["detail"]))
        print("scanned %d files: %d findings, %d info"
              % (len(all_files), len(findings), len(infos)))
    return 1 if findings else 0


SCAFFOLD_BASE = {
    "GOVERNANCE.md": """# Governance

Rules that keep this corpus honest. Read before editing anything.

## One current truth

At any time, exactly one document governs each question. Current-truth
documents are listed in `CORPUS_INDEX.md` under Current. Everything else
is historical record: keep it, never let it silently govern action.
When truth changes, update the current document, mark the old
one as SUPERSEDED with a link to its replacement, and record
a decision.

## Decisions get records

Any decision you would be annoyed to re-litigate in six months gets a
decision record in `decisions/`, numbered sequentially, using
`decisions/0000-decision-template.md`. Status is Proposed or Accepted.

## Logs are append-only

`log/decisions_log.md` is append-only. Never rewrite history to fix a
stale path; append a pointer note instead.

## Authoring rules

- Relative links must resolve from the file that holds them.
- Keep in-use documents in Markdown so both humans and AI can read them.
- Optional: ASCII only (set "ascii" in `.corpuskeeper.json`).

## After any edit

Run `corpus_keeper.py audit .` and clear the findings. If you added,
moved, or removed a file, update `CORPUS_INDEX.md`. If it was a
decision, append to `log/decisions_log.md`.
""",
    "decisions/0000-decision-template.md": """# DR-0000: Template

## Status

Proposed

## Date

YYYY-MM-DD

## Context

Describe the decision pressure, constraints, facts, and alternatives.

## Decision

State the decision plainly.

## Consequences

Describe expected benefits, costs, risks, and follow-up work.

## Verification

Describe how the decision will be checked or revisited.
""",
    "log/decisions_log.md": """# Decisions log (append-only)

| Date | Decision | Record |
|------|----------|--------|
""",
}

INDEX_HEADER = ["# Corpus Index", "",
                "The map of this corpus. One line per document. Keep it "
                "current; the", "audit will flag drift.", "",
                "## Current (authoritative)", "",
                "- `GOVERNANCE.md` - the rules for editing this corpus"]

INDEX_FOOTER = ["", "## Decisions", "",
                "- `decisions/0000-decision-template.md` - template for "
                "decision records", "",
                "## Logs", "",
                "- `log/decisions_log.md` - append-only decision log", "",
                "## Historical", "",
                "(superseded documents move here, each linking to its "
                "replacement)", ""]


def build_index(extra_lines=None):
    return "\n".join(INDEX_HEADER + (extra_lines or []) + INDEX_FOOTER)


def write_scaffold(root, files):
    created, skipped = [], []
    for rel in sorted(files):
        full = os.path.join(root, rel)
        if os.path.exists(full):
            skipped.append(rel)
            continue
        os.makedirs(os.path.dirname(full) or root, exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(files[rel])
        created.append(rel)
    for rel in created:
        print("created %s" % rel)
    for rel in skipped:
        print("skipped %s (exists)" % rel)
    return created, skipped


def cmd_init(args):
    root = os.path.abspath(args.path)
    os.makedirs(root, exist_ok=True)
    files = dict(SCAFFOLD_BASE)
    files["CORPUS_INDEX.md"] = build_index()
    files[CONFIG_NAME] = json.dumps(DEFAULT_CONFIG, indent=2) + "\n"
    write_scaffold(root, files)
    print("Scaffold complete. Next: corpus_keeper.py audit %s" % args.path)
    return 0


def build_parser(init_func):
    parser = argparse.ArgumentParser(prog="corpus_keeper",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="scaffold governance files")
    p_init.add_argument("path", nargs="?", default=".")
    p_init.set_defaults(func=init_func)
    p_audit = sub.add_parser("audit", help="run hygiene checks")
    p_audit.add_argument("path", nargs="?", default=".")
    p_audit.add_argument("--json", dest="as_json", action="store_true",
                         help="emit JSON instead of text")
    p_audit.add_argument("--no-ascii", action="store_true",
                         help="skip the ASCII check")
    p_audit.add_argument("--exclude", action="append",
                         help="extra exclude pattern (repeatable)")
    p_audit.set_defaults(func=cmd_audit)
    return parser, p_init


def main(argv=None):
    parser, _ = build_parser(cmd_init)
    args = parser.parse_args(argv)
    return args.func(args)


# === end of core (kit extension appends below this marker) ===

if __name__ == "__main__":
    sys.exit(main())
