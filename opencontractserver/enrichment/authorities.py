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

import logging
import re
from dataclasses import dataclass

from django.contrib.auth import get_user_model

from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import CorpusDocumentService
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.utils.files import read_field_file_text

logger = logging.getLogger(__name__)
User = get_user_model()

# Subsection canonical keys fall back to their root section: the authority
# corpus stores one document per *section* (dgcl:122), while citations may be
# subsection-precise (dgcl:122(17)). Root = authority prefix + section number
# (with optional trailing letter), i.e. everything before the first "(".
_ROOT_KEY_RE = re.compile(r"^(?P<root>[a-z0-9-]+:\d+[a-z]?)", re.IGNORECASE)


@dataclass
class AuthoritySection:
    """One statute section destined to become an authority document."""

    key: str  # canonical key, e.g. "dgcl:145"
    heading: str  # document title, e.g. "DGCL § 145 — Indemnification"
    text: str  # full section text
    source_url: str | None = None


def candidate_keys(canonical_key: str) -> list[str]:
    """Keys to try when resolving a citation: exact first, then section root."""
    keys = [canonical_key]
    m = _ROOT_KEY_RE.match(canonical_key)
    if m and m.group("root") != canonical_key:
        keys.append(m.group("root"))
    return keys


def authority_alias_registry(user=None) -> dict[str, str]:
    """Build the authority alias -> canonical-prefix map for extraction.

    Static defaults (``constants.AUTHORITY_PREFIX``) merged with aliases
    declared by authority corpora: the bootstrapper stamps each section
    document with ``custom_meta.authority_aliases``, so adding a body of law
    is a bootstrap call, not a code change. DB-declared aliases override
    static entries on collision. When ``user`` is given, only aliases on
    documents visible to that user are included.
    """
    mapping: dict[str, str] = dict(C.AUTHORITY_PREFIX)
    qs = (
        Document.objects.all()
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
    (``dgcl:122``). Returns ``None`` when no visible authority document
    carries the key.
    """
    for key in candidate_keys(canonical_key):
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
        result["relink"] = EnrichmentService().relink_corpora_for_keys(
            [sec.key for sec in sections]
        )
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
                except Exception:  # unreadable -> rewrite below
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
