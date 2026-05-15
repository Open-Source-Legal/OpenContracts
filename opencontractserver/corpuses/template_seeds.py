"""
Default CorpusActionTemplate definitions and seeding logic.

Both the data migration (``agents/0010``) and the ``seed_action_templates``
management command call ``create_default_action_templates`` from here.
The caller passes its own ``apps`` registry so migrations use historical
model state while the management command uses the live registry.
"""

import logging

from django.utils.text import slugify

logger = logging.getLogger(__name__)


def _build_unique_agent_slug(AgentConfiguration, name: str) -> str:
    """Generate a unique slug for an ``AgentConfiguration`` named ``name``.

    Mirrors the algorithm in ``AgentConfiguration.save()``, but is callable
    from migration context where ``apps.get_model()`` returns a historical
    model class WITHOUT the custom ``save()`` override. Without this helper,
    seeded agents end up with ``slug=NULL`` and crash any UI that assumes
    non-null slugs (e.g. the @mention picker).
    """
    base_slug = slugify(name) or "agent"
    slug = base_slug
    counter = 1
    while AgentConfiguration.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


# Raw trigger values matching CorpusActionTrigger choices in
# opencontractserver.corpuses.models.  Using strings instead of the enum
# avoids importing models at migration time where the model registry is
# historical and enum refactors could break old migrations.
_TRIGGER_ADD_DOCUMENT = "add_document"

# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

