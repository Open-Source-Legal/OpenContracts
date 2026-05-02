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


CREATE_LABEL_FOR_LABELSET_MUTATION = """
    mutation CreateLabelForLabelset(
        $labelsetId: String!
        $text: String
        $color: String
        $labelType: String
    ) {
        createAnnotationLabelForLabelset(
            labelsetId: $labelsetId
            text: $text
            color: $color
            labelType: $labelType
        ) {
            ok
            message
            objId
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

    def test_remove_labels_rejects_non_owner_even_when_labelset_is_public(self) -> None:
        """``is_public`` grants READ only — it does not grant UPDATE.

        Without an explicit guardian UPDATE grant a non-creator must not be
        able to mutate the labelset's membership, regardless of ``is_public``.
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
        self.assertFalse(data["ok"])
        self.assertIn("Error removing label(s) from labelset", data["message"])

        # Nothing should have changed
        remaining = set(self.labelset.annotation_labels.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.label_a.pk, self.label_b.pk, self.label_c.pk})

    def test_remove_labels_allows_non_owner_with_explicit_update_permission(
        self,
    ) -> None:
        """A non-creator who has been granted UPDATE on the labelset may remove labels.

        Pins the documented model: anyone with edit rights to a LabelSet can
        add/remove labels — not just the creator. See
        ``docs/permissioning/consolidated_permissioning_guide.md``.
        """

        set_permissions_for_obj_to_user(
            self.other_user, self.labelset, [PermissionTypes.UPDATE]
        )

        variables = {
            "labelIds": [to_global_id("AnnotationLabelType", self.label_a.id)],
            "labelsetId": to_global_id("LabelSetType", self.labelset.id),
        }

        result = self.other_client.execute(REMOVE_LABELS_MUTATION, variables=variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["removeAnnotationLabelsFromLabelset"]
        self.assertTrue(
            data["ok"],
            msg=f"Mutation did not succeed. Message: {data['message']}",
        )
        remaining = set(self.labelset.annotation_labels.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.label_b.pk, self.label_c.pk})


