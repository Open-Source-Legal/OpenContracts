"""Public profile traversal retains resource READ for transfers."""

from django.contrib.auth.models import Group
from django.test import TestCase
from guardian.shortcuts import assign_perm

from config.jwt_auth.shortcuts import get_token
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User, UserExport, UserImport
from opencontractserver.utils.ids import to_global_id
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

Transfer = UserExport | UserImport
TransferModel = type[UserExport] | type[UserImport]

FIELDS: dict[str, TransferModel] = {
    "userexportSet": UserExport,
    "lockedUserexportObjects": UserExport,
    "userimportSet": UserImport,
    "lockedUserimportObjects": UserImport,
}


class ProfileTransferReadTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="profile-transfer-owner", is_profile_public=True
        )
        self.stranger = User.objects.create_user(username="profile-transfer-stranger")
        self.reader = User.objects.create_user(username="profile-transfer-reader")
        self.group_reader = User.objects.create_user(username="profile-transfer-group")
        self.admin = User.objects.create_user(
            username="profile-transfer-admin", is_superuser=True
        )
        group = Group.objects.create(name="profile-transfer-readers")
        self.group_reader.groups.add(group)
        self.rows: dict[TransferModel, tuple[Transfer, Transfer]] = {}
        models: tuple[TransferModel, ...] = (UserExport, UserImport)
        for model in models:
            private = model.objects.create(
                name="Private transfer",
                creator=self.owner,
                user_lock=self.owner,
                is_public=False,
            )
            public = model.objects.create(
                name="Public transfer",
                creator=self.owner,
                user_lock=self.owner,
                is_public=True,
            )
            model.objects.create(
                name="Other profile",
                creator=self.stranger,
                user_lock=self.stranger,
                is_public=True,
            )
            set_permissions_for_obj_to_user(
                self.reader, private, [PermissionTypes.READ]
            )
            assign_perm(f"read_{model._meta.model_name}", group, private)
            self.rows[model] = (private, public)

    def query(self, field, actor):
        headers = {"Authorization": f"Bearer {get_token(actor)}"} if actor else {}
        response = self.client.post(
            "/graphql/",
            {
                "query": "query($slug: String!) { userBySlug(slug: $slug) { "
                + field
                + " { edges { node { id name } } } } }",
                "variables": {"slug": self.owner.slug},
            },
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_related_transfer_lists_keep_resource_read_and_parent_membership(self):
        for role, actor in (
            ("owner", self.owner),
            ("reader", self.reader),
            ("group", self.group_reader),
            ("stranger", self.stranger),
            ("superuser", self.admin),
            ("anonymous", None),
        ):
            for field, model in FIELDS.items():
                with self.subTest(role=role, field=field):
                    private, public = self.rows[model]
                    result = self.query(field, actor)
                    self.assertNotIn("errors", result)
                    nodes = result["data"]["userBySlug"][field]["edges"]
                    # Import list READ has no concrete Guardian permission tables;
                    # its existing manager admits only the creator or public rows.
                    private_visible = role == "owner" or (
                        model is UserExport and role in ("reader", "group")
                    )
                    expected = [public, private] if private_visible else [public]
                    self.assertEqual(
                        {node["node"]["id"] for node in nodes},
                        {
                            to_global_id(model.__name__ + "Type", row.pk)
                            for row in expected
                        },
                    )