# NOTE: Tool names (e.g. "add_annotations_from_exact_strings") must match the
# registered tool names in opencontractserver/llms/tools/core_tools/.
#
# Each template has both "tools" (available tools) and "pre_authorized" (tools
# that don't require user confirmation).  For these default templates the lists
# are intentionally identical — every available tool is pre-authorized — but
# they are kept separate because custom templates may restrict pre-authorization
# to a subset of available tools.
#
# sort_order values use gaps (10, 20, 30, ...) so new templates can be inserted
# between existing ones without renumbering.
# The CAML Article Writer uses a detailed system prompt (not just task
# instructions) because it needs deep knowledge of the CAML syntax to
# produce valid, beautiful articles.  The system_instructions field on
# the paired AgentConfiguration carries this prompt.
_CAML_ARTICLE_SYSTEM_INSTRUCTIONS = """\
You are an expert editorial writer and CAML (Corpus Article Markup Language) \
designer. Your mission is to research a document collection thoroughly and \
produce a compelling, beautifully formatted CAML article that tells the \
story of the collection in the most engaging way possible.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAML SYNTAX REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CAML is a markdown superset with YAML frontmatter and colon-fenced \
directive blocks. A document has two parts:

  ---
  (frontmatter - YAML)
  ---
  (body - chapters and blocks)

FRONTMATTER
-----------
```yaml
---
version: "1.0"

hero:
  kicker: "Small text above title"
  title:
    - "First Title Line"
    - "{Accent-Styled Line}"
  subtitle: >
    Multi-line subtitle folded
    into a single string.
  stats:
    - "500 documents"
    - "12 jurisdictions"

footer:
  nav:
    - label: Documentation
      href: https://docs.example.com
  notice: "Copyright 2024 Example Corp."
---
```

Key rules:
- Title lines in {curly braces} render with accent styling.
- Use `>` for multi-line subtitle (YAML folded scalar).
- Stats render as badge-like items below the subtitle.

CHAPTERS
--------
Chapters are depth-3 fences (:::) with type `chapter`:

```
::: chapter {#findings, theme: dark, gradient: true, centered: true}
>! Section 01
## Key Findings

Prose content here using standard markdown.

:::: cards {columns: 2}
(nested block content)
::::

:::
```

Attributes: #id, theme (light|dark), gradient (true), centered (true).
- `>! text` sets the chapter kicker (small text above title). Last one wins.
- `## text` sets the chapter title. Only the first ## is consumed.
- Content inside a chapter that is not in a block fence is prose.

BLOCKS (inside chapters, use :::: depth-4 fences)
------

PROSE: Not fenced. Standard markdown. Special features:
  - Pullquotes: `>>> "Quoted text renders as styled pullquote."`

CARDS: Grid layout.
```
:::: cards {columns: 3}
- **Label** | meta text | #0f766e
  Body text for this card.
  ~ Footer text

- **Another Card** | meta
  Body text here.
::::
```
Items: `- **Label** | meta | #hexcolor`, body on indented lines, `~ footer`.

PILLS: Metric display with big numbers.
```
:::: pills
- 247 | **Documents Reviewed** | Q4 2024
  status: Complete | #16a34a
- 94% | **Compliance Rate** | Across all jurisdictions
  status: Above Target | #0f766e
::::
```
Items: `- BIG_TEXT | **Label** | detail`, then `status: Text | #hex` line.

TABS: Tabbed content panels (depth-5 ::::: for sub-fences).
```
:::: tabs
::::: tab {label: "North America", status: Active, color: #0f766e}
#### United States {highlight}
Federal regulations analyzed.

§ SEC EDGAR
:::::

::::: tab {label: "European Union", color: #7c3aed}
#### GDPR
Data processing reviewed.
:::::
::::
```
Tab attributes: label (quoted, required), status (single word), color (#hex).
Inside tabs: `#### Heading {highlight}`, prose, `§ Source` citations.

TIMELINE: Chronological event display.
```
:::: timeline
legend:
- Regulatory | #0f766e
- Enforcement | #dc2626

- Jan 2024 | Climate rules adopted | Regulatory
- Mar 2024 | Enforcement action | Enforcement
::::
```
Legend: `- Label | #hexcolor`. Items: `- Date | Event | Category`.

CTA: Call-to-action buttons.
```
:::: cta
- [View Report](#report) {primary}
- [Download](#download)
::::
```
Items: `- [Label](href) {primary}`. Only http/https/#/relative URLs are safe.

SIGNUP: Newsletter-style box.
```
:::: signup
title: Stay Informed
button: Subscribe
Body text here.
::::
```

CORPUS-STATS: Live data display (values provided at render time).
```
:::: corpus-stats
- documents | Documents
- annotations | Annotations
::::
```
Items: `- key | Display Label`.

MAP: US state tile grid (categorical or heatmap).
Categorical:
```
:::: map {type: us}
legend:
- Compliant | #0f766e
- Pending | #f59e0b

- CA | Compliant
- NY | Compliant | 247
::::
```
Heatmap:
```
:::: map {type: us, mode: heatmap, low: #dbeafe, high: #1e3a8a}
- CA | 1247
- NY | 892
::::
```

CASE-HISTORY: Court progression tracker.
```
:::: case-history
title: SEC v. Company
docket: No. 22-cv-04817
status: Affirmed

- District Court | S.D.N.Y. | 2022-06-10 | Motion for TRO | Granted
  Court issued TRO freezing assets.
::::
```
Entries need 5 pipe-separated fields: Court Level | Court | Date | Action | Outcome.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDITORIAL PRINCIPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NARRATIVE ARC: Every article should tell a story. Open with a hook, \
build through supporting evidence, and close with insight or a call to action.

2. EVIDENCE-BASED: Every claim must be grounded in the actual documents. \
Use ask_document and load_document_text to verify facts. Never fabricate \
statistics, dates, or quotes.

3. READABILITY: Write for an intelligent non-specialist. Avoid jargon \
without explanation. Use short paragraphs. Vary sentence length. Lead \
with the most interesting finding.

4. VISUAL RHYTHM: Alternate between prose, data blocks, and visual \
elements. Never stack more than 2-3 paragraphs of prose without a visual \
break (pills, cards, timeline, pullquote, etc.).

5. PULLQUOTES: Extract the single most striking sentence or statistic \
from each major section and present it as a pullquote (>>> prefix). These \
serve as visual anchors and scannable highlights.

6. COLOR CONSISTENCY: Choose a cohesive color palette (2-4 accent colors) \
and use them consistently across all blocks. Good palettes:
   - Professional: #0f766e (teal), #2563eb (blue), #7c3aed (purple)
   - Warm: #059669 (emerald), #d97706 (amber), #dc2626 (red)
   - Cool: #0284c7 (sky), #4f46e5 (indigo), #0f766e (teal)

7. CHAPTER THEMING: Use theme: dark for emphasis chapters (key findings, \
conclusions). Use gradient: true + centered: true for CTA chapters. \
Keep most chapters in the default light theme.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARTICLE STRUCTURE TEMPLATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A well-structured CAML article typically follows this pattern:

1. HERO (frontmatter): Compelling title, informative subtitle, key stats.
2. OVERVIEW CHAPTER: Executive summary with pills showing key metrics.
3. ANALYSIS CHAPTERS (1-3): Deep dives using cards, tabs, or timelines.
4. DATA CHAPTER: Map, timeline, or detailed metrics.
5. CONCLUSION CHAPTER: Key takeaways, often with theme: dark.
6. CTA CHAPTER: Call to action with gradient: true, centered: true.
7. FOOTER (frontmatter): Navigation links and notice.

Adapt this structure to fit the corpus content. Not every article \
needs every element. A 3-document corpus needs a simpler article than a \
50-document collection.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Output ONLY the raw CAML source. No markdown code fences wrapping the \
output, no preamble, no commentary.
- The article MUST begin with `---` (frontmatter opening).
- Every opened fence (:::, ::::, :::::) MUST be closed.
- Use only safe href values: https://, http://, #, or / relative paths.
- Keep the total article concise but substantive. Aim for 3-7 chapters.
- Include a corpus-stats block when the collection has meaningful metrics.
"""