class CreateLabelForLabelsetMutationTestCase(TestCase):
    """Coverage for ``CreateLabelForLabelsetMutation`` permission gating.

    The mutation moved from creator-only to guardian-permission-based, so we
    pin the four cases reviewers asked for: creator happy path, non-creator
    rejection, ``is_public`` is not enough, and explicit ``UPDATE`` works.
    """

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

    def _create_variables(self, text: str = "New Label") -> dict:
        return {
            "labelsetId": to_global_id("LabelSetType", self.labelset.id),
            "text": text,
            "color": "#ABCDEF",
            "labelType": LabelType.SPAN_LABEL,
        }

    def test_creator_can_create_label(self) -> None:
        """Regression guard: the creator's happy path still works."""

        result = self.client.execute(
            CREATE_LABEL_FOR_LABELSET_MUTATION,
            variables=self._create_variables("Creator Label"),
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createAnnotationLabelForLabelset"]
        self.assertTrue(
            data["ok"],
            msg=f"Mutation did not succeed. Message: {data['message']}",
        )
        self.assertEqual(data["message"], "SUCCESS")
        self.assertIsNotNone(data["objId"])
        self.assertEqual(self.labelset.annotation_labels.count(), 1)
        self.assertEqual(self.labelset.annotation_labels.first().text, "Creator Label")

    def test_non_owner_without_permission_is_rejected(self) -> None:
        """A user with no permission on the labelset cannot add labels."""

        result = self.other_client.execute(
            CREATE_LABEL_FOR_LABELSET_MUTATION,
            variables=self._create_variables("Should Not Exist"),
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createAnnotationLabelForLabelset"]
        self.assertFalse(data["ok"])
        self.assertEqual(self.labelset.annotation_labels.count(), 0)
        # No orphan AnnotationLabel should leak when the caller is unauthorized
        self.assertFalse(
            AnnotationLabel.objects.filter(text="Should Not Exist").exists()
        )

    def test_non_owner_rejected_even_when_labelset_is_public(self) -> None:
        """``is_public`` is READ-only and must not grant CREATE rights."""

        self.labelset.is_public = True
        self.labelset.save()

        result = self.other_client.execute(
            CREATE_LABEL_FOR_LABELSET_MUTATION,
            variables=self._create_variables("Public Should Not Help"),
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createAnnotationLabelForLabelset"]
        self.assertFalse(data["ok"])
        self.assertEqual(self.labelset.annotation_labels.count(), 0)
        self.assertFalse(
            AnnotationLabel.objects.filter(text="Public Should Not Help").exists()
        )

    def test_non_owner_with_explicit_update_permission_can_create(self) -> None:
        """A collaborator with guardian UPDATE on the labelset may add labels."""

        set_permissions_for_obj_to_user(
            self.other_user, self.labelset, [PermissionTypes.UPDATE]
        )

        result = self.other_client.execute(
            CREATE_LABEL_FOR_LABELSET_MUTATION,
            variables=self._create_variables("Collaborator Label"),
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createAnnotationLabelForLabelset"]
        self.assertTrue(
            data["ok"],
            msg=f"Mutation did not succeed. Message: {data['message']}",
        )
        self.assertEqual(self.labelset.annotation_labels.count(), 1)
        new_label = self.labelset.annotation_labels.first()
        self.assertEqual(new_label.text, "Collaborator Label")
        self.assertEqual(new_label.creator_id, self.other_user.id)

    def test_blank_text_is_rejected(self) -> None:
        """An empty/whitespace ``text`` must NOT silently fall back to the
        ``"Text Label"`` model default — clients should see a validation error.
        """

        result = self.client.execute(
            CREATE_LABEL_FOR_LABELSET_MUTATION,
            variables=self._create_variables("   "),
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createAnnotationLabelForLabelset"]
        self.assertFalse(data["ok"])
        self.assertIn("blank", data["message"].lower())
        self.assertEqual(self.labelset.annotation_labels.count(), 0)

    def test_omitted_text_is_rejected(self) -> None:
        """A client that omits ``text`` entirely must NOT receive a
        ``"Text Label"`` row by default — the model default is hidden
        behind a required-field guard.
        """
        # GraphQL doesn't support omitting an argument from variables,
        # but the resolver default is ``text=None``; build a custom
        # variables dict that simulates the omission by passing None
        # via JSON null (the GraphQL coercion that sends ``null`` for an
        # unsupplied optional argument).
        variables = self._create_variables("placeholder")
        variables["text"] = None

        result = self.client.execute(
            CREATE_LABEL_FOR_LABELSET_MUTATION,
            variables=variables,
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createAnnotationLabelForLabelset"]
        self.assertFalse(data["ok"])
        self.assertIn("blank", data["message"].lower())
        self.assertEqual(self.labelset.annotation_labels.count(), 0)
        self.assertFalse(AnnotationLabel.objects.filter(text="Text Label").exists())

    def test_permission_denied_message_does_not_leak_validation_state(
        self,
    ) -> None:
        """A non-owner caller hitting validation should still get the
        same generic 404-style denial as if the labelset didn't exist —
        the permission check runs FIRST so blank-text vs
        permission-denied are indistinguishable to outsiders.
        """
        # ``other_user`` has no permission on ``self.labelset``.  Send
        # an *invalid* mutation (blank text) — the response must look
        # like a "does not exist", NOT like "blank text".
        variables = self._create_variables("   ")

        result = self.other_client.execute(
            CREATE_LABEL_FOR_LABELSET_MUTATION,
            variables=variables,
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createAnnotationLabelForLabelset"]
        self.assertFalse(data["ok"])
        # Must NOT mention "blank" — that would leak that the caller's
        # request was structurally valid but rejected by permission.
        self.assertNotIn("blank", data["message"].lower())
        self.assertIn("does not exist", data["message"].lower())

    def test_nonexistent_labelset_returns_same_not_found_message(self) -> None:
        """A valid relay-encoded ID for a PK that does not exist must
        produce the same not-found response as a permission denial,
        pinning the IDOR-safe behaviour against future refactors.
        """
        variables = self._create_variables("Should Not Be Created")
        variables["labelsetId"] = to_global_id("LabelSetType", 999_999)

        result = self.client.execute(
            CREATE_LABEL_FOR_LABELSET_MUTATION,
            variables=variables,
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createAnnotationLabelForLabelset"]
        self.assertFalse(data["ok"])
        self.assertIn("does not exist", data["message"].lower())
        self.assertFalse(
            AnnotationLabel.objects.filter(text="Should Not Be Created").exists()
        )
