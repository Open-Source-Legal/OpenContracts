# Frontend `any` Baseline

Tracks the `Audit and reduce \`any\` usage in frontend TypeScript` initiative
([#1448](https://github.com/Open-Source-Legal/OpenContracts/issues/1448)).

The frontend does not run ESLint today, so we enforce a count-based gate
instead of a per-rule severity. The mechanism is intentionally minimal — a
plain Node script and a committed JSON file — so the contract is obvious to
anyone touching it.

## Files

| Path | Role |
|------|------|
| `frontend/scripts/check-any-baseline.js` | Counts `any` occurrences and compares them to the baseline. |
| `frontend/.any-baseline.json` | Committed snapshot: total + per-area breakdown. |
| `.github/workflows/frontend.yml` (Lint job) | Runs `yarn any:check:strict` on every PR. |

## What the script counts

Type-position uses of `any` in `frontend/src/**/*.{ts,tsx}`:

```
: any        as any        <any>        any[]
Array<any>   Promise<any>  ReadonlyArray<any>
```

Comment-only lines (`//`, `/* … */`, leading `*`) are skipped. The matcher does
not catch every shape (`Record<string, any>`, callback parameter inference,
implicit `any` from missing types) but it covers the vast majority of explicit
opt-outs the team writes by hand.

## Workflow

### Day-to-day (regression gate)

```bash
cd frontend
yarn any:check          # local: shows current vs. baseline, fails on regressions
```

CI runs `yarn any:check:strict`, which additionally fails when the current
count is *below* the baseline without the baseline file being updated. That
keeps the snapshot honest — every reduction is recorded in the same PR that
produced it.

### Lowering the baseline

When a PR replaces `any` with a real type:

```bash
cd frontend
yarn any:write          # rewrites .any-baseline.json with the new total + breakdown
```

Commit the regenerated `frontend/.any-baseline.json` alongside the type fixes
and call out the delta in the PR description (e.g. `annotator: 90 → 86`).

### Adding a new file with no `any`

No action — the baseline only tracks totals, not file lists. New files are
expected to land without explicit `any`.

### Adding a new file that needs `any`

Don't, if you can avoid it. If genuinely unavoidable (e.g. wrapping a
third-party library with no types), offset by lowering another area in the
same PR so the total does not grow. Document the trade-off in the PR.

## Areas tracked

The breakdown groups paths under `frontend/src/`:

- `knowledge_base` — `components/knowledge_base/**`
- `annotator` — `components/annotator/**`
- `widgets_chat` — `components/widgets/chat/**`
- `widgets_other` — remaining `components/widgets/**`
- `components_other` — remaining `components/**`
- `graphql`, `hooks`, `atoms`, `routing`, `utils`, `types` — top-level dirs
- `other` — anything else under `src/`

Order in `byArea` is descending by count, so the largest pockets are visible
at the top of the file.

## Prioritised drain (per the issue)

1. `components/knowledge_base/` — annotation/permission rendering
2. `components/annotator/` — PDF/annotation interaction surface
3. `components/widgets/chat/` — agent/tool interaction surface

When replacing `any` with a real type, prefer reusing types from
`frontend/src/types/graphql-api.ts` (or the GraphQL codegen output) over
hand-rolled shapes.