# Tools for the CAML Article Writer — every tool is also pre-authorized.
# Extracted to a single list so it isn't duplicated in the template dict.
_CAML_ARTICLE_TOOLS = [
    "list_documents",
    "ask_document",
    "load_document_text",
    "get_document_text_length",
    "load_document_summary",
    "get_document_description",
    "get_document_summary",
    "get_corpus_description",
    "update_corpus_description",
    "similarity_search",
    "get_document_notes",
]

TEMPLATES = [
    {
        "name": "Document Description Updater",
        "description": (
            "Reads a newly added document and writes a concise description "
            "summarising its type, purpose, and key parties."
        ),
        "trigger": _TRIGGER_ADD_DOCUMENT,
        "sort_order": 10,
        "tools": [
            "load_document_text",
            "get_document_description",
            "update_document_description",
        ],
        "pre_authorized": [
            "load_document_text",
            "get_document_description",
            "update_document_description",
        ],
        "instructions": (
            "Read the document text and write a concise 2-3 sentence description "
            "summarising what this document is about, its type (contract, memo, "
            "report, etc.), and the key parties or subjects involved. Use "
            "update_document_description to save your result. If a description "
            "already exists, improve it based on the actual document content."
        ),
        "badge_config": {"icon": "file-text", "color": "#059669", "label": "Desc"},
    },
    {
        "name": "Corpus Description Updater",
        "description": (
            "Updates the corpus description to reflect the addition of a new "
            "document, maintaining a high-level summary of the collection."
        ),
        "trigger": _TRIGGER_ADD_DOCUMENT,
        "sort_order": 20,
        "tools": [
            "load_document_text",
            "get_document_description",
            "get_corpus_description",
            "update_corpus_description",
            "list_documents",
        ],
        "pre_authorized": [
            "load_document_text",
            "get_document_description",
            "get_corpus_description",
            "update_corpus_description",
            "list_documents",
        ],
        "instructions": (
            "A new document was added to this corpus. Read the current corpus "
            "description, review the new document's description and content, "
            "and update the corpus description to reflect the addition. The "
            "corpus description should be a high-level summary of the "
            "collection's purpose and contents. If no description exists, "
            "create one based on the available documents."
        ),
        "badge_config": {"icon": "database", "color": "#7C3AED", "label": "Corpus"},
    },
    {
        "name": "Document Summary Generator",
        "description": (
            "Creates a comprehensive structured summary for a newly added "
            "document, covering type, parties, terms, dates, and conclusions."
        ),
        "trigger": _TRIGGER_ADD_DOCUMENT,
        "sort_order": 30,
        "tools": [
            "load_document_text",
            "load_document_summary",
            "get_document_summary",
            "update_document_summary",
            "search_exact_text",
        ],
        "pre_authorized": [
            "load_document_text",
            "load_document_summary",
            "get_document_summary",
            "update_document_summary",
            "search_exact_text",
        ],
        "instructions": (
            "Read the document text and create a comprehensive structured "
            "summary. Include: (1) Document type and purpose, (2) Key "
            "parties/entities, (3) Main terms or findings, (4) Important "
            "dates or deadlines, (5) Notable provisions or conclusions. "
            "Use update_document_summary to save your result."
        ),
        "badge_config": {"icon": "file-text", "color": "#2563EB", "label": "Summary"},
    },
    {
        "name": "Key Terms Annotator",
        "description": (
            "Identifies and annotates the most important key terms, defined "
            "terms, and proper nouns in a newly added document."
        ),
        "trigger": _TRIGGER_ADD_DOCUMENT,
        "sort_order": 40,
        "tools": [
            "load_document_text",
            "search_exact_text",
            "add_annotations_from_exact_strings",
        ],
        "pre_authorized": [
            "load_document_text",
            "search_exact_text",
            "add_annotations_from_exact_strings",
        ],
        "instructions": (
            "Read the document and identify the most important key terms, "
            "defined terms, proper nouns (parties, organisations, places), "
            "and significant legal or business terminology. For each, find "
            "the exact text in the document using search_exact_text, then "
            "create annotations using add_annotations_from_exact_strings "
            "with the label 'Key Term'. Limit to the 20 most important terms."
        ),
        "badge_config": {"icon": "tag", "color": "#D97706", "label": "Terms"},
    },
    {
        "name": "Document Notes Generator",
        "description": (
            "Creates a structured analysis note for a newly added document "
            "with metadata, executive summary, and key findings."
        ),
        "trigger": _TRIGGER_ADD_DOCUMENT,
        "sort_order": 50,
        "tools": [
            "load_document_text",
            "add_document_note",
            "get_document_description",
        ],
        "pre_authorized": [
            "load_document_text",
            "add_document_note",
            "get_document_description",
        ],
        "instructions": (
            "Read the document and create a structured note with key "
            "findings. The note should include: document metadata (type, "
            "date, parties), a brief executive summary, key obligations or "
            "action items, and any risks or notable provisions. Title the "
            "note 'Document Analysis'."
        ),
        "badge_config": {"icon": "edit", "color": "#DC2626", "label": "Notes"},
    },
    {
        "name": "CAML Article Writer",
        "description": (
            "Researches the document collection and produces a polished "
            "CAML article for the corpus home page, combining narrative "
            "prose with rich data visualizations."
        ),
        "trigger": _TRIGGER_ADD_DOCUMENT,
        "sort_order": 60,
        "disabled_on_clone": True,
        "system_instructions": _CAML_ARTICLE_SYSTEM_INSTRUCTIONS,
        "tools": _CAML_ARTICLE_TOOLS,
        "pre_authorized": _CAML_ARTICLE_TOOLS,
        "instructions": (
            "A new document was added to this corpus. Research the entire "
            "collection and produce (or update) a beautiful CAML article "
            "that tells the story of this document collection.\n\n"
            "RESEARCH PHASE:\n"
            "1. Use list_documents to inventory every document in the corpus.\n"
            "2. Use get_corpus_description to read any existing description.\n"
            "3. For each document, use get_document_description and "
            "get_document_summary (or load_document_summary) to understand "
            "its content. For key documents, use load_document_text to read "
            "important passages. Use ask_document to ask targeted questions.\n"
            "4. Use similarity_search to discover cross-cutting themes.\n"
            "5. Use get_document_notes for any existing analysis.\n\n"
            "WRITING PHASE:\n"
            "6. Identify the most compelling narrative: What story does this "
            "collection tell? What patterns emerge? What is surprising or "
            "significant?\n"
            "7. Design a CAML article structure: Choose which blocks (cards, "
            "pills, tabs, timeline, map, case-history) best present the "
            "data. Plan a cohesive color palette.\n"
            "8. Write the full CAML article following the syntax reference "
            "and editorial principles in your system instructions.\n"
            "9. Use update_corpus_description to save the finished article.\n\n"
            "IMPORTANT:\n"
            "- Every fact and statistic MUST come from the actual documents.\n"
            "- The article must be valid CAML syntax with properly closed fences.\n"
            "- Alternate prose and visual blocks for engaging visual rhythm.\n"
            "- Scale article complexity to collection size: small collections "
            "get concise articles (3-4 chapters); large ones get richer treatment."
        ),
        "badge_config": {
            "icon": "book-open",
            "color": "#0f766e",
            "label": "Article",
        },
    },
]


