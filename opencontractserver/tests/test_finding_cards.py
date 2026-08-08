"""The structured finding card.

Exists to replace prose that every consumer had to re-parse. The tests that
matter are about *semantics a phrasing cannot carry* — above all whether an
interval is half-open, since that is what decides which regime owns the
boundary day.
"""

from typing import Any

from django.test import TestCase

from opencontractserver.enrichment.finding_cards import (
    ObligationCard,
    ObligationSchema,
    RegimeCard,
)

#: The scale the GridDossier corpus configures in its CAML. Declared HERE, in
#: the test, rather than in the schema module — that is the whole point of the
#: change: a ramp is a property of the subject under study, not of the card.
RAMP_SCHEMA = ObligationSchema(
    threshold_unit="MW", threshold_steps=(25, 50, 75, 100), threshold_label="ramp"
)


def _card(**overrides) -> RegimeCard:
    """A July-10 regime card, with fields overridden per test.

    Built then copied rather than assembled from a kwargs dict: a dict holding
    strings and lists types as ``dict[str, object]``, which cannot be unpacked
    into the constructor without a type error at every field. ``model_copy``
    skips validation, which is what a fixture wants.
    """
    base = RegimeCard(
        as_of_date="2026-07-10",
        applicable_process="Legacy LLIS",
        authority_status="Controlling through end of day",
        effective_interval_start="2022-03-25",
        effective_interval_end="2026-07-11",
        confidence="HIGH",
        unresolved_qualifications=["Transition exceptions"],
    )
    return base.model_copy(update=overrides) if overrides else base


class FindingCardIntervalTests(TestCase):
    """``[start, end)`` — the end is exclusive, and that is the whole point."""

    def test_the_last_day_of_a_regime_is_covered(self):
        # The rule runs THROUGH 10 July. A system that treated the transition as
        # "sometime on the 10th" answers the reference question wrongly.
        self.assertTrue(_card().covers("2026-07-10"))

    def test_the_cutover_date_is_not_covered_by_the_prior_regime(self):
        # The single most common way a transition answer goes quietly wrong: an
        # inclusive end date makes both regimes claim 11 July.
        self.assertFalse(_card().covers("2026-07-11"))

    def test_a_date_before_the_start_is_not_covered(self):
        self.assertFalse(_card().covers("2020-01-01"))

    def test_an_open_ended_interval_covers_everything_after_its_start(self):
        card = _card(
            as_of_date="2026-07-11",
            effective_interval_start="2026-07-11",
            effective_interval_end=None,
        )
        self.assertTrue(card.covers("2026-07-11"))
        self.assertTrue(card.covers("2030-01-01"))
        self.assertFalse(card.covers("2026-07-10"))

    def test_interval_renders_half_open_with_an_explicit_open_end(self):
        self.assertEqual(_card().render_interval(), "[2022-03-25, 2026-07-11)")
        open_ended = _card(effective_interval_end=None)
        self.assertEqual(open_ended.render_interval(), "[2022-03-25, …)")

    def test_two_adjacent_cards_partition_the_boundary(self):
        """No date is claimed by both regimes, and none falls through."""
        before = _card()
        after = _card(
            as_of_date="2026-07-11",
            applicable_process="Batch Zero",
            effective_interval_start="2026-07-11",
            effective_interval_end=None,
        )
        self.assertTrue(before.covers("2026-07-10"))
        self.assertFalse(after.covers("2026-07-10"))
        self.assertFalse(before.covers("2026-07-11"))
        self.assertTrue(after.covers("2026-07-11"))


