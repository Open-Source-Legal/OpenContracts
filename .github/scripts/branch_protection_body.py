"""Build the PUT body that adds a required status check to a protected branch.

``PUT /repos/{owner}/{repo}/branches/{branch}/protection`` replaces the ENTIRE
protection object, so the only safe way to add one required check is to read
the current object back and re-send it with the new context merged in. This
module is that merge, kept separate from ``require_backend_ci_gate.sh`` so it
can be self-tested without touching a live repository.

Two things it must not do, both of which are silent when wrong:

* **Replace the checks list.** Adding ``frontend-ci-gate`` must not remove
  ``backend-ci-gate``. The first version of this code assigned
  ``"checks": [{"context": CONTEXT}]`` outright, which meant the documented
  way to require a second workflow would have quietly unrequired the first.
* **Reset unrelated settings.** ``strict``, the review rules, the
  force-push/deletion bans and any push restrictions all have to survive the
  round trip untouched.

Usage:
    CONTEXT=backend-ci-gate python3 branch_protection_body.py < current.json
    python3 branch_protection_body.py --self-test
"""

from __future__ import annotations

import json
import os
import sys


def _enabled(current: dict, key: str) -> bool:
    """Read one of the ``{"enabled": bool}`` sub-objects the GET returns."""
    value = current.get(key)
    if isinstance(value, dict):
        return bool(value.get("enabled", False))
    return bool(value)


def _merge_checks(rsc: dict, context: str) -> list[dict]:
    """Union ``context`` into the branch's existing required checks.

    Accepts either the modern ``checks`` list or the legacy ``contexts`` list
    of bare strings, and preserves ``app_id`` where GitHub reported one (that
    field pins a check to the app allowed to report it; dropping it would
    widen the requirement to any app).
    """
    existing = rsc.get("checks")
    if existing is None:
        existing = [{"context": name} for name in rsc.get("contexts", [])]

    checks: list[dict] = []
    seen: set[str] = set()
    for entry in existing:
        name = entry.get("context")
        if not name or name in seen:
            continue
        seen.add(name)
        merged = {"context": name}
        if entry.get("app_id") is not None:
            merged["app_id"] = entry["app_id"]
        checks.append(merged)

    if context not in seen:
        checks.append({"context": context})

    return checks


def build_body(current: dict, context: str) -> dict:
    """Return the full PUT body: everything currently set, plus ``context``."""
    rsc = current.get("required_status_checks") or {}

    body: dict = {
        "required_status_checks": {
            # Preserved, not hardcoded. `strict` forces every PR to be rebased
            # onto the tip before merging, which serialises all merges — if a
            # maintainer has turned it on, re-running this must not undo it.
            "strict": bool(rsc.get("strict", False)),
            "checks": _merge_checks(rsc, context),
        },
        "enforce_admins": _enabled(current, "enforce_admins"),
        "required_pull_request_reviews": None,
        "restrictions": None,
        "required_linear_history": _enabled(current, "required_linear_history"),
        "allow_force_pushes": _enabled(current, "allow_force_pushes"),
        "allow_deletions": _enabled(current, "allow_deletions"),
        "block_creations": _enabled(current, "block_creations"),
        "required_conversation_resolution": _enabled(
            current, "required_conversation_resolution"
        ),
        "lock_branch": _enabled(current, "lock_branch"),
        "allow_fork_syncing": _enabled(current, "allow_fork_syncing"),
    }

    reviews = current.get("required_pull_request_reviews")
    if reviews is not None:
        body["required_pull_request_reviews"] = {
            "dismiss_stale_reviews": reviews.get("dismiss_stale_reviews", False),
            "require_code_owner_reviews": reviews.get(
                "require_code_owner_reviews", False
            ),
            "require_last_push_approval": reviews.get(
                "require_last_push_approval", False
            ),
            "required_approving_review_count": reviews.get(
                "required_approving_review_count", 0
            ),
        }

    restrictions = current.get("restrictions")
    if restrictions is not None:
        # The GET returns full objects; the PUT wants bare logins/slugs.
        body["restrictions"] = {
            "users": [u["login"] for u in restrictions.get("users", [])],
            "teams": [t["slug"] for t in restrictions.get("teams", [])],
            "apps": [a["slug"] for a in restrictions.get("apps", [])],
        }

    return body


