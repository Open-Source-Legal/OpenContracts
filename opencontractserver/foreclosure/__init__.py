"""California foreclosure compliance.

Integrates the ``legalis-ca-foreclosure`` ruleset — Civ. Code § 2924 et seq.
encoded as dated, versioned rules — with OpenContracts corpora.

The ruleset runs as a separate service rather than in-process. It is written in
Rust, and an FFI boundary would couple this deployment to a Rust toolchain and
turn the ruleset's panics into worker crashes. Over HTTP it is independently
deployable and independently versioned, at the cost of one network hop per
matter.

A foreclosure matter maps onto a corpus: each recorded instrument (Notice of
Default, Notice of Trustee's Sale, Trustee's Deed) is a document, and the
matter is the corpus they belong to. That is why this is a
``@corpus_analyzer_task`` rather than a per-document one — no single instrument
answers whether the three-month period elapsed.
"""