class RecordFindingCardValidationTests(TestCase):
    """``record_finding``'s optional card half, validated before it is stored.

    These run against the pure helper rather than the tool closure, which needs
    a live agent and a Celery task around it.
    """

    @staticmethod
    def _build(**overrides):
        from opencontractserver.tasks.research_tasks import _build_finding_card

        # Annotated: a bare literal types as dict[str, Sequence[str]], which
        # cannot unpack into the str/list-typed parameters.
        kwargs: dict[str, Any] = {
            "as_of_date": "2026-07-10",
            "applicable_process": "Legacy LLIS",
            "authority_status": "Controlling through end of day",
            "effective_interval_start": "2025-12-15",
            "effective_interval_end": "2026-07-11",
            "primary_authority_effective_from": "2025-12-15",
            "confidence": "HIGH",
            "unresolved_qualifications": ["Transition exceptions"],
            # A regime card has no obligor, so the attribution gate never
            # reads this; passed because the parameter is deliberately
            # required (see ``_build_finding_card``).
            "cited_passages": [],
            "schema": RAMP_SCHEMA,
        }
        kwargs.update(overrides)
        return _build_finding_card(**kwargs)

    def test_a_finding_with_no_card_fields_is_not_a_card(self):
        card, error = self._build(
            as_of_date=None,
            applicable_process=None,
            authority_status=None,
            effective_interval_start=None,
            effective_interval_end=None,
            primary_authority_effective_from=None,
            confidence=None,
            unresolved_qualifications=None,
        )
        self.assertIsNone(card)
        self.assertIsNone(error)

    def test_a_complete_card_is_accepted(self):
        card, error = self._build()
        self.assertIsNone(error)
        self.assertEqual(card["effective_interval_end"], "2026-07-11")
        self.assertEqual(card["confidence"], "HIGH")

    def test_a_half_filled_card_is_refused(self):
        # Worse than a plain finding: a consumer cannot tell an absent field
        # from an unestablished one.
        card, error = self._build(authority_status=None)
        self.assertIsNone(card)
        self.assertIn("authority_status", error)

    def test_an_authority_effective_after_the_day_it_is_cited_for_is_refused(self):
        # The error this whole shape exists to catch: a run cited the revised
        # Planning Guide (effective 2026-07-11) as the authority for
        # 2026-07-10. A document effective later cannot be what governed that
        # day, even where the newer version describes the transition.
        card, error = self._build(primary_authority_effective_from="2026-07-11")
        self.assertIsNone(card)
        self.assertIn("cannot be what", error)
        self.assertIn("superseded", error)

    def test_an_authority_effective_on_the_day_is_fine(self):
        card, _ = self._build(
            as_of_date="2026-07-11",
            effective_interval_start="2026-07-11",
            effective_interval_end=None,
            primary_authority_effective_from="2026-07-11",
        )
        self.assertIsNotNone(card)

    def test_an_inverted_interval_is_refused(self):
        card, error = self._build(effective_interval_end="2025-01-01")
        self.assertIsNone(card)
        self.assertIn("EXCLUSIVE", error)

    def test_confidence_is_normalised_and_constrained(self):
        card, _ = self._build(confidence="high")
        self.assertEqual(card["confidence"], "HIGH")
        card, error = self._build(confidence="fairly sure")
        self.assertIsNone(card)
        self.assertIn("HIGH, MEDIUM or LOW", error)

    def test_an_empty_qualifications_list_is_refused(self):
        # "We looked and found none" and "nobody filled this in" must not
        # render identically — that ambiguity is what the card exists to
        # remove, so the agent has to say something either way.
        card, error = self._build(unresolved_qualifications=[])
        self.assertIsNone(card)
        self.assertIn("cannot be empty", error)

    def test_whitespace_only_qualifications_are_refused(self):
        card, error = self._build(unresolved_qualifications=["   ", ""])
        self.assertIsNone(card)
        self.assertIn("cannot be empty", error)

    def test_an_explicit_none_is_accepted_and_kept(self):
        from opencontractserver.tasks.research_tasks import NOTHING_UNRESOLVED

        card, error = self._build(unresolved_qualifications=[NOTHING_UNRESOLVED])
        self.assertIsNone(error)
        self.assertEqual(card["unresolved_qualifications"], [NOTHING_UNRESOLVED])


