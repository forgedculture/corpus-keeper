# Corpus Keeper

Your AI is only as good as the folder you point it at. Corpus Keeper
keeps that folder honest.

Every team wiring an AI assistant into their documents is accruing the
same disease: context rot. The old price sheet that still looks
current. The plan that was cancelled in a meeting but not in writing.
Two docs that disagree about the same fact. The AI cannot tell which
one is true, so it picks one - with total confidence. The failure gets
blamed on the AI. The cause is the corpus.

Corpus Keeper is a zero-dependency auditor and governance scaffold for
any folder of documents that you, your team, or your AI treats as
ground truth.

## Try it in sixty seconds

    git clone https://github.com/forgedculture/corpus-keeper
    cd corpus-keeper
    python3 corpus_keeper.py audit demo_corpus

You will see 6 findings: two broken links, a non-ASCII character, a
phantom index entry, an unindexed file, and a deprecated document with
no pointer to its replacement. Then open `demo_corpus/pricing_2025.md`
and `demo_corpus/pricing_current.md`: both claim to be quotable
pricing, and they disagree on every number. That seventh defect is the
kind a script cannot catch - see "The semantic layer" below.

## What it checks

Mechanical rot, on every run: broken relative links, non-ASCII bytes
(optional), index drift (files missing from your index, index entries
pointing at nothing), and stale markers (SUPERSEDED, DEPRECATED) with
no pointer to current truth.

Exit codes are the contract: 0 clean, 1 findings, 2 error. It drops
into a script, cron job, or CI unchanged.

## Bring your own folder under management

    python3 corpus_keeper.py init /path/to/your/folder
    python3 corpus_keeper.py audit /path/to/your/folder

`init` scaffolds the governance layer: GOVERNANCE.md (the rules),
CORPUS_INDEX.md (the map), a numbered decision-record template, and an
append-only decisions log. Existing files are never overwritten.

The rules in one breath: one current truth at a time, decisions get
records, logs are append-only, the index is the map, audit after every
edit.

## The semantic layer

The auditor catches rot of form. Rot of meaning - contradictions
between documents, a stale doc that still looks current, a change
nobody recorded a decision for - needs a reader. The Corpus Keeper
kit wires your AI assistant to do that pass: a Claude skill, a
ChatGPT Custom GPT setup, and an AGENTS.md for Codex, Cursor, Gemini
CLI, and Copilot, plus governance templates and support.

The kit, and the methodology behind it, live at
[forgedculture.com](https://forgedculture.com).

## Requirements and license

Python 3.8+, standard library only. Apache 2.0 (see LICENSE).
Configuration via `.corpuskeeper.json` (written by `init`): index
filename, ASCII policy, exclude patterns, document extensions.

Maintainers: run `./check.sh` before committing; CI runs the same
script.
