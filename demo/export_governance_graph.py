"""Export the cross-corpus governance graph to JSON for the demo visualization.

Run inside the Django container:

    docker compose -f local.yml run --rm -v "$PWD/demo:/app/demo" django \
        python manage.py shell -c "exec(open('/app/demo/export_governance_graph.py').read())"

Builds a node-link graph across every corpus that has CorpusReference rows,
plus every authority corpus they resolve into:

* nodes   — documents (filing primaries, exhibits, statute sections) and
            "ghost" nodes for still-EXTERNAL law citations (cited but no
            authority document yet).
* edges   — DocumentRelationship rows (intra-corpus doc->doc reference edges)
            and CorpusReference rows (LAW links, resolved cross-corpus or
            external), weighted by mention count.

Output: /app/demo/governance_graph.json (mounted back to ./demo).
"""

import json
import re
from collections import Counter, defaultdict

from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.enrichment.authorities import candidate_keys

OUT_PATH = "/app/demo/governance_graph.json"

# Company name = title up to the filing-type marker, e.g.
# "Fervo Energy Company S-1 (2025-12-19) - Exhibit 10.12" -> "Fervo Energy Company".
_COMPANY_RE = re.compile(r"^(?P<co>.+?)\s+(?:S-1|S-1/A|Form D|10-K|10-Q|8-K)\b")

AUTHORITY_DISPLAY = {
    "dgcl": "DGCL",
    "securities-act": "Securities Act",
    "exchange-act": "Exchange Act",
    "irc": "IRC",
    "sec-rule": "SEC Rule",
    "ica": "ICA",
    "iaa": "IAA",
}


def company_of(title: str) -> str | None:
    m = _COMPANY_RE.match(title or "")
    return m.group("co") if m else None


# Fallback grouping when a document title carries no filing-type marker
# (e.g. Form D SPV notices): group by the corpus, labeled from its title head.
def corpus_group_name(corpus_title: str) -> str:
    return (corpus_title or "").split("—")[0].split(" - ")[0].strip()[:40]


def doc_kind(doc: Document) -> str:
    if (doc.custom_meta or {}).get("canonical_key"):
        return "statute"
    if "exhibit" in (doc.title or "").lower():
        return "exhibit"
    return "primary"


def short_label(doc: Document) -> str:
    title = doc.title or f"doc {doc.id}"
    meta = doc.custom_meta or {}
    if meta.get("canonical_key"):
        # "DGCL § 145 — Indemnification ..." -> "DGCL § 145"
        return title.split("—")[0].split("(")[0].strip()
    # Exhibit numbers may be parenthesised: "Exhibit 10.(2)(A)", "Exhibit 10.12(A)".
    m = re.search(r"Exhibit\s+\d+\.[\d.]*(?:\([0-9A-Za-z]+\))*", title, re.IGNORECASE)
    if m:
        co = company_of(title)
        return f"{co.split()[0]} {m.group(0)}" if co else m.group(0)
    co = company_of(title)
    return f"{co} S-1" if co else title[:40]


authority_corpora = list(
    Corpus.objects.filter(
        id__in=CorpusReference.objects.filter(target_corpus__isnull=False).values(
            "target_corpus_id"
        )
    ).order_by("id")
)
# An authority corpus can itself carry references (statutes cite statutes);
# classify it as authority, not filing.
filing_corpora = list(
    Corpus.objects.filter(references__isnull=False)
    .exclude(id__in=[c.id for c in authority_corpora])
    .distinct()
    .order_by("id")
)
ref_corpora = filing_corpora + authority_corpora

refs = CorpusReference.objects.filter(
    corpus__in=ref_corpora, reference_type="LAW"
).select_related("source_annotation")

doc_ids: set[int] = set()
ghost_keys: set[str] = set()
edge_weight: Counter = Counter()  # (src_node, tgt_node, type) -> mentions

for ref in refs:
    src_doc = ref.source_annotation.document_id
    if ref.reference_type == "LAW":
        doc_ids.add(src_doc)
        if ref.target_document_id:
            if ref.target_document_id == src_doc:
                continue  # self-citation ("this section") — no edge to draw
            doc_ids.add(ref.target_document_id)
            edge_weight[(f"doc:{src_doc}", f"doc:{ref.target_document_id}", "LAW")] += 1
        elif ref.canonical_key:
            # Roll unresolved keys up to their section root so subsection
            # variants (506(b)/(c)/(d)) share one ghost node.
            root = candidate_keys(ref.canonical_key)[-1]
            ghost_keys.add(root)
            edge_weight[(f"doc:{src_doc}", f"key:{root}", "LAW_EXTERNAL")] += 1

for rel in DocumentRelationship.objects.filter(corpus__in=ref_corpora):
    doc_ids.add(rel.source_document_id)
    doc_ids.add(rel.target_document_id)
    edge_weight[
        (f"doc:{rel.source_document_id}", f"doc:{rel.target_document_id}", "DOCUMENT")
    ] += 1

degree: Counter = Counter()
for (src, tgt, _t), w in edge_weight.items():
    degree[src] += w
    degree[tgt] += w

docs = {d.id: d for d in Document.objects.filter(id__in=doc_ids)}
doc_corpus = defaultdict(set)
for c in filing_corpora + authority_corpora:
    for did in c.document_paths.filter(
        is_current=True, is_deleted=False, document_id__in=doc_ids
    ).values_list("document_id", flat=True):
        doc_corpus[did].add(c.id)

corpus_titles = {c.id: c.title for c in filing_corpora + authority_corpora}
filing_ids = {c.id for c in filing_corpora}

nodes = []
for did, doc in docs.items():
    cid = sorted(doc_corpus.get(did, set()))[0] if doc_corpus.get(did) else None
    kind = doc_kind(doc)
    company = company_of(doc.title or "")
    if company is None and kind != "statute" and cid in filing_ids:
        company = corpus_group_name(corpus_titles.get(cid, ""))
    nodes.append(
        {
            "id": f"doc:{did}",
            "label": short_label(doc),
            "title": doc.title,
            "kind": kind,
            "corpus_id": cid,
            "company": company,
            "authority": (doc.custom_meta or {}).get("authority"),
            "degree": degree[f"doc:{did}"],
        }
    )
for key in sorted(ghost_keys):
    prefix = key.split(":", 1)[0]
    nodes.append(
        {
            "id": f"key:{key}",
            "label": f"{AUTHORITY_DISPLAY.get(prefix, prefix)} § {key.split(':', 1)[1]}",
            "title": key,
            "kind": "external",
            "corpus_id": None,
            "company": None,
            "authority": prefix,
            "degree": degree[f"key:{key}"],
        }
    )

edges = [
    {"source": src, "target": tgt, "type": typ, "weight": w}
    for (src, tgt, typ), w in sorted(edge_weight.items())
]

graph = {
    "corpora": [
        {"id": c.id, "title": c.title, "kind": "filing"} for c in filing_corpora
    ]
    + [{"id": c.id, "title": c.title, "kind": "authority"} for c in authority_corpora],
    "nodes": nodes,
    "edges": edges,
    "stats": {
        "documents": len(docs),
        "external_keys": len(ghost_keys),
        "edges": len(edges),
        "mentions": sum(edge_weight.values()),
    },
}

with open(OUT_PATH, "w") as f:
    json.dump(graph, f, indent=1)

print(
    f"governance graph: {len(nodes)} nodes, {len(edges)} edges, "
    f"{graph['stats']['mentions']} mentions -> {OUT_PATH}"
)