class DeepResearchGroupPromptTests(TestCase):
    """The agent has to be told the cross-corpus tool exists.

    Without this the mission read "explore the corpus", ``search_across_group``
    was never mentioned, and a group-scoped run answered from the anchor corpus
    alone — the tool was wired up and simply never called.
    """

    @staticmethod
    def _prompt(**kwargs):
        from opencontractserver.research.constants import (
            build_deep_research_system_prompt,
        )

        base: dict[str, Any] = {
            "task_description": "what applied when",
            "corpus_title": "ERCOT Current Large-Load Rules",
            "corpus_description": None,
            "max_steps": 60,
        }
        base.update(kwargs)
        return build_deep_research_system_prompt(**base)

    def test_a_group_scoped_run_is_told_about_the_cross_corpus_tool(self):
        prompt = self._prompt(corpus_group_title="DFW Large-Load Public Authorities")
        self.assertIn("search_across_group", prompt)
        self.assertIn("DFW Large-Load Public Authorities", prompt)
        # The distinction that matters: the default tool does NOT leave the
        # anchor corpus, so an agent that only uses it silently under-answers.
        self.assertIn("ONLY the anchor corpus", prompt)

    def test_a_corpus_only_run_is_not_offered_a_tool_it_does_not_have(self):
        prompt = self._prompt()
        self.assertNotIn("search_across_group", prompt)
        self.assertIn("similarity_search", prompt)

    def test_a_group_run_is_told_how_little_of_the_group_the_anchor_is(self):
        # Twenty runs of a group-scoped question called search_across_group
        # exactly ZERO times: the agent searched the anchor, got hits, and
        # stopped. Nothing told it the anchor was 2 documents of the group's
        # 354, or that the corpus the question names was one of the nine it
        # never opened. Knowing the tool exists was not enough.
        prompt = self._prompt(
            corpus_group_title="DFW Large-Load Public Authorities",
            corpus_group_scale=(
                "10 corpora holding 354 documents in total. This anchor corpus "
                "holds 2 of them"
            ),
        )
        self.assertIn("354 documents", prompt)
        self.assertIn("holds 2 of them", prompt)
        self.assertIn("does not mean", prompt)

    def test_scale_is_omitted_rather_than_guessed_when_unknown(self):
        prompt = self._prompt(corpus_group_title="DFW Large-Load Public Authorities")
        self.assertIn("search_across_group", prompt)
        self.assertNotIn("documents in total", prompt)

    def test_both_scopes_are_told_a_search_hit_is_already_citable(self):
        # An earlier version of this prompt told the agent to PIN every finding
        # with an exact-phrase lookup after discovering it by meaning. That is
        # two retrievals per finding, and it halved the card yield: runs spent
        # 40+ calls on phrase lookups (which were HITTING, not missing) and
        # filed two or three cards before the step budget ran down. A search
        # hit already carries its cite handle, so say so.
        for kwargs in ({}, {"corpus_group_title": "DFW Large-Load Public Authorities"}):
            prompt = self._prompt(**kwargs)
            self.assertIn("directly citable", prompt)
            self.assertIn("do NOT need a second lookup", prompt)


class ModelContextWindowTests(TestCase):
    """Prefix matching makes an unlisted ``gpt-4*`` model inherit 8K.

    ``gpt-4.1`` fell through to the bare ``gpt-4`` entry, so the compaction
    layer sized itself against 8,192 tokens for a model holding ~1M — shrinking
    history constantly and reporting a nearly-exhausted budget to an agent that
    had barely started.
    """

    @staticmethod
    def _window(model: str) -> int:
        from opencontractserver.llms.context_guardrails import (
            get_context_window_for_model,
        )

        return get_context_window_for_model(model)

    def test_gpt_41_is_not_sized_as_gpt_4(self):
        self.assertGreater(self._window("gpt-4.1"), 1_000_000)
        self.assertGreater(self._window("gpt-4.1-mini"), 1_000_000)

    def test_the_provider_prefix_does_not_change_the_answer(self):
        self.assertEqual(self._window("openai:gpt-4.1"), self._window("gpt-4.1"))

    def test_the_models_that_really_are_8k_still_are(self):
        # The bare gpt-4 entry is correct for gpt-4 itself; the bug was only in
        # what silently inherited it.
        self.assertEqual(self._window("gpt-4"), 8_192)
        self.assertEqual(self._window("gpt-4-turbo"), 128_000)
        self.assertEqual(self._window("gpt-4o"), 128_000)


