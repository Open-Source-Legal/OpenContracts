# TEMPORARY verification probe -- see the PR description. This file is
# deliberately misformatted so `black` fails in the linter job, which skips
# pytest, which is the exact state a required `pytest` check would report
# GREEN for. It exists to prove `backend-ci-gate` reports FAILURE and that
# GitHub actually blocks the merge. Delete with the branch.
x=1
def  f( a,b ):
    return {  'a':a,"b":b }
