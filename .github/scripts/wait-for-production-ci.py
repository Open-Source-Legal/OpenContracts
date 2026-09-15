#!/usr/bin/env python3
"""Wait for successful push CI for the exact commit being released (no secrets)."""

import json
import os
import time
import urllib.parse
import urllib.request
from typing import TypedDict


class WorkflowRun(TypedDict):
    head_sha: str
    event: str
    head_branch: str
    run_number: int
    run_attempt: int
    status: str
    conclusion: str
    html_url: str


def check_runs(runs: list[WorkflowRun], sha: str) -> bool:
    # Reruns can supersede a prior failure; the newest run is authoritative.
    matches = [
        r
        for r in runs
        if r["head_sha"] == sha and r["event"] == "push" and r["head_branch"] == "main"
    ]
    if not matches:
        return False
    run = max(matches, key=lambda r: (r["run_number"], r.get("run_attempt", 1)))
    if run["status"] != "completed":
        return False
    if run["conclusion"] != "success":
        raise RuntimeError("Required main CI failed: " + run["html_url"])
    return True


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    workflows = json.loads(os.environ["REQUIRED_WORKFLOWS"])
    deadline = time.monotonic() + 5400
    while time.monotonic() < deadline:
        complete = True
        for workflow in workflows:
            path = (
                f"repos/{repository}/actions/workflows/{workflow}/runs?"
                + urllib.parse.urlencode(
                    {"head_sha": sha, "event": "push", "per_page": 100}
                )
            )
            request = urllib.request.Request(
                "https://api.github.com/" + path,
                headers={
                    "Authorization": "Bearer " + os.environ["GH_TOKEN"],
                    "Accept": "application/vnd.github+json",
                },
            )
            # The API origin and HTTPS scheme above are fixed, not caller inputs.
            with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
                runs = json.load(response)["workflow_runs"]
            complete = check_runs(runs, sha) and complete
        if complete:
            print("Required CI passed for " + sha, flush=True)
            return
        print("Waiting for main CI on " + sha, flush=True)
        time.sleep(30)
    raise TimeoutError(
        "Required CI did not succeed within 90 minutes; no release requested"
    )


if __name__ == "__main__":
    main()
