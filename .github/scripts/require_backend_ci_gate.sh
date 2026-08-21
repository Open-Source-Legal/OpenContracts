#!/usr/bin/env bash
#
# ADD a REQUIRED status check to a protected branch — `backend-ci-gate` by
# default, any context via CONTEXT=.
#
# This is the governance half of the `gate` job in backend.yml. Merging that
# job changes nothing by itself — a check only gates a merge once branch
# protection names it.
#
# It ADDS: the new context is unioned into whatever the branch already
# requires, so running this a second time with a different CONTEXT (which is
# exactly what docs/development/test-suite.md tells you to do when another
# workflow grows its own gate) does not unrequire the first one. `strict` and
# every other protection setting are read back and re-sent unchanged.
#
# Why this is a script and not a one-line `gh api` in a README:
#
#   * `PUT /repos/{o}/{r}/branches/{b}/protection` REPLACES THE ENTIRE
#     protection object. Sending just `required_status_checks` silently drops
#     `required_pull_request_reviews`, `allow_force_pushes: false`,
#     `allow_deletions: false` and everything else currently set. So the
#     current object has to be read back and re-sent with the new key merged
#     in — which is what branch_protection_body.py does.
#   * The narrower `PATCH .../protection/required_status_checks` sub-resource
#     is not usable to CREATE the object: it 404s with "Required status checks
#     not enabled" when none exists yet.
#   * A required context is matched BYTE-FOR-BYTE against the check-run name.
#     Requiring a name that is never reported blocks every PR forever, with no
#     error anywhere. The preflight below refuses to do that.
#
# Usage:
#   require_backend_ci_gate.sh              # dry run: print the PUT body, change nothing
#   require_backend_ci_gate.sh --apply      # actually apply it
#   require_backend_ci_gate.sh --self-test  # exercise the merge logic, touch nothing
#
# Env: REPO, BRANCH, CONTEXT override the defaults below.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPO="${REPO:-Open-Source-Legal/OpenContracts}"
BRANCH="${BRANCH:-main}"
CONTEXT="${CONTEXT:-backend-ci-gate}"

APPLY=0
if [ "${1:-}" = "--apply" ]; then
    APPLY=1
elif [ "${1:-}" = "--self-test" ]; then
    exec python3 "$HERE/branch_protection_body.py" --self-test
elif [ -n "${1:-}" ]; then
    echo "usage: $0 [--apply|--self-test]" >&2
    exit 2
fi

# --- Preflight: has this context ever actually been reported? ---------------
# Requiring a name no workflow produces is the single worst outcome here: every
# PR hangs Pending, permanently, and nothing logs a reason. Look for the name
# on recent commits of the branch before trusting it.
echo "Preflight: looking for a check run named '$CONTEXT' on recent $BRANCH commits..."
found=0
for sha in $(gh api "repos/$REPO/commits?sha=$BRANCH&per_page=15" -q '.[].sha'); do
    if gh api "repos/$REPO/commits/$sha/check-runs" -q '.check_runs[].name' 2>/dev/null |
        grep -Fxq "$CONTEXT"; then
        echo "  found on ${sha:0:9}"
        found=1
        break
    fi
done

if [ "$found" -ne 1 ]; then
    echo >&2
    echo "REFUSING: no check run named '$CONTEXT' found on the last 15 commits of $BRANCH." >&2
    echo "The gate job must be merged to $BRANCH and have run at least once first," >&2
    echo "otherwise requiring this context blocks every pull request indefinitely." >&2
    exit 1
fi

# --- Build the replacement object from the CURRENT one ----------------------
current="$(gh api "repos/$REPO/branches/$BRANCH/protection")"

body="$(CONTEXT="$CONTEXT" python3 "$HERE/branch_protection_body.py" <<<"$current")"

echo
echo "--- PUT repos/$REPO/branches/$BRANCH/protection ---"
echo "$body"
echo

if [ "$APPLY" -ne 1 ]; then
    echo "Dry run — nothing changed. Re-run with --apply to write this."
    exit 0
fi

gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" --input - <<<"$body" >/dev/null
echo "Applied. Verifying..."
gh api "repos/$REPO/branches/$BRANCH/protection/required_status_checks"
