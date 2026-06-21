"""Phase 4: prefix rewrite rules — evaluation in both resolution seams + preview.

A rewrite rule (e.g. ``irc:N`` → ``usc-26:N``) is a mechanical fallback applied
AFTER explicit per-key equivalences in both ``_provider_for`` (ingestion) and
``find_authority_target`` (link resolution), so an explicit row always wins. The
``preview_rewrite_rule`` command dry-runs a rule without writing.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.documents.models import Document
from opencontractserver.enrichment.authorities import (
    AuthoritySection,
    bootstrap_authority_corpus,
    find_authority_target,
)
from opencontractserver.enrichment.data import mappings as M
from opencontractserver.enrichment.services import AuthorityDiscoveryService

User = get_user_model()


class ShippedRewriteRuleTests(TestCase):
    def test_yaml_ships_the_irc_rule(self):
        rules = M.iter_rewrite_rules()
        assert any("irc:" in r["pattern"] for r in rules), rules

    def test_apply_rewrite_rules_default_cache(self):
        # Uses the shipped YAML (default cache), not an explicit rule list.
        assert M.apply_rewrite_rules("irc:501") == ["usc-26:501"]
        assert M.apply_rewrite_rules("dgcl:145") == []


class ProviderForRewriteFallbackTests(TestCase):
    def test_irc_key_bridges_via_rewrite_rule(self):
        # No explicit irc:501 equivalence — only the mechanical rule can bridge it.
        assert not AuthorityKeyEquivalence.objects.filter(from_key="irc:501").exists()
        name, provider, fetch_key = AuthorityDiscoveryService._provider_for("irc:501")
        assert name is not None
        assert fetch_key == "usc-26:501"
        assert provider.can_handle(fetch_key)

    def test_explicit_equivalence_beats_rewrite_rule(self):
        # An explicit row mapping irc:999 -> usc-15:999 must win over the rule's
        # usc-26:999 (per-key precedence).
        AuthorityKeyEquivalence.objects.create(
            from_key="irc:999", to_key="usc-15:999", source="manual"
        )
        _name, _provider, fetch_key = AuthorityDiscoveryService._provider_for("irc:999")
        assert fetch_key == "usc-15:999"

    def test_equivalence_then_rewrite_compose(self):
        # An equivalence pointing INTO a rewriteable key must resolve: foo:1 has
        # no provider, its equivalence counterpart irc:7 has no provider either,
        # but the rewrite rule irc:N -> usc-26:N yields a provider-handled key.
        # The ingest seam must compose equivalence+rewrite (symmetric with
        # find_authority_target), not give up after the equivalence hop.
        AuthorityKeyEquivalence.objects.create(
            from_key="foo:1", to_key="irc:7", source="manual"
        )
        _name, _provider, fetch_key = AuthorityDiscoveryService._provider_for("foo:1")
        assert fetch_key == "usc-26:7"

    def test_unmatched_key_is_unsupported(self):
        name, _provider, fetch_key = AuthorityDiscoveryService._provider_for("madeup:1")
        assert name is None
        assert fetch_key is None


class FindAuthorityTargetRewriteFallbackTests(TransactionTestCase):
    def test_irc_key_resolves_to_usc_doc_via_rewrite(self):
        user = User.objects.create_user(username="rewrite-user", password="p")
        bootstrap_authority_corpus(
            creator_id=user.id,
            corpus_title="USC Title 26",
            sections=[
                AuthoritySection(
                    key="usc-26:501",
                    heading="Exemption from tax on corporations",
                    text="An organization described in subsection (c) ...",
                )
            ],
            make_public=True,
            relink=False,
        )
        doc = Document.objects.get(custom_meta__canonical_key="usc-26:501")
        # irc:501 has no document and no explicit equivalence — only the rewrite
        # rule (irc:N -> usc-26:N) can reach the usc-26:501 document.
        found = find_authority_target("irc:501", user)
        assert found is not None
        assert found.pk == doc.pk


class PreviewRewriteRuleCommandTests(TestCase):
    def test_preview_adhoc_rule_over_explicit_keys(self):
        out = StringIO()
        call_command(
            "preview_rewrite_rule",
            "--keys",
            "irc:501,dgcl:145",
            "--pattern",
            r"^irc:(?P<n>.+)$",
            "--replacement",
            r"usc-26:\g<n>",
            stdout=out,
        )
        text = out.getvalue()
        assert "irc:501 -> usc-26:501" in text
        assert "ingestable" in text
        # dgcl:145 does not match the irc rule.
        assert "dgcl:145 ->" not in text

    def test_preview_shipped_yaml_rule(self):
        out = StringIO()
        call_command("preview_rewrite_rule", "--keys", "irc:777", stdout=out)
        assert "irc:777 -> usc-26:777" in out.getvalue()

    def test_pattern_without_replacement_errors(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("preview_rewrite_rule", "--pattern", "^irc:(.+)$")