class ObligationCardTests(TestCase):
    """The project-readiness shape, and the acceptance gates expressed as code.

    A regime card is built around an interval. "Which requirements apply, which
    forms are needed, what is still unknown" has no interval, and forcing it
    through the regime shape pushed the substance back into prose.
    """

    @staticmethod
    def _build(**overrides):
        from opencontractserver.tasks.research_tasks import _build_finding_card

        kwargs: dict[str, Any] = {
            "as_of_date": None,
            "applicable_process": None,
            "authority_status": None,
            "effective_interval_start": None,
            "effective_interval_end": None,
            "primary_authority_effective_from": None,
            "confidence": "HIGH",
            "unresolved_qualifications": ["Whether security has been posted"],
            "obligation": "Post financial security for the interconnection",
            "applicability": "GENERALLY_APPLICABLE",
            "applies_at": [],
            "responsible_party": "Interconnecting Large Load Entity",
            "preparer": None,
            "submitter": None,
            "recipient": "Oncor",
            "certifier": None,
            "approval_date": None,
            "effective_date": None,
            "service_request_date": None,
            "application_date": None,
            "commencement_date": None,
            "form_reference": "Protocol Section 23, Form W",
            "material": True,
            "deadline": "2026-07-24",
            "has_citations": True,
            # Names the obligor the way operative text actually does — full
            # term and defined acronym — so the attribution gate grounds both
            # spellings a card might use.
            "cited_passages": [
                "The Interconnecting Large Load Entity (ILLE) shall post "
                "financial security of $50,000 per MW prior to the execution "
                "of the interconnection agreement."
            ],
            "schema": RAMP_SCHEMA,
        }
        kwargs.update(overrides)
        return _build_finding_card(**kwargs)

    def test_a_complete_obligation_card_is_accepted(self):
        card, error = self._build()
        self.assertIsNone(error)
        assert card is not None
        self.assertEqual(card["kind"], "OBLIGATION")
        self.assertEqual(card["applicability"], "GENERALLY_APPLICABLE")

    def test_an_obligation_needs_an_obligor(self):
        card, error = self._build(responsible_party=None)
        self.assertIsNone(card)
        self.assertIn("responsible_party", error)

    def test_an_obligation_needs_text(self):
        card, error = self._build(obligation="   ")
        self.assertIsNone(card)
        self.assertIn("obligation", error)

    def test_every_card_must_be_classified(self):
        card, error = self._build(applicability=None)
        self.assertIsNone(card)
        self.assertIn("applicability must be one of", error)

    def test_an_unknown_classification_is_refused(self):
        card, error = self._build(applicability="probably relevant")
        self.assertIsNone(card)
        self.assertIn("applicability must be one of", error)

    def test_classification_is_case_and_space_tolerant(self):
        card, _ = self._build(applicability="conditional")
        assert card is not None
        self.assertEqual(card["applicability"], "CONDITIONAL")
        card, _ = self._build(applicability="alternative pathway")
        assert card is not None
        self.assertEqual(card["applicability"], "ALTERNATIVE_PATHWAY")

    def test_phase_triggered_must_name_its_ramp_steps(self):
        # Otherwise "phase-triggered" is a label, not a classification: the
        # reader still cannot tell whether it bites at 25 MW or only at 100.
        card, error = self._build(applicability="PHASE_TRIGGERED", applies_at=[])
        self.assertIsNone(card)
        self.assertIn("applies_at", error)

    def test_phase_triggered_with_steps_is_accepted_and_sorted(self):
        card, error = self._build(
            applicability="PHASE_TRIGGERED", applies_at=[100, 75, 75]
        )
        self.assertIsNone(error)
        assert card is not None
        self.assertEqual(card["applies_at"], [75, 100])

    def test_a_ramp_step_outside_the_evaluated_set_is_refused(self):
        card, error = self._build(applicability="PHASE_TRIGGERED", applies_at=[60])
        self.assertIsNone(card)
        self.assertIn("not ramp steps", error)

    def test_a_material_obligation_without_a_citation_is_blocked(self):
        # Refused at the door rather than filtered at finalisation: a card
        # dropped silently later reads to the model as if it was accepted.
        card, error = self._build(material=True, has_citations=False)
        self.assertIsNone(card)
        self.assertIn("MATERIAL", error)
        self.assertIn("supporting_source_ids", error)

    def test_an_immaterial_card_may_stand_without_a_citation(self):
        card, error = self._build(material=False, has_citations=False)
        self.assertIsNone(error)
        assert card is not None
        self.assertFalse(card["material"])

    def test_an_obligor_the_cited_passage_never_names_is_marked_not_refused(self):
        # The misattribution two reviewers independently found: the obligation
        # is real and the citation is real, and the duty has been moved onto a
        # party the evidence does not mention. Refusing it lost the obligation
        # outright and sent the agent guessing at placeholder party names, so
        # the card is kept and labelled instead.
        card, error = self._build(responsible_party="Oncor Electric Delivery")
        self.assertIsNone(error)
        assert card is not None
        self.assertFalse(card["obligor_grounded"])
        self.assertEqual(card["responsible_party"], "Oncor Electric Delivery")

    def test_an_obligor_named_by_an_acronym_in_the_passage_is_grounded(self):
        # "TSP" is below the content-word length floor, so only the acronym
        # pass can see it. Without that, every defined-term party would read as
        # ungrounded.
        card, error = self._build(
            responsible_party="TSP",
            cited_passages=["The TSP shall submit the completed form to ERCOT."],
        )
        self.assertIsNone(error)
        assert card is not None
        self.assertTrue(card["obligor_grounded"])
        self.assertEqual(card["responsible_party"], "TSP")

    def test_a_citation_with_no_readable_text_cannot_ground_an_obligor(self):
        # Fails closed, matching the claim-support check: a citation with
        # nothing to read is not evidence of anything.
        card, error = self._build(cited_passages=[])
        self.assertIsNone(error)
        assert card is not None
        self.assertFalse(card["obligor_grounded"])

    def test_an_immaterial_card_is_not_held_to_the_attribution_check(self):
        # Context rather than a duty the project must discharge — it is already
        # exempt from the citation gate, and holding it to the stricter one
        # would be incoherent.
        card, error = self._build(
            material=False, responsible_party="Oncor Electric Delivery"
        )
        self.assertIsNone(error)
        assert card is not None
        self.assertTrue(card["obligor_grounded"])

    def test_the_six_date_kinds_are_kept_apart(self):
        card, error = self._build(
            approval_date="2026-06-18",
            effective_date="2026-07-11",
            service_request_date="2026-05-01",
            application_date="2026-05-15",
            deadline="2026-07-24",
            commencement_date="2027-03-01",
        )
        self.assertIsNone(error)
        assert card is not None
        # Approval is not effectiveness is not the filing date.
        self.assertEqual(card["approval_date"], "2026-06-18")
        self.assertEqual(card["effective_date"], "2026-07-11")
        self.assertNotEqual(card["approval_date"], card["effective_date"])
        self.assertEqual(len(ObligationCard(**card).stated_dates()), 6)

    def test_roles_that_match_the_responsible_party_are_not_counted_distinct(self):
        card, _ = self._build(
            responsible_party="ILLE", preparer="ILLE", submitter="Oncor"
        )
        assert card is not None
        roles = ObligationCard(**card).distinct_roles()
        self.assertNotIn("preparer", roles)
        self.assertEqual(roles["submitter"], "Oncor")

    def test_a_blank_role_is_null_not_empty_string(self):
        # An absent role is a different claim from a role that coincides with
        # the responsible party, so it must not render as "".
        card, _ = self._build(preparer="   ")
        assert card is not None
        self.assertIsNone(card["preparer"])

    def test_form_and_deadline_are_optional(self):
        card, error = self._build(form_reference=None, deadline=None)
        self.assertIsNone(error)
        assert card is not None
        self.assertIsNone(card["form_reference"])
        self.assertIsNone(card["deadline"])

    def test_an_empty_qualification_is_refused_here_too(self):
        card, error = self._build(unresolved_qualifications=[])
        self.assertIsNone(card)
        self.assertIn("cannot be empty", error)

    def test_the_two_shapes_cannot_be_mixed(self):
        card, error = self._build(
            as_of_date="2026-07-11", applicable_process="Batch Zero"
        )
        self.assertIsNone(card)
        self.assertIn("not both", error)

    def test_a_regime_card_still_reports_its_own_kind(self):
        from opencontractserver.tasks.research_tasks import _build_finding_card

        card, error = _build_finding_card(
            as_of_date="2026-07-10",
            applicable_process="Legacy LLIS",
            authority_status="Controlling through end of day",
            effective_interval_start="2025-12-15",
            effective_interval_end="2026-07-11",
            primary_authority_effective_from="2025-12-15",
            confidence="HIGH",
            unresolved_qualifications=["Start date not established"],
            cited_passages=[],
            schema=RAMP_SCHEMA,
        )
        self.assertIsNone(error)
        assert card is not None
        self.assertEqual(card["kind"], "REGIME")


