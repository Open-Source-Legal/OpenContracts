#!/usr/bin/env bash
#
# Backend CI's aggregate gate — the one check branch protection requires.
#
# WHY THIS EXISTS, since "just require the pytest job" is the obvious answer
# and it does not work. Both of the direct alternatives fail, in opposite
# directions:
#
#   1. Requiring `pytest` lets a red linter through. GitHub reports a job that
#      its own `if:` skipped as SUCCESS to branch protection ("if a job within
#      a workflow is skipped due to a conditional, it will report its status
#      as Success"). Backend CI's `pytest` is gated on
#      `needs.linter.result == 'success'`, so a red linter SKIPS pytest — and
#      a required `pytest` check reads green for it. Measured, not theorised:
#      when this was written, PRs #2260, #2264 and #2265 were all sitting at
#      `linter=failure / pytest=skipped` and would have been mergeable.
#
#   2. Requiring `pytest` while the workflow carries a workflow-level path
#      filter deadlocks every PR the filter excludes. A workflow skipped by
#      path filtering never reports at all, and the required check hangs
#      Pending forever — an unmergeable docs-only PR.
#
# So the requirable check has to be a job that ALWAYS runs and that inspects
# the other jobs' results itself, distinguishing "skipped because this PR
# genuinely touches no backend code" from "skipped because something upstream
# broke". That distinction is this script.
#
# Usage:
#   backend_ci_gate.sh <event> <backend> <linter> <pytest>
#   backend_ci_gate.sh --self-test
#
#   event    github.event_name          e.g. pull_request | push
#   backend  needs.changes.outputs.backend  'true' | 'false' | '' (job skipped
#            on push, or errored — it is `continue-on-error`, and Backend CI
#            deliberately fails open there)
#   linter   needs.linter.result        success | failure | cancelled | skipped
#   pytest   needs.pytest.result        success | failure | cancelled | skipped
#
# Exits 0 to allow the merge, 1 to block it.

set -euo pipefail

# Decide whether the observed job results are acceptable. Echoes a one-line
# explanation either way; returns 0 (allow) or 1 (block).
evaluate() {
    local event="$1" backend="$2" linter="$3" pytest="$4"

    # The only legitimate reason for the backend jobs not to have run: this is
    # a PR and the path filter found no backend files in it. Note this is
    # deliberately keyed on the literal 'false'. An empty value means the
    # `changes` job was skipped (push events) or errored, and Backend CI's
    # own `if:` conditions fail OPEN there and run the jobs anyway — so an
    # empty value must fall through to the strict branch below, not here.
    if [ "$event" = "pull_request" ] && [ "$backend" = "false" ]; then
        # Defensive: under the current workflow both jobs are skipped in this
        # case. If either somehow ran and failed, that is still a failure —
        # do not let the path filter launder it.
        if [ "$linter" = "failure" ] || [ "$linter" = "cancelled" ] ||
            [ "$pytest" = "failure" ] || [ "$pytest" = "cancelled" ]; then
            echo "BLOCK: no backend files changed, but linter=$linter pytest=$pytest"
            return 1
        fi
        echo "ALLOW: no backend files changed (linter=$linter pytest=$pytest)"
        return 0
    fi

    # Everything else — any push, and any PR that touches backend paths or
    # whose path filter could not be trusted — must have actually run both
    # jobs to completion. `skipped` is a failure here; that is the whole
    # point of the gate.
    if [ "$linter" != "success" ]; then
        echo "BLOCK: linter=$linter (expected success)"
        return 1
    fi
    if [ "$pytest" != "success" ]; then
        echo "BLOCK: pytest=$pytest (expected success)"
        return 1
    fi

    echo "ALLOW: linter=success pytest=success"
    return 0
}

# Prove the gate can fail. Every row is a state Backend CI can actually
# produce; the rows marked BLOCK are the ones a naive `required: pytest`
# would have waved through.
self_test() {
    local failures=0 rc=0 out=""

    # want  event         backend  linter     pytest    # what it is
    local cases=(
        "ALLOW pull_request false     skipped   skipped"   # docs/frontend-only PR
        "ALLOW pull_request true      success   success"   # ordinary green PR
        "BLOCK pull_request true      failure   skipped"   # <- the #2262 hole
        "BLOCK pull_request true      success   skipped"   # pytest skipped silently
        "BLOCK pull_request true      success   failure"   # tests genuinely failed
        "BLOCK pull_request true      cancelled skipped"   # run cancelled
        "ALLOW pull_request ''        success   success"   # changes errored, fail-open, jobs ran
        "BLOCK pull_request ''        failure   skipped"   # changes errored AND linter red
        "ALLOW push         ''        success   success"   # ordinary green push to main
        "BLOCK push         ''        failure   skipped"   # <- the #2262 merge commit
        "BLOCK push         ''        success   skipped"   # pytest skipped on a push
        "BLOCK pull_request false     failure   skipped"   # defensive: ran anyway, failed
        "BLOCK pull_request false     skipped   failure"   # defensive: ran anyway, failed
    )

    for row in "${cases[@]}"; do
        # shellcheck disable=SC2086
        set -- $row
        local want="$1" event="$2" backend="$3" linter="$4" pytest="$5"
        [ "$backend" = "''" ] && backend=""

        rc=0
        out="$(evaluate "$event" "$backend" "$linter" "$pytest")" || rc=$?

        local got="ALLOW"
        [ "$rc" -ne 0 ] && got="BLOCK"

        if [ "$got" != "$want" ]; then
            echo "FAIL  want=$want got=$got  [$event backend='$backend' linter=$linter pytest=$pytest] -> $out"
            failures=$((failures + 1))
        else
            echo "ok    $want  [$event backend='$backend' linter=$linter pytest=$pytest]"
        fi
    done

    if [ "$failures" -ne 0 ]; then
        echo "self-test: $failures case(s) failed"
        return 1
    fi
    echo "self-test: ${#cases[@]}/${#cases[@]} cases passed"
    return 0
}

main() {
    if [ "${1:-}" = "--self-test" ]; then
        self_test
        return $?
    fi

    if [ "$#" -ne 4 ]; then
        echo "usage: $0 <event> <backend> <linter> <pytest>" >&2
        echo "       $0 --self-test" >&2
        return 2
    fi

    evaluate "$1" "$2" "$3" "$4"
}

main "$@"
