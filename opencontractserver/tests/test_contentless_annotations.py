"""Contentless structural annotations: parse-time filter and cleanup command."""

from io import StringIO
from typing import cast

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.parsers.warp_ingest_parser import WarpIngestParser
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.utils.contentless_annotations import (
    contentless_structural_filter,
    has_word_characters,
    is_contentless,
)

User = get_user_model()

# chr() keeps these invisible characters visible in source.
NBSP = chr(0x00A0)
EN_SPACE = chr(0x2002)
PUA_BULLET = chr(0xF0A8)


def _annot(id, text, parent_id=None, label="Paragraph", modalities=("TEXT",)):
    return {
        "id": id,
        "annotationLabel": label,
        "rawText": text,
        "page": 0,
        "annotation_json": {},
        "parent_id": parent_id,
        "annotation_type": "TOKEN_LABEL",
        "structural": True,
        "content_modalities": list(modalities),
    }


def _rel(id, sources, targets):
    return {
        "id": id,
        "relationshipLabel": "refersTo",
        "source_annotation_ids": sources,
        "target_annotation_ids": targets,
        "structural": True,
    }


def _ids(items):
    return [item["id"] for item in items]


class ContentlessRuleTests(SimpleTestCase):
    def test_word_characters_in_any_script_count_as_content(self):
        for text in ("a", "7", "第", "Ж", "§ 1", " x "):
            self.assertTrue(has_word_characters(text), text)
        for blank in (None, "", NBSP * 3, PUA_BULLET, "•", "____", "。", ")"):
            self.assertFalse(has_word_characters(blank), repr(blank))

    def test_images_and_content_regions_are_never_contentless(self):
        self.assertTrue(is_contentless(EN_SPACE * 5, "PARAGRAPH", []))
        self.assertFalse(is_contentless("", "SECTION", ["IMAGE"]))
        for label in ("picture", "TABLE", "Formula", "checkbox_unselected"):
            self.assertFalse(is_contentless("", label, []), label)


class ContentlessFilterTests(SimpleTestCase):
    def test_nothing_dropped_returns_input_unchanged(self):
        annotations = [_annot("a", "Title"), _annot("b", "Body", "a")]
        relationships = [_rel("r", ["a"], ["b"])]
        kept, kept_rels, dropped = contentless_structural_filter(
            annotations, relationships
        )
        self.assertEqual((kept, kept_rels, dropped), (annotations, relationships, 0))

    def test_only_leaves_are_dropped_until_stable(self):
        annotations = [
            _annot("root", "Section 1"),
            _annot("noise_leaf", NBSP, "root"),
            # A container whose children are all noise goes too ...
            _annot("noise_box", "", "root", label="SECTION"),
            _annot("noise_box_child", "____", "noise_box"),
            # ... but one holding content is structure and stays.
            _annot("bullet", PUA_BULLET, "root"),
            _annot("item", "Item text", "bullet"),
        ]
        kept, _, dropped = contentless_structural_filter(annotations, [])
        self.assertEqual(dropped, 3)
        self.assertEqual(_ids(kept), ["root", "bullet", "item"])
        self.assertEqual(kept[2]["parent_id"], "bullet")

    def test_non_structural_and_region_annotations_are_kept(self):
        annotations = [
            {**_annot("user", NBSP), "structural": False},
            _annot("table", "\n\n", label="TABLE"),
            _annot("figure", "", label="SECTION", modalities=("IMAGE",)),
        ]
        _, _, dropped = contentless_structural_filter(annotations, [])
        self.assertEqual(dropped, 0)

    def test_mixed_int_and_str_ids_match(self):
        annotations = [_annot(1, "Title"), _annot(2, NBSP, 1), _annot(3, "x", "1")]
        kept, kept_rels, _ = contentless_structural_filter(
            annotations, [_rel("r", [1], ["2"])]
        )
        self.assertEqual(_ids(kept), [1, 3])
        self.assertEqual(kept_rels, [])

    def test_annotations_without_ids_do_not_collide(self):
        annotations = [_annot(None, NBSP), _annot(None, "Body")]
        kept, _, dropped = contentless_structural_filter(annotations, [])
        self.assertEqual((dropped, [a["rawText"] for a in kept]), (1, ["Body"]))

    def test_cyclic_parents_terminate_and_are_kept(self):
        annotations = [_annot("a", NBSP, "b"), _annot("b", NBSP, "a")]
        kept, _, dropped = contentless_structural_filter(annotations, [])
        self.assertEqual((dropped, _ids(kept)), (0, ["a", "b"]))

    def test_relationships_lose_dropped_endpoints_and_empty_ones_go(self):
        annotations = [_annot("a", "A"), _annot("b", "B"), _annot("n", NBSP)]
        relationships = [
            _rel("trimmed", ["a"], ["b", "n"]),
            _rel("emptied", ["n"], ["a"]),
            _rel("untouched", ["a"], ["b"]),
        ]
        _, kept_rels, _ = contentless_structural_filter(annotations, relationships)
        self.assertEqual(_ids(kept_rels), ["trimmed", "untouched"])
        self.assertEqual(kept_rels[0]["target_annotation_ids"], ["b"])
        self.assertEqual(relationships[0]["target_annotation_ids"], ["b", "n"])


class SaveParsedDataDropsContentlessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="noise", password="pw12345678")
        self.doc = Document.objects.create(
            title="Noise Doc", file_type="pdf", creator=self.user
        )
        self.doc.pdf_file.save("n.pdf", ContentFile(b"%PDF-1.7\n%%EOF\n"))

    def test_contentless_structural_annotations_are_not_created(self):
        export = {
            "title": "Noise Doc",
            "content": "Title\nBody",
            "description": None,
            "pawls_file_content": [],
            "page_count": 1,
            "doc_labels": [],
            "labelled_text": [
                _annot("a1", "Title"),
                _annot("a2", PUA_BULLET, "a1", label="Bullet"),
                _annot("a3", "Body", "a1"),
            ],
            "relationships": [_rel("r1", ["a2"], ["a3"])],
        }
        WarpIngestParser().save_parsed_data(
            user_id=self.user.id,
            doc_id=self.doc.id,
            open_contracts_data=cast(OpenContractDocExport, export),
        )
        self.assertEqual(
            sorted(Annotation.objects.values_list("raw_text", flat=True)),
            ["Body", "Title"],
        )
        body = Annotation.objects.get(raw_text="Body")
        self.assertEqual(body.parent.raw_text, "Title")
        self.assertFalse(
            Relationship.objects.filter(relationship_label__text="refersTo").exists()
        )
        # No label is created only for dropped annotations.
        self.assertFalse(AnnotationLabel.objects.filter(text="Bullet").exists())


class PruneCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="prune", password="pw12345678")
        self.doc = Document.objects.create(title="d", creator=self.user)
        self.labels = {}
        self.rel_label = AnnotationLabel.objects.create(
            text="refersTo", label_type="RELATIONSHIP_LABEL", creator=self.user
        )

    def make(self, text, parent=None, label="Paragraph", structural=True, **extra):
        if label not in self.labels:
            self.labels[label] = AnnotationLabel.objects.create(
                text=label, label_type="TOKEN_LABEL", creator=self.user
            )
        return Annotation.objects.create(
            document=self.doc,
            creator=self.user,
            annotation_label=self.labels[label],
            raw_text=text,
            parent=parent,
            structural=structural,
            content_modalities=extra.get("modalities", ["TEXT"]),
        )

    def relate(self, sources, targets):
        rel = Relationship.objects.create(
            document=self.doc,
            creator=self.user,
            relationship_label=self.rel_label,
            structural=True,
        )
        rel.source_annotations.set(sources)
        rel.target_annotations.set(targets)
        return rel

    def run_command(self, *args):
        out = StringIO()
        call_command("prune_contentless_structural_annotations", *args, stdout=out)
        return out.getvalue()

    def test_prunes_noise_leaves_and_keeps_structure_and_regions(self):
        root = self.make("Section 1")
        noise_leaf = self.make(EN_SPACE * 4, parent=root)
        noise_box = self.make("", parent=root, label="SECTION")
        self.make("____", parent=noise_box)
        bullet = self.make(PUA_BULLET, parent=root)
        item = self.make("Item text", parent=bullet)
        kept = {
            root,
            bullet,
            item,
            self.make("第一条"),
            self.make("", label="picture", modalities=["IMAGE"]),
            self.make("\n\n", label="TABLE"),
            self.make("□", label="checkbox_unselected"),
            self.make(NBSP, structural=False),
        }
        emptied = self.relate([noise_leaf], [item])
        trimmed = self.relate([root], [item, noise_leaf])

        dry_run = self.run_command("--dry-run")
        self.assertIn("would delete 3", dry_run)
        self.assertIn("2  Paragraph ['TEXT']", dry_run)
        self.assertIn("1  SECTION ['TEXT']", dry_run)
        self.assertEqual(Annotation.objects.count(), len(kept) + 3)

        self.run_command()
        self.assertEqual(
            set(Annotation.objects.values_list("pk", flat=True)),
            {a.pk for a in kept},
        )
        item.refresh_from_db()
        self.assertEqual(item.parent_id, bullet.pk)
        self.assertFalse(Relationship.objects.filter(pk=emptied.pk).exists())
        self.assertEqual(list(trimmed.target_annotations.all()), [item])

        self.assertIn("No contentless", self.run_command())