class ObligationSchemaConfigTests(TestCase):
    """The threshold scale is configuration, not a constant.

    It used to be ``RAMP_STEPS_MW = (25, 50, 75, 100)`` in the card schema, so
    the card served exactly one Texas interconnection project and silently
    refused any value outside that project's plan. It now comes from an
    ``obligation-schema`` marker in the corpus's own CAML article.
    """

    @staticmethod
    def _build(**overrides):
        from opencontractserver.tasks.research_tasks import _build_finding_card

        kwargs: dict[str, Any] = {
            "as_of_date": None,
            "applicable_process": None,
            "authority_status": None,
            "effective_interval_start": None,
            "effective_interval_end": None,
            "primary_authority_effective_from": None,
            "confidence": "HIGH",
            "unresolved_qualifications": ["None identified."],
            "obligation": "File the annual return",
            "applicability": "PHASE_TRIGGERED",
            "responsible_party": "The employer",
            "material": True,
            "has_citations": True,
            "cited_passages": ["An employer with 250 or more employees shall file."],
            "schema": ObligationSchema(),
        }
        kwargs.update(overrides)
        return _build_finding_card(**kwargs)

    def test_a_corpus_with_no_configured_scale_accepts_any_threshold(self):
        # The generic default. Nothing to validate against, so nothing is
        # refused — an employment-law corpus is not wrong for using 250.
        card, error = self._build(applies_at=[250])
        self.assertIsNone(error)
        assert card is not None
        self.assertEqual(card["applies_at"], [250])
        self.assertIsNone(card["threshold_unit"])

    def test_phase_triggered_still_has_to_say_where_it_bites(self):
        # The requirement that survives without a scale: the classification is
        # meaningless if the card will not name a value.
        card, error = self._build(applies_at=[])
        self.assertIsNone(card)
        self.assertIn("applies_at", error)

    def test_a_configured_scale_refuses_a_value_it_does_not_contain(self):
        card, error = self._build(
            applies_at=[60],
            schema=ObligationSchema(
                threshold_unit="MW",
                threshold_steps=(25, 50, 75, 100),
                threshold_label="ramp",
            ),
        )
        self.assertIsNone(card)
        self.assertIn("ramp", error)
        self.assertIn("60", error)
        # Whole numbers read as whole numbers; "60.0 MW" invites the model to
        # echo a float back.
        self.assertNotIn("60.0", error)

    def test_a_configured_scale_stamps_its_unit_onto_the_card(self):
        # A bare 75 in a stored JSON column means nothing a year later.
        card, error = self._build(
            applies_at=[75],
            schema=ObligationSchema(threshold_unit="MW", threshold_steps=(25, 75)),
        )
        self.assertIsNone(error)
        assert card is not None
        self.assertEqual(card["threshold_unit"], "MW")