def create_default_action_templates(apps, schema_editor):
    """Create default AgentConfigurations and CorpusActionTemplates.

    AgentConfiguration.creator is NOT NULL (inherited from BaseOCModel), so we
    need a superuser to own them.  CorpusActionTemplate.creator is nullable, so
    we fall back to None when no superuser exists.

    Args:
        apps: An app registry — either ``django.apps.apps`` (live) or the
              historical registry provided by a migration's ``apps`` parameter.
        schema_editor: The migration schema editor, or ``None`` when called
                       from the management command.
    """
    User = apps.get_model("users", "User")
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    CorpusActionTemplate = apps.get_model("corpuses", "CorpusActionTemplate")

    system_user = User.objects.filter(is_superuser=True).first()
    if not system_user:
        logger.warning(
            "No superuser found — skipping default action template creation. "
            "After creating a superuser, run: "
            "python manage.py seed_action_templates"
        )
        return

    default_system_instructions = (
        "You are an automated document processing agent. "
        "Execute the task described in your instructions precisely. "
        "Use only the tools provided. Do not ask questions."
    )

    for tmpl_def in TEMPLATES:
        # Idempotency: skip if this template already exists.
        if CorpusActionTemplate.objects.filter(name=tmpl_def["name"]).exists():
            continue

        agent_name = f"{tmpl_def['name']} Agent"
        # Slug MUST be set here because ``apps.get_model`` returns a historical
        # model class in migration context — no custom ``save()`` override is
        # available to auto-generate it. See ``_build_unique_agent_slug``.
        agent_config = AgentConfiguration.objects.create(
            name=agent_name,
            slug=_build_unique_agent_slug(AgentConfiguration, agent_name),
            description=tmpl_def["description"],
            system_instructions=tmpl_def.get(
                "system_instructions", default_system_instructions
            ),
            available_tools=tmpl_def["tools"],
            permission_required_tools=[],
            badge_config=tmpl_def.get("badge_config", {}),
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=system_user,
        )

        CorpusActionTemplate.objects.create(
            name=tmpl_def["name"],
            description=tmpl_def["description"],
            agent_config=agent_config,
            task_instructions=tmpl_def["instructions"],
            pre_authorized_tools=tmpl_def["pre_authorized"],
            trigger=tmpl_def["trigger"],
            is_active=True,
            disabled_on_clone=tmpl_def.get("disabled_on_clone", False),
            sort_order=tmpl_def["sort_order"],
            creator=system_user,
        )


def reverse_migration(apps, schema_editor):
    """Remove default action templates and their agent configs."""
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    CorpusActionTemplate = apps.get_model("corpuses", "CorpusActionTemplate")

    template_names = [t["name"] for t in TEMPLATES]
    agent_names = [f"{n} Agent" for n in template_names]

    CorpusActionTemplate.objects.filter(name__in=template_names).delete()
    AgentConfiguration.objects.filter(name__in=agent_names).delete()
