# Test: Runtime LLM configuration end-to-end

## Purpose

Verify that the new pipeline-component-style LLM provider registry, the
per-corpus `preferred_llm` default, and the per-agent override flow
end-to-end — i.e. that the actual pydantic-ai `Agent` instance built
for a chat receives the right model spec depending on which layer was
set.

## Prerequisites

- Migrations `corpuses/0052_corpus_preferred_llm` and
  `agents/0014_agentconfiguration_preferred_llm` applied.
- A superuser exists (for the Django shell snippets below).
- Provider API keys in env-vars for any non-Ollama provider you'll
  exercise (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`).
  Phase 1 of this feature does not register credentials — pydantic-ai
  picks them up from the process environment.

## Steps

### 1 — Confirm the four providers are registered

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.pipeline.registry import get_all_llm_providers_cached
for p in get_all_llm_providers_cached():
    print(p.provider_key, '->', p.supported_models[:3], '... requires_api_key=', p.requires_api_key)
"
```

Expected output:

```
openai     -> ('gpt-4o', 'gpt-4o-mini', 'gpt-4.1') ... requires_api_key= True
anthropic  -> ('claude-opus-4-7', 'claude-opus-4-6', 'claude-sonnet-4-6') ... requires_api_key= True
google-gla -> ('gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-1.5-pro') ... requires_api_key= True
ollama     -> ('llama3.3', 'llama3.2', 'qwen2.5') ... requires_api_key= False
```

### 2 — Query the providers through GraphQL

```bash
curl -s -X POST http://localhost:8000/graphql/ \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=$DJANGO_SESSION_KEY" \
  -d '{"query":"query { pipelineComponents { llmProviders { providerKey title supportedModels requiresApiKey } } }"}' \
  | python3 -m json.tool
```

Should return the four providers with their `supportedModels` arrays.

### 3 — Reject a malformed corpus.preferred_llm

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus
from django.core.exceptions import ValidationError

user = get_user_model().objects.filter(is_superuser=True).first()
try:
    Corpus.objects.create(title='Bad LLM Corpus', creator=user, preferred_llm='not-a-provider:foo')
    print('FAIL: should have raised')
except ValidationError as e:
    print('OK rejected:', e.message_dict.get('preferred_llm'))
"
```

### 4 — Set a per-corpus default and confirm it wins over settings

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms.llm_registry import resolve_model_spec

user = get_user_model().objects.filter(is_superuser=True).first()
corpus, _ = Corpus.objects.update_or_create(
    title='LLM Override Test Corpus',
    creator=user,
    defaults={'preferred_llm': 'anthropic:claude-opus-4-6'},
)
print('corpus.preferred_llm =', corpus.preferred_llm)
print('corpus.created_with_llm =', corpus.created_with_llm)
print('resolver output =', resolve_model_spec(corpus_preferred=corpus.preferred_llm))
"
```

Expected: corpus stores `"anthropic:claude-opus-4-6"`,
`created_with_llm` is whatever default was active at creation, and the
resolver returns `"anthropic:claude-opus-4-6"`.

### 5 — Build an agent and confirm pydantic-ai sees the corpus default

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
import asyncio
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms.api import agents

user = get_user_model().objects.filter(is_superuser=True).first()
corpus = Corpus.objects.get(title='LLM Override Test Corpus')

async def go():
    agent = await agents.for_corpus(corpus=corpus, user_id=user.id, persist=False)
    print('agent.config.model_name =', agent.config.model_name)

asyncio.run(go())
"
```

Expected: `agent.config.model_name = anthropic:claude-opus-4-6`.

### 6 — Confirm per-call override wins

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
import asyncio
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms.api import agents

user = get_user_model().objects.filter(is_superuser=True).first()
corpus = Corpus.objects.get(title='LLM Override Test Corpus')

async def go():
    agent = await agents.for_corpus(
        corpus=corpus,
        user_id=user.id,
        persist=False,
        model='google-gla:gemini-2.0-flash',
    )
    print('agent.config.model_name =', agent.config.model_name)

asyncio.run(go())
"
```

Expected: `agent.config.model_name = google-gla:gemini-2.0-flash`
(per-call wins over the corpus default).

### 7 — Per-agent override via AgentConfiguration

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from django.contrib.auth import get_user_model
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus

user = get_user_model().objects.filter(is_superuser=True).first()
corpus = Corpus.objects.get(title='LLM Override Test Corpus')

# Corpus defaults to Opus, but this summarizer agent uses Haiku.
agent, _ = AgentConfiguration.objects.update_or_create(
    name='Summarizer (Haiku)',
    scope='CORPUS',
    corpus=corpus,
    creator=user,
    defaults={
        'description': 'Summarizer that uses Haiku 4.5 to save tokens.',
        'system_instructions': 'You produce concise summaries.',
        'preferred_llm': 'anthropic:claude-haiku-4-5',
    },
)
print('agent.preferred_llm =', agent.preferred_llm)
print('corpus.preferred_llm =', corpus.preferred_llm)
"
```

Then exercise the @-mention flow against this agent in the chat UI
(`@summarizer-haiku what's this corpus about?`) and confirm in the
agent task logs that the pydantic-ai agent was built with
`model=anthropic:claude-haiku-4-5` while the regular corpus chat keeps
using Opus.

## Expected results

- Step 3 raises `ValidationError({"preferred_llm": ...})`.
- Steps 4–6 print the documented resolver outputs.
- Step 7 demonstrates that two agents talking to the same corpus run
  on different models (Opus for the default corpus chat, Haiku for the
  named summarizer agent).

## Cleanup

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus

AgentConfiguration.objects.filter(name='Summarizer (Haiku)').delete()
Corpus.objects.filter(title__in=['LLM Override Test Corpus', 'Bad LLM Corpus']).delete()
"
```
