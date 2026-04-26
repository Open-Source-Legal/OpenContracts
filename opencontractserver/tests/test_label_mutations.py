"""Tests for GraphQL label/labelset mutations in ``config.graphql.label_mutations``.

Currently focuses on the regression fix for issue #1359 –
``RemoveLabelsFromLabelsetMutation`` previously referenced
``labelset.documents`` (a non-existent attribute), which caused every
invocation to silently fail inside a broad ``except Exception`` swallower.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.types.enums import LabelType, PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


REMOVE_LABELS_MUTATION = """
    mutation RemoveAnnotationLabels($labelIds: [String]!, $labelsetId: String!) {
        removeAnnotationLabelsFromLabelset(
            labelIds: $labelIds
            labelsetId: $labelsetId
        ) {
            ok
            message
        }
    }
"""


class RemoveLabelsFromLabelsetMutationTestCase(TestCase):
    """Regression coverage for issue #1359."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", password="otherpassword"
        )

        self.client = Client(schema, context_value=TestContext(self.user))
        self.other_client = Client(schema, context_value=TestContext(self.other_user))

        self.labelset = LabelSet.objects.create(
            title="Test Labelset",
            description="Test labelset",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.labelset, [PermissionTypes.CRUD]
        )

        self.label_a = AnnotationLabel.objects.create(
            text="Label A",
            label_type=LabelType.SPAN_LABEL,
            color="#FF0000",
            creator=self.user,
        )
        self.label_b = AnnotationLabel.objects.create(
            text="Label B",
            label_type=LabelType.SPAN_LABEL,
            color="#00FF00",
            creator=self.user,
        )
        self.label_c = AnnotationLabel.objects.create(
            text="Label C",
            label_type=LabelType.SPAN_LABEL,
            color="#0000FF",
            creator=self.user,
        )
        self.labelset.annotation_labels.add(self.label_a, self.label_b, self.label_c)

    def test_remove_labels_from_labelset_actually_removes_them(self) -> None:
        """Mutation should remove the specified labels from the labelset M2M."""

        variables = {
            "labelIds": [
                to_global_id("AnnotationLabelType", self.label_a.id),
                to_global_id("AnnotationLabelType", self.label_b.id),
            ],
            "labelsetId": to_global_id("LabelSetType", self.labelset.id),
        }

        result = self.client.execute(REMOVE_LABELS_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["removeAnnotationLabelsFromLabelset"]
        self.assertTrue(
            data["ok"],
            msg=f"Mutation did not succeed. Message: {data['message']}",
        )
        self.assertEqual(data["message"], "Success")

        remaining = set(self.labelset.annotation_labels.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.label_c.pk})

        # Only the M2M link is removed — the labels themselves are not deleted
        self.assertTrue(AnnotationLabel.objects.filter(pk=self.label_a.pk).exists())
        self.assertTrue(AnnotationLabel.objects.filter(pk=self.label_b.pk).exists())

    def test_remove_labels_ignores_ids_not_in_labelset(self) -> None:
        """IDs that are not part of the labelset should be silently ignored."""

        stray = AnnotationLabel.objects.create(
            text="Stray",
            label_type=LabelType.SPAN_LABEL,
            color="#123456",
            creator=self.user,
        )
        variables = {
            "labelIds": [
                to_global_id("AnnotationLabelType", self.label_a.id),
                to_global_id("AnnotationLabelType", stray.id),
            ],
            "labelsetId": to_global_id("LabelSetType", self.labelset.id),
        }

        result = self.client.execute(REMOVE_LABELS_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["removeAnnotationLabelsFromLabelset"]
        self.assertTrue(data["ok"])

        remaining = set(self.labelset.annotation_labels.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.label_b.pk, self.label_c.pk})
        # The stray label is still alive and well
        self.assertTrue(AnnotationLabel.objects.filter(pk=stray.pk).exists())

    def test_remove_labels_rejects_non_owner_non_public(self) -> None:
        """A user who neither owns nor can see the labelset must not mutate it."""

        variables = {
            "labelIds": [to_global_id("AnnotationLabelType", self.label_a.id)],
            "labelsetId": to_global_id("LabelSetType", self.labelset.id),
        }

        result = self.other_client.execute(REMOVE_LABELS_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["removeAnnotationLabelsFromLabelset"]
        self.assertFalse(data["ok"])
        self.assertIn("Error removing label(s) from labelset", data["message"])

        # Nothing should have changed
        remaining = set(self.labelset.annotation_labels.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.label_a.pk, self.label_b.pk, self.label_c.pk})

    def test_remove_labels_empty_list_is_noop(self) -> None:
        """Empty ``labelIds`` should succeed without changing the labelset."""

        variables = {
            "labelIds": [],
            "labelsetId": to_global_id("LabelSetType", self.labelset.id),
        }

        result = self.client.execute(REMOVE_LABELS_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["removeAnnotationLabelsFromLabelset"]
        self.assertTrue(data["ok"])
        remaining = set(self.labelset.annotation_labels.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.label_a.pk, self.label_b.pk, self.label_c.pk})

    def test_remove_labels_allows_public_labelset(self) -> None:
        """A public labelset is editable via this mutation by any authed user.

        This pins the current resolver behaviour (``Q(creator=user) | Q(is_public=True)``)
        so that future permission hardening is an intentional change rather than an
        accidental regression.
        """

        self.labelset.is_public = True
        self.labelset.save()

        variables = {
            "labelIds": [to_global_id("AnnotationLabelType", self.label_a.id)],
            "labelsetId": to_global_id("LabelSetType", self.labelset.id),
        }

        result = self.other_client.execute(REMOVE_LABELS_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["removeAnnotationLabelsFromLabelset"]
        self.assertTrue(data["ok"])
        remaining = set(self.labelset.annotation_labels.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.label_b.pk, self.label_c.pk})