class ObligationSchemaFromCamlTests(TestCase):
    """Parsing the marker an author writes into the corpus article."""

    def test_a_full_marker_configures_unit_steps_and_label(self):
        from opencontractserver.corpuses.caml_intelligence import (
            parse_component_props,
        )

        caml = (
            "# ERCOT Large-Load Rules\n\n::: oc-component\n"
            "[component:obligation-schema unit=MW steps=25,50,75,100 label=ramp]\n"
            ":::\n"
        )
        schema = ObligationSchema.from_caml_props(
            parse_component_props(caml, "obligation-schema")
        )
        self.assertEqual(schema.threshold_unit, "MW")
        self.assertEqual(schema.threshold_steps, (25.0, 50.0, 75.0, 100.0))
        self.assertEqual(schema.threshold_label, "ramp")
        self.assertIn("ramp steps 25, 50, 75, 100 MW", schema.describe())

    def test_an_absent_marker_yields_the_unconstrained_default(self):
        from opencontractserver.corpuses.caml_intelligence import (
            parse_component_props,
        )

        schema = ObligationSchema.from_caml_props(
            parse_component_props("# Just an article\n", "obligation-schema")
        )
        self.assertFalse(schema.has_scale)
        self.assertEqual(schema.describe(), "")

    def test_a_malformed_steps_value_degrades_instead_of_raising(self):
        # A corpus author writing prose must never break a research run with a
        # typo, so a bad value drops the scale rather than exploding.
        schema = ObligationSchema.from_caml_props(
            {"unit": "MW", "steps": "25,fifty,100"}
        )
        self.assertFalse(schema.has_scale)
        self.assertEqual(schema.threshold_unit, "MW")

    def test_steps_are_deduplicated_and_ordered(self):
        schema = ObligationSchema.from_caml_props({"steps": "100,25,50,25"})
        self.assertEqual(schema.threshold_steps, (25.0, 50.0, 100.0))


