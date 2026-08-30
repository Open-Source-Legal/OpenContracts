- Pinned the `flake8` pre-commit hook's `additional_dependencies`
  (`.pre-commit-config.yaml`: `flake8-isort==7.0.0`, `isort==6.0.1`). They were
  unpinned, and `additional_dependencies` are re-resolved every time a hook env
  is rebuilt, so `flake8-isort` floated up to **isort 9.0.1** while the
  standalone `isort` hook stayed `rev`-pinned to 6.0.1. The two versions
  disagree about repeated `from X import (...)` statements — the shape isort 6
  itself emits for aliased imports — so `isort` kept files in a layout `flake8`
  then rejected. The result was the `linter` job failing on `main` and on every
  open PR with 10 `I001`/`I005` findings in
  `opencontractserver/llms/agents/pydantic_ai_agents.py` and
  `opencontractserver/utils/compact_pawls.py`, neither of which any of those PRs
  touched. `isort` here must track the `isort` hook's `rev`.
