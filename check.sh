#!/usr/bin/env bash
#
# corpus-keeper (public core) checks. Run locally (./check.sh) or from
# CI; both must agree. Exit 0 = green. Keep this file ASCII-only: the
# ASCII step below scans it.

set -uo pipefail
cd "$(dirname "$0")"

fail=0
report () {  # $1 = step name, $2 = return code
  if [ "$2" -eq 0 ]; then
    printf '  PASS  %s\n' "$1"
  else
    printf '  FAIL  %s\n' "$1"
    fail=1
  fi
}

# 1. Demo corpus must show exactly the planted defects.
demo_out=$(python3 corpus_keeper.py audit demo_corpus); code=$?
{ [ "$code" -eq 1 ] && grep -q "6 findings" <<<"$demo_out"; }
report "Demo corpus shows exactly the planted defects" $?

# 2. Core scaffold audits clean, and core must not accept --engine
#    (the engine switcher belongs to the kit).
core_rc=0
d="$(mktemp -d)/core"
python3 corpus_keeper.py init "$d" >/dev/null || core_rc=1
cp corpus_keeper.py "$d"/corpus_keeper.py
python3 corpus_keeper.py audit "$d" >/dev/null || core_rc=1
if python3 corpus_keeper.py init "$d" --engine all >/dev/null 2>&1; then
  core_rc=1
fi
report "Core scaffold clean; core rejects --engine" "$core_rc"

# 3. All files must be ASCII (demo corpus exempt).
python3 - <<'PY'
import glob, os, sys
bad = 0
for f in glob.glob("**/*", recursive=True):
    if not os.path.isfile(f) or "demo_corpus" in f: continue
    try: open(f, "rb").read().decode("ascii")
    except Exception: bad += 1; print("  NONASCII", f)
sys.exit(1 if bad else 0)
PY
report "Files are ASCII (demo corpus exempt)" $?

echo "------------------------------------"
if [ "$fail" -eq 0 ]; then
  echo "corpus-keeper core checks: GREEN"
else
  echo "corpus-keeper core checks: RED"
fi
exit "$fail"
