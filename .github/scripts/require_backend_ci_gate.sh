#!/usr/bin/env bash
#
# Make `backend-ci-gate` a REQUIRED status check on a protected branch.
#
# This is the governance half of the `gate` job in backend.yml. Merging that
# job changes nothing by itself — a check only gates a merge once branch
# protection names it.
#
# Why this is a script and not a one-line `gh api` in a README:
#
#   * `PUT /repos/{o}/{r}/branches/{b}/protection` REPLACES THE ENTIRE
#     protection object. Sending just `required_status_checks` silently drops
#     `required_pull_request_reviews`, `allow_force_pushes: false`,
#     `allow_deletions: false` and everything else currently set. So the
#     current object has to be read back and re-sent with the new key merged
#     in — which is what this does.
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
#
# Env: REPO, BRANCH, CONTEXT override the defaults below.

set -euo pipefail

REPO="${REPO:-Open-Source-Legal/OpenContracts}"
BRANCH="${BRANCH:-main}"
CONTEXT="${CONTEXT:-backend-ci-gate}"

APPLY=0
if [ "${1:-}" = "--apply" ]; then
    APPLY=1
elif [ -n "${1:-}" ]; then
    echo "usage: $0 [--apply]" >&2
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

body="$(CONTEXT="$CONTEXT" python3 -c '
import json, os, sys

cur = json.load(sys.stdin)


def enabled(key):
    return bool(cur.get(key, {}).get("enabled", False))


# The four nullable-but-required keys of the PUT body, plus every optional
# flag currently set, so nothing is lost in the round trip.
out = {
    "required_status_checks": {
        # strict=false: do NOT force every PR to be rebased onto the tip of
        # the branch before merging. strict=true serialises all merges and
        # is a much larger behavioural change than adding a gate.
        "strict": False,
        "checks": [{"context": os.environ["CONTEXT"]}],
    },
    "enforce_admins": enabled("enforce_admins"),
    "required_pull_request_reviews": None,
    "restrictions": None,
    "required_linear_history": enabled("required_linear_history"),
    "allow_force_pushes": enabled("allow_force_pushes"),
    "allow_deletions": enabled("allow_deletions"),
    "block_creations": enabled("block_creations"),
    "required_conversation_resolution": enabled("required_conversation_resolution"),
    "lock_branch": enabled("lock_branch"),
    "allow_fork_syncing": enabled("allow_fork_syncing"),
}

rpr = cur.get("required_pull_request_reviews")
if rpr is not None:
    out["required_pull_request_reviews"] = {
        "dismiss_stale_reviews": rpr.get("dismiss_stale_reviews", False),
        "require_code_owner_reviews": rpr.get("require_code_owner_reviews", False),
        "require_last_push_approval": rpr.get("require_last_push_approval", False),
        "required_approving_review_count": rpr.get("required_approving_review_count", 0),
    }

restrictions = cur.get("restrictions")
if restrictions is not None:
    out["restrictions"] = {
        "users": [u["login"] for u in restrictions.get("users", [])],
        "teams": [t["slug"] for t in restrictions.get("teams", [])],
        "apps": [a["slug"] for a in restrictions.get("apps", [])],
    }

json.dump(out, sys.stdout, indent=2)
' <<<"$current")"

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