def _self_test() -> int:
    """Prove the merge adds without removing, and preserves what it found."""
    failures = 0

    def check(name: str, condition: bool) -> None:
        nonlocal failures
        if condition:
            print(f"ok    {name}")
        else:
            print(f"FAIL  {name}")
            failures += 1

    # 1. Fresh branch: no required_status_checks object at all.
    fresh = build_body({}, "backend-ci-gate")
    check(
        "fresh branch gets exactly the new context",
        fresh["required_status_checks"]["checks"] == [{"context": "backend-ci-gate"}],
    )
    check(
        "fresh branch defaults strict=false",
        fresh["required_status_checks"]["strict"] is False,
    )

    # 2. THE regression this module exists for: adding a second context must
    #    not drop the first.
    existing = {
        "required_status_checks": {
            "strict": False,
            "checks": [{"context": "backend-ci-gate", "app_id": 15368}],
        }
    }
    added = build_body(existing, "frontend-ci-gate")
    contexts = [c["context"] for c in added["required_status_checks"]["checks"]]
    check(
        "adding a second context keeps the first",
        contexts == ["backend-ci-gate", "frontend-ci-gate"],
    )
    check(
        "app_id of the pre-existing check is preserved",
        added["required_status_checks"]["checks"][0].get("app_id") == 15368,
    )

    # 3. Re-running with a context already present is a no-op, not a duplicate.
    again = build_body(existing, "backend-ci-gate")
    check(
        "re-adding an existing context does not duplicate it",
        again["required_status_checks"]["checks"]
        == [{"context": "backend-ci-gate", "app_id": 15368}],
    )

    # 4. strict=true set by a maintainer must survive a re-run.
    strict_on = build_body(
        {"required_status_checks": {"strict": True, "checks": []}}, "backend-ci-gate"
    )
    check(
        "strict=true is preserved",
        strict_on["required_status_checks"]["strict"] is True,
    )

    # 5. Legacy `contexts` list (no `checks`) is migrated, not dropped.
    legacy = build_body(
        {"required_status_checks": {"strict": False, "contexts": ["old-check"]}},
        "backend-ci-gate",
    )
    legacy_contexts = [c["context"] for c in legacy["required_status_checks"]["checks"]]
    check(
        "legacy contexts list is migrated and unioned",
        legacy_contexts == ["old-check", "backend-ci-gate"],
    )

    # 6. Everything else round-trips.
    rich = {
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "require_last_push_approval": True,
            "required_approving_review_count": 2,
        },
        "enforce_admins": {"enabled": True},
        "required_linear_history": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "block_creations": {"enabled": True},
        "required_conversation_resolution": {"enabled": True},
        "lock_branch": {"enabled": False},
        "allow_fork_syncing": {"enabled": True},
        "restrictions": {
            "users": [{"login": "JSv4"}],
            "teams": [{"slug": "core"}],
            "apps": [{"slug": "dependabot"}],
        },
    }
    out = build_body(rich, "backend-ci-gate")
    check("enforce_admins preserved", out["enforce_admins"] is True)
    check(
        "review settings preserved",
        out["required_pull_request_reviews"]["required_approving_review_count"] == 2
        and out["required_pull_request_reviews"]["dismiss_stale_reviews"] is True,
    )
    check(
        "restrictions flattened to logins/slugs",
        out["restrictions"]
        == {"users": ["JSv4"], "teams": ["core"], "apps": ["dependabot"]},
    )
    check("required_linear_history preserved", out["required_linear_history"] is True)
    check("block_creations preserved", out["block_creations"] is True)
    check("allow_fork_syncing preserved", out["allow_fork_syncing"] is True)

    if failures:
        print(f"self-test: {failures} case(s) failed")
        return 1
    print("self-test: all cases passed")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()

    context = os.environ.get("CONTEXT")
    if not context:
        print("CONTEXT env var is required", file=sys.stderr)
        return 2

    json.dump(build_body(json.load(sys.stdin), context), sys.stdout, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