class CardFieldContractTests(TestCase):
    """The stored card IS ``model_dump()``, so these names are a wire contract.

    The frontend embed
    (``frontend/src/components/corpuses/CorpusHome/intelligence/embeds/
    ResearchFindingsEmbed.tsx``) declares a matching TypeScript interface and
    reads these keys off the report's ``findings``. TypeScript cannot see this
    module, so a rename here is invisible over there: the component read
    ``card.owed_by`` — a name ``ObligationCard`` never had — and every real
    obligation card rendered a blank heading in production while the component
    suite stayed green against hand-authored mocks carrying the wrong shape.

    This is the tripwire. A field renamed, added or dropped fails HERE, next to
    a comment naming the file that has to change with it. It is deliberately a
    whole-set comparison rather than a spot-check of the fields the embed reads
    today: the embed grows, and a test that only knows about today's subset
    stops covering it the moment it does.
    """

    OBLIGATION_FIELDS = {
        "kind",
        "obligation",
        "applicability",
        "applies_at",
        "threshold_unit",
        "responsible_party",
        "preparer",
        "submitter",
        "recipient",
        "certifier",
        "obligor_grounded",
        "approval_date",
        "effective_date",
        "service_request_date",
        "application_date",
        "deadline",
        "commencement_date",
        "form_reference",
        "material",
        "confidence",
        "unresolved_qualifications",
    }

    REGIME_FIELDS = {
        "kind",
        "as_of_date",
        "applicable_process",
        "authority_status",
        "effective_interval_start",
        "effective_interval_end",
        "primary_authority_effective_from",
        "confidence",
        "unresolved_qualifications",
    }

    def test_obligation_card_field_names_are_pinned(self):
        self.assertEqual(set(ObligationCard.model_fields), self.OBLIGATION_FIELDS)

    def test_regime_card_field_names_are_pinned(self):
        self.assertEqual(set(RegimeCard.model_fields), self.REGIME_FIELDS)

    def test_a_dumped_card_carries_exactly_those_keys(self):
        # ``model_fields`` is the declaration; ``model_dump()`` is what is
        # actually stored on the report and shipped to the browser. Pin both,
        # so a serialisation alias could not diverge from the field list.
        dumped = ObligationCard(
            obligation="File the study",
            applicability="GENERALLY_APPLICABLE",
            responsible_party="The developer",
            confidence="HIGH",
            unresolved_qualifications=["nothing outstanding"],
        ).model_dump()
        self.assertEqual(set(dumped), self.OBLIGATION_FIELDS)
        # The heading the embed renders. Named explicitly because this is the
        # exact key that drifted.
        self.assertEqual(dumped["responsible_party"], "The developer")
