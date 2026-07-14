"""Bootstrap "authority corpora" — statute / regulation reference targets.

An authority corpus holds one text document per statute section (e.g. DGCL
§ 145). Each document carries its canonical key in ``Document.custom_meta``
(``{"canonical_key": "dgcl:145", "authority": "dgcl"}``) so the cross-corpus
resolution pass can upgrade EXTERNAL law references (emitted by the
enrichment engine with the same canonical keys) into RESOLVED links that
point at a concrete document in another corpus.

Document creation is delegated to the existing text-import tool
(``create_or_update_text_document`` -> ``Corpus.import_content``), so
authority documents get real versioning, paths, and permissions like any
other corpus document.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db.models import Q

from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import CorpusDocumentService
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.utils.files import read_field_file_text

logger = logging.getLogger(__name__)
User = get_user_model()

# Subsection canonical keys fall back to their root section: the authority
# corpus stores one document per *section* (dgcl:122, cfr-40:261.4), while
# citations may be subsection-precise (dgcl:122(17), cfr-40:261.4(a)). The root
# is the key with trailing parenthetical SUBSECTION groups stripped. Dotted /
# hyphenated SECTION numbers (cfr-40:261.4, usc-15:80a-1, cfr-17:240.10b-5,
# sec-rule:10b-5) are WHOLE sections and must be preserved intact — the old
# "digits + optional letter" root pattern wrongly truncated them at the first
# "." or "-".
_SUBSECTION_SUFFIX_RE = re.compile(r"(?:\([0-9a-zA-Z]+\))+$")


@dataclass
class AuthoritySection:
    """One statute section destined to become an authority document."""

    key: str  # canonical key, e.g. "dgcl:145"
    heading: str  # document title, e.g. "DGCL § 145 — Indemnification"
    text: str  # full section text
    source_url: str | None = None


def parse_section_spec(
    spec: Mapping, *, label: str = "spec"
) -> tuple[list[AuthoritySection], list[str] | None]:
    """Validate a parsed section-spec mapping into ``AuthoritySection`` objects.

    The single section-spec contract, shared by the ``bootstrap_authority`` and
    ``load_authority_pack`` management commands so a standalone spec and a pack
    spec are held to exactly the same schema. Raises ``ValueError`` on any
    violation (callers wrap it into a ``CommandError``); ``label`` prefixes the
    message so a multi-spec pack run names the offending file. Returns
    ``(sections, aliases)``.
    """
    raw_sections = spec.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError(f"{label}: must contain a non-empty 'sections' list.")

    sections: list[AuthoritySection] = []
    for i, sec in enumerate(raw_sections):
        if not isinstance(sec, dict) or not all(
            isinstance(sec.get(f), str) and sec[f].strip()
            for f in ("key", "heading", "text")
        ):
            raise ValueError(
                f"{label}: sections[{i}] must have non-empty 'key', 'heading' "
                "and 'text' (optional 'source_url')."
            )
        sections.append(
            AuthoritySection(
                key=sec["key"].strip(),
                heading=sec["heading"].strip(),
                text=sec["text"],
                source_url=sec.get("source_url"),
            )
        )

    # ``aliases`` flows untouched into ``custom_meta.authority_aliases``, which
    # ``authority_alias_registry`` iterates as ``for alias in aliases or []``. A
    # bare string there is truthy, so ``or []`` is skipped and Python iterates it
    # character-by-character — registering 'C','P','E' as separate alias keys
    # from "CPE" and corrupting the alias map. Reject any non-list-of-strings
    # here so a malformed spec fails loudly instead of silently corrupting state.
    raw_aliases = spec.get("aliases")
    if raw_aliases is not None and not (
        isinstance(raw_aliases, list) and all(isinstance(a, str) for a in raw_aliases)
    ):
        raise ValueError(
            f"{label}: 'aliases' must be a list of strings, got "
            f"{type(raw_aliases).__name__!r}."
        )
    return sections, raw_aliases


def read_section_spec(
    path, *, label: str | None = None
) -> tuple[list[AuthoritySection], list[str] | None]:
    """Read a JSON section-spec file and validate it via :func:`parse_section_spec`.

    Raises ``ValueError`` on an unreadable/invalid-JSON file or a schema
    violation, so both authority-bootstrap commands share one read-and-validate
    path. ``label`` defaults to the file path.
    """
    path = Path(path)
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read spec {path}: {exc}") from exc
    return parse_section_spec(spec, label=label or str(path))


def candidate_keys(canonical_key: str) -> list[str]:
    """Keys to try when resolving a citation.

    Order: the exact key first; then — if the key contains an underscore —
    the same key with every ``_`` replaced by ``-``. Real canonical keys use
    hyphens exclusively in their namespace prefix (``exchange-act:16``,
    ``sec-rule:144``) and never an underscore, but an LLM occasionally emits
    an underscore-separated variant anyway, pattern-matching Python-identifier
    conventions instead of the real hyphenated key grammar — so we try the
    normalized form as a fallback rather than silently returning nothing.
    Finally, the section-root fallback (trailing parenthetical subsection
    groups stripped) is applied to BOTH the exact key and the
    normalized-underscore variant, so a subsection citation with an
    underscore typo still rolls up to its section root. Order is preserved
    (exact key first) and no duplicate entries are returned.
    """
    keys = [canonical_key]
    normalized = canonical_key.replace("_", "-")
    if normalized != canonical_key:
        keys.append(normalized)

    for base in (canonical_key, normalized):
        root = _SUBSECTION_SUFFIX_RE.sub("", base)
        if root and root != base and root not in keys:
            keys.append(root)

    return keys


def namespace_classification_cache(prefixes) -> dict[str, tuple]:
    """Prefetch ``{prefix: (jurisdiction, authority_type)}`` from AuthorityNamespace.

    One query for a whole batch — pass the result to
    :func:`classify_canonical_key` as ``namespace_cache`` so a batch writer
    resolves the namespace tier once instead of per row (no N+1).
    """
    from opencontractserver.annotations.models import AuthorityNamespace

    return {
        p: (j, t)
        for p, j, t in AuthorityNamespace.objects.filter(
            prefix__in=set(prefixes)
        ).values_list("prefix", "jurisdiction", "authority_type")
    }


def classify_canonical_key(
    canonical_key: str | None,
    jurisdiction: str | None = None,
    authority_type: str | None = None,
    *,
    namespace_cache: dict[str, tuple] | None = None,
) -> tuple:
    """Resolve ``(jurisdiction, authority_type)`` for a canonical key.

    The single classification ladder used at BOTH read time (``discover()``)
    and persist time (``EnrichmentWriter``), so a stored ``CorpusReference``
    carries exactly the taxonomy the inventory reports. Precedence:

    1. values already on the candidate (passed in) — the detector knows best;
    2. the ``AuthorityNamespace`` registry row for the key's prefix;
    3. the static ``classify_prefix`` shape rules
       (``usc-NN`` / ``cfr-NN`` / ``fedreg`` / ``act`` / ``publ`` / ``stat`` / …).

    ``namespace_cache`` (``{prefix: (jur, typ)}`` from
    :func:`namespace_classification_cache`) skips the per-row AuthorityNamespace
    query; omit it for a single lookup.
    """
    if jurisdiction is not None and authority_type is not None:
        return (jurisdiction, authority_type)
    prefix = canonical_key.split(":", 1)[0] if canonical_key else ""
    ns_jur = ns_typ = None
    if prefix:
        if namespace_cache is not None:
            ns_jur, ns_typ = namespace_cache.get(prefix, (None, None))
        else:
            ns_jur, ns_typ = namespace_classification_cache([prefix]).get(
                prefix, (None, None)
            )
        if ns_jur is None and ns_typ is None:
            ns_jur, ns_typ = C.classify_prefix(prefix)
    return (jurisdiction or ns_jur, authority_type or ns_typ)


def authority_alias_registry(user=None) -> dict[str, str]:
    """Build the authority alias -> canonical-prefix map for extraction.

    Static defaults (``constants.AUTHORITY_PREFIX``) merged with aliases
    declared by authority corpora: the bootstrapper stamps each section
    document with ``custom_meta.authority_aliases``, so adding a body of law
    is a bootstrap call, not a code change. DB-declared aliases override
    static entries on collision. When ``user`` is given, only aliases on
    documents visible to that user are included.
    """
    from opencontractserver.annotations.models import AuthorityNamespace

    mapping: dict[str, str] = dict(C.AUTHORITY_PREFIX)

    # Namespace registry (Phase 0): global namespaces always; corpus-linked
    # namespaces only when their corpus is visible to ``user``. Fail closed —
    # without a user, contribute only global namespaces (no private leak).
    ns_qs = AuthorityNamespace.objects.all()
    if user is None:
        ns_qs = ns_qs.filter(is_global=True)
    else:
        ns_qs = ns_qs.filter(
            Q(is_global=True)
            | Q(authority_corpus__in=Corpus.objects.visible_to_user(user))
        )
    for ns_prefix, aliases in ns_qs.values_list("prefix", "aliases"):
        for alias in aliases or []:
            if isinstance(alias, str) and alias.strip():
                mapping[alias.strip().lower()] = ns_prefix

    # Legacy per-document alias source (authority corpora stamp custom_meta).
    # Fail closed: without a user contribute only the static + global rows.
    qs = (
        Document.objects.none()
        if user is None
        else Document.objects.visible_to_user(user)
    )
    rows = qs.filter(custom_meta__has_key="authority_aliases").values_list(
        "custom_meta", flat=True
    )
    for meta in rows:
        meta = meta or {}
        prefix = meta.get("authority")
        if not prefix:
            continue
        for alias in meta.get("authority_aliases") or []:
            if isinstance(alias, str) and alias.strip():
                mapping[alias.strip().lower()] = prefix
    return mapping


def find_authority_target(canonical_key: str, user) -> Document | None:
    """Find the authority document for a canonical key, visible to ``user``.

    Falls back from subsection keys (``dgcl:122(17)``) to the root section
    (``dgcl:122``).  Also follows ``AuthorityKeyEquivalence`` rows so that
    an act-section citation (``exchange-act:10(b)``) resolves to the USC
    document materialised under the equivalent USC key (``usc-15:78j``).

    Returns ``None`` when no visible authority document carries any of the
    candidate keys.
    """
    from opencontractserver.annotations.models import AuthorityKeyEquivalence

    # Start with direct candidates (exact + section root).
    keys: list[str] = list(candidate_keys(canonical_key))

    # Hop across namespaces via the equivalence table (act-section <-> USC).
    # NOTE: This is a single-pass (non-recursive) hop, sufficient for the
    # hub-and-spoke seed (act-section → USC). Transitive chains (A→B→C) would
    # require iterating until the key set stabilises.
    # Query both directions (from_key and to_key) in one round-trip. Membership
    # is tested against the *original* candidate set (snapshot here) so that the
    # "other" side is unambiguous even when both ends of an equivalence row
    # happen to be present, and we skip re-adding a side already covered.
    original_keys: set[str] = set(keys)
    equivs = AuthorityKeyEquivalence.objects.filter(
        Q(from_key__in=keys) | Q(to_key__in=keys)
    )
    for equiv in equivs:
        # Follow whichever side is NOT already among the original keys.
        other = equiv.to_key if equiv.from_key in original_keys else equiv.from_key
        if other in original_keys:
            continue
        keys.extend(candidate_keys(other))

    # Prefix rewrite-rule fallback (Phase 4): extend the candidate set with
    # mechanical rewrites (e.g. irc:N -> usc-26:N), tried AFTER explicit
    # equivalence hops so a per-key row always wins. Snapshot ``keys`` first so
    # we rewrite the originals, not keys we just appended.
    from opencontractserver.enrichment.data import mappings as _enrichment_mappings

    for key in list(keys):
        for rewritten in _enrichment_mappings.apply_rewrite_rules(key):
            keys.extend(candidate_keys(rewritten))

    # Deduplicate preserving insertion order.
    seen: set[str] = set()
    deduped: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            deduped.append(k)

    for key in deduped:
        doc = (
            Document.objects.visible_to_user(user)
            .filter(
                custom_meta__canonical_key=key,
                # Version-ups create a new Document row; only the current
                # (non-superseded) version has a live path record.
                path_records__is_current=True,
                path_records__is_deleted=False,
            )
            .order_by("id")
            .first()
        )
        if doc is not None:
            return doc

    # Whole-act fallback. A bare authority key with no section (e.g.
    # ``exchange-act``, emitted by the popular-name grammar for "the Exchange
    # Act") references the WHOLE body of law. Authority corpora hold one
    # document per section and no section-less "whole act" document, so resolve
    # such a citation to a representative section — the lowest-id current
    # document carrying that authority — so a whole-act citation links into the
    # existing corpus instead of stranding as a wanted/unsupported frontier
    # entry. Scoped to colon-less keys: a section-precise citation we don't hold
    # (e.g. ``dgcl:999``) must stay genuinely unresolved, never silently
    # resolving to a different section of the same body.
    if ":" not in canonical_key:
        representative = (
            Document.objects.visible_to_user(user)
            .filter(
                custom_meta__authority=canonical_key,
                path_records__is_current=True,
                path_records__is_deleted=False,
            )
            .order_by("id")
            .first()
        )
        if representative is not None:
            return representative
    return None


def bootstrap_authority_corpus(
    *,
    creator_id: int,
    corpus_title: str,
    sections: list[AuthoritySection],
    aliases: list[str] | None = None,
    corpus_id: int | None = None,
    make_public: bool = False,
    relink: bool = True,
    relink_async: bool = False,
) -> dict:
    """Production entry point: bootstrap an authority, then converge filings.

    Wraps :class:`AuthorityCorpusBootstrapper` with the two behaviours every
    real backfill wants (and tests usually don't):

    * ``make_public`` — publish the corpus so the authority resolves
      citations for *every* user (``Corpus.save`` propagates ``is_public``
      to its documents);
    * ``relink`` (default on) — reactive re-link: immediately upgrade
      EXTERNAL references in every corpus citing the bootstrapped keys,
      each under its own creator's visibility.

    When ``relink_async`` is set, the relink sweep is enqueued as a Celery
    task and ``result["relink"]`` carries ``{"queued": True, "task_id": ...}``
    instead of the inline summary — the async agent-tool path uses this so a
    large authority set doesn't hold its thread-pool slot for minutes. The
    management command keeps the inline path (``relink_async=False``).

    The agent tool and the ``bootstrap_authority`` management command both
    route through here so the workflow exists exactly once.
    """
    from opencontractserver.enrichment.services import EnrichmentService

    result = AuthorityCorpusBootstrapper().bootstrap(
        creator_id=creator_id,
        corpus_title=corpus_title,
        sections=sections,
        corpus_id=corpus_id,
        aliases=aliases,
    )
    if make_public:
        corpus = Corpus.objects.get(pk=result["corpus_id"])
        if not corpus.is_public:
            corpus.is_public = True
            # save() (not .update()) so the is_public change propagates to
            # the corpus's documents.
            corpus.save(update_fields=["is_public", "modified"])
        result["made_public"] = True
    if relink:
        keys = [sec.key for sec in sections]
        if relink_async:
            from opencontractserver.tasks.corpus_tasks import (
                relink_corpora_for_keys_task,
            )

            async_result = relink_corpora_for_keys_task.delay(keys)
            result["relink"] = {"queued": True, "task_id": async_result.id}
        else:
            result["relink"] = EnrichmentService().relink_corpora_for_keys(keys)
    return result


class AuthorityCorpusBootstrapper:
    """Create or refresh an authority corpus from a section spec."""

    def bootstrap(
        self,
        *,
        creator_id: int,
        corpus_title: str,
        sections: list[AuthoritySection],
        corpus_id: int | None = None,
        aliases: list[str] | None = None,
    ) -> dict:
        """Idempotently materialise ``sections`` as keyed documents.

        Unchanged sections are skipped; changed text version-ups the existing
        document at the same path (title-derived). Returns a summary dict.
        """
        # Local import: the tool module imports services that import models —
        # keep the engine importable without dragging the whole tool package.
        from opencontractserver.llms.tools.core_tools.text_document_import import (
            create_or_update_text_document,
        )

        user = User.objects.get(pk=creator_id)
        if corpus_id is not None:
            # Visibility-scoped: invisible and nonexistent corpora raise the
            # same ``Corpus.DoesNotExist`` (no existence oracle).
            corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
            corpus_created = False
        else:
            corpus, corpus_created = Corpus.objects.get_or_create(
                title=corpus_title, creator=user
            )

        created = updated = skipped = restamped = 0
        for sec in sections:
            # Match by key, falling back to title: a concurrent full-row save
            # from the document-processing pipeline can clobber a freshly
            # stamped custom_meta (lost update), so a re-run must recognise
            # the document by title and restamp rather than re-import it.
            existing = self._find_by_key(user, corpus, sec.key) or self._find_by_title(
                user, corpus, sec.heading
            )
            if existing is not None:
                try:
                    current = read_field_file_text(existing.txt_extract_file)
                except (OSError, ValueError, AttributeError):
                    # Unreadable (missing file / no file associated / decode
                    # error) -> treat as needs-rewrite below. Narrow on purpose
                    # so genuine bugs surface instead of being swallowed.
                    current = None
                if current == sec.text:
                    meta = existing.custom_meta or {}
                    if meta.get("canonical_key") != sec.key or (
                        aliases and meta.get("authority_aliases") != aliases
                    ):
                        self._stamp_key(existing.id, sec, aliases)
                        restamped += 1
                    else:
                        skipped += 1
                    continue

            out = create_or_update_text_document(
                corpus_id=corpus.id,
                title=sec.heading,
                content=sec.text,
                author_id=creator_id,
                description=f"Authority text for {sec.key}"
                + (f" (source: {sec.source_url})" if sec.source_url else ""),
            )
            self._stamp_key(out["document_id"], sec, aliases)
            if out["status"] == "created":
                created += 1
            else:
                updated += 1

        return {
            "corpus_id": corpus.id,
            "corpus_created": corpus_created,
            "documents_created": created,
            "documents_updated": updated,
            "documents_skipped": skipped,
            "documents_restamped": restamped,
        }

    @staticmethod
    def _find_by_key(user, corpus, key: str) -> Document | None:
        return (
            CorpusDocumentService.get_corpus_documents(user, corpus)
            .filter(custom_meta__canonical_key=key)
            .first()
        )

    @staticmethod
    def _find_by_title(user, corpus, title: str) -> Document | None:
        return (
            CorpusDocumentService.get_corpus_documents(user, corpus)
            .filter(title=title)
            .first()
        )

    @staticmethod
    def _stamp_key(
        document_id: int, sec: AuthoritySection, aliases: list[str] | None = None
    ) -> None:
        doc = Document.objects.get(pk=document_id)
        meta = dict(doc.custom_meta or {})
        meta["canonical_key"] = sec.key
        meta["authority"] = sec.key.split(":", 1)[0]
        if sec.source_url:
            meta["source_url"] = sec.source_url
        if aliases:
            meta["authority_aliases"] = aliases
        doc.custom_meta = meta
        doc.save(update_fields=["custom_meta"])
