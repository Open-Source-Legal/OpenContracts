# Test: Batch-run an agent corpus action across every doc in a corpus

## Purpose

End-to-end verification of the new `startCorpusActionBatchRun` GraphQL
mutation + Layers-icon UI button. Confirms that:

1. A non-superuser collaborator with corpus `UPDATE` can press the button.
2. Every active document in the corpus that has not already been processed
   gets a `CorpusActionExecution(trigger="manual_batch", status="QUEUED")`
   row.
3. The `run_agent_corpus_action` Celery task fires once per eligible doc.
4. Pressing the button a second time skips docs that are already
   `QUEUED | RUNNING | COMPLETED` (idempotent re-press).
5. A `FAILED` execution is re-queued on the next press (retry path).

## Prerequisites

- Local stack up: `docker compose -f local.yml up`.
- Migrations applied through `corpuses/0051_add_manual_batch_trigger`.
- An LLM API key configured on the `agents.AgentConfiguration` you'll use
  (or test against a lightweight `task_instructions`-only action that just
  exercises the dispatch path — the agent will fail to load the LLM but the
  execution rows + dispatch are what we're verifying here).

## Steps

### 1. Create a corpus with three docs and an agent action

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus, CorpusAction, CorpusActionTrigger
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
owner = User.objects.filter(is_superuser=True).first()
collab, _ = User.objects.get_or_create(username='batch-test-collab', defaults={'email': 'c@test'})

corpus = Corpus.objects.create(title='Batch Test Corpus', creator=owner)
set_permissions_for_obj_to_user(collab, corpus, [PermissionTypes.UPDATE])

for i in range(3):
    doc = Document.objects.create(title=f'Batch Doc {i}', creator=owner)
    DocumentPath.objects.create(
        document=doc, corpus=corpus, path=f'/documents/doc_{doc.pk}',
        version_number=1, is_current=True, is_deleted=False, creator=owner,
    )

action = CorpusAction.objects.create(
    corpus=corpus,
    name='Generate Descriptions',
    trigger=CorpusActionTrigger.ADD_DOCUMENT,
    task_instructions='Read the document and update its description with a one-sentence summary.',
    creator=owner,
)
print(f'corpus={corpus.id} action={action.id} collab={collab.id}')
"
```

### 2. Trigger the batch run via GraphQL

Use the frontend Layers button, or curl with a session cookie:

```bash
curl -s -X POST http://localhost:8000/graphql/ \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=<collab-session-key>" \
  -d '{
    "query": "mutation($id: ID!) { startCorpusActionBatchRun(corpusActionId: $id) { ok message queuedCount skippedAlreadyRunCount totalActiveDocuments } }",
    "variables": {"id": "<corpus-action-relay-global-id>"}
  }' | python3 -m json.tool
```

### 3. Verify execution rows landed and have the right trigger

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.corpuses.models import CorpusActionExecution

execs = CorpusActionExecution.objects.filter(trigger='manual_batch')
print(f'manual_batch executions: {execs.count()}')
for e in execs:
    print(f'  doc={e.document_id} status={e.status}')
"
```

### 4. Re-press: idempotent skip

Run step 2 again. Expected response:

```json
{
  "ok": true,
  "queuedCount": 0,
  "skippedAlreadyRunCount": 3,
  "totalActiveDocuments": 3
}
```

### 5. Retry path: mark one execution FAILED, press again

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.corpuses.models import CorpusActionExecution
ex = CorpusActionExecution.objects.filter(trigger='manual_batch').first()
ex.status = CorpusActionExecution.Status.FAILED
ex.save()
print(f'Marked execution {ex.id} as FAILED')
"
```

Re-press the batch button. Expected: `queuedCount=1`, `skippedAlreadyRunCount=2`.

## Expected Results

- All three docs end up with a `manual_batch` execution after step 2.
- Step 4 returns `queuedCount=0` and creates no new rows.
- Step 5 produces exactly one new execution row (the previously-failed doc
  gets re-queued; the two completed docs remain skipped).
- The Action Execution History panel on the corpus settings page shows the
  batch-trigger rows alongside any auto-fired ones.

## Cleanup

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.corpuses.models import Corpus
Corpus.objects.filter(title='Batch Test Corpus').delete()
"
```
