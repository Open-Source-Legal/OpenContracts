- **GraphQL spec validation restored on the served endpoint (security).**
  ``GraphQLView(validation_rules=[DepthLimit…])`` REPLACED graphql-core's
  spec rule set (that is ``validate()``'s semantics for an explicit rules
  list), silently disabling every standard GraphQL validation — unknown
  arguments/fields and variable-type checks — in all environments. Invalid
  queries executed with the bogus parts ignored, which let ~26 invalid
  frontend documents ship unnoticed (several backing silently-broken
  features). ``config/graphql/schema.py`` now builds
  ``[*specified_rules, DepthLimitValidationRule(, DisableIntrospection)]``,
  pinned by ``test_security_hardening.TestServedValidationRulesIncludeSpecRules``.
  Every shipped frontend document is now swept in CI by
  ``opencontractserver/tests/architecture/test_frontend_graphql_documents.py``
  (ad-hoc: ``scripts/validate_frontend_graphql.py``; the sweep strips Apollo
  ``@client`` selections and skips fragment-only/interpolated documents).
- **All 26 invalid frontend documents repaired**, including features that
  could never have worked: ``deleteMetadataColumn`` and ``updateFieldset``
  were called by the UI but did not exist server-side (both now implemented
  in ``config/graphql/extract_mutations.py`` via the BaseService
  get_or_none/require_permission pattern with IDOR-unified messages);
  ``GET_CORPUS_CHAT_MESSAGES`` used a misspelled argument + relay shape on a
  plain list field (corpus chat history always loaded empty objects);
  ``tokenAuth`` was schema-conditional on ``USE_AUTH0`` (now always the
  ``WithUser`` payload, so the login document validates everywhere); the
  document-by-id redirect selected the nonexistent ``DocumentType.corpus``
  (corpus context now sourced from the route's slug resolution where it
  exists — the previous mock-only field meant graph-node click-throughs
  always landed on standalone paths); dead ``ADD_DOCUMENT_TO_CORPUS``
  removed; plus variable-type (ID!/String!, JSONString/GenericScalar,
  String/enum) and payload-field corrections across vote, thread-moderation,
  research-report, TOC and corpus-list documents.
- **Presigned file URLs no longer outlive their signatures.** The AWS
  settings branch derived the shared file-URL cache lifetime from
  ``_AWS_EXPIRY`` (the stored objects' HTTP CacheControl max-age, 7 days)
  instead of the presign lifetime (``AWS_QUERYSTRING_EXPIRE``, 1 hour), so
  redis served dead 403 pdf/pawls/txt links for up to 5 hours.
  ``AWS_QUERYSTRING_EXPIRE`` is now explicit, the cache TTL derives from it,
  and ``clamp_shared_url_cache_ttl`` (``opencontractserver/utils/files.py``)
  enforces TTL ≤ half the signature lifetime even against env overrides.
- **3-minute analysis-annotation responses fixed.**
  ``UserFeedbackQuerySet.visible_to_user`` expressed annotation-inherited
  visibility as ``commented_annotation_id__in=<visible-annotations
  subquery>`` — an uncorrelated ``IN`` materialized over the entire
  annotations table on every evaluation (~0.8s each; 216 pagination counts
  made ``GetAnnotationsForAnalysis`` take ~176s for a 108-mention document).
  Rewritten as a correlated ``Exists`` pinned to the feedback row's
  annotation id — identical semantics (permissioning invariant suites pass),
  measured 176s → 2.3s. Shape pinned by
  ``test_feedback.TestVisibilityQueryShape``.
