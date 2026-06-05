"""
Default CorpusActionTemplate definitions and seeding logic.

Both the data migration (``agents/0010``) and the ``seed_action_templates``
management command call ``create_default_action_templates`` from here.
The caller passes its own ``apps`` registry so migrations use historical
model state while the management command uses the live registry.
"""

import logging

from django.utils.text import slugify

from opencontractserver.corpuses.caml_authoring import (
    CAML_ARTICLE_SYSTEM_INSTRUCTIONS,
)

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
        "system_instructions": CAML_ARTICLE_SYSTEM_INSTRUCTIONS,
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
