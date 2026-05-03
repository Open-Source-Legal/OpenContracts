"""Management command to populate content_modalities field for existing annotations."""

import logging

from django.core.management.base import BaseCommand

from opencontractserver.annotations.compact_json import iter_page_annotations
from opencontractserver.annotations.models import Annotation
from opencontractserver.utils.pawls_io import TokenView, load_canonical_v2

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Populate content_modalities field for existing annotations by analyzing their tokens"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update even annotations that already have content_modalities set",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]

        if force:
            annotations = Annotation.objects.all()
            self.stdout.write(f"Processing ALL {annotations.count()} annotations...")
        else:
            annotations = Annotation.objects.filter(content_modalities=[])
            self.stdout.write(
                f"Processing {annotations.count()} annotations with empty content_modalities..."
            )

        updated_count = 0
        error_count = 0

        for annotation in annotations.iterator(chunk_size=100):
            try:
                modalities = self._determine_modalities(annotation)

                if modalities and modalities != annotation.content_modalities:
                    if dry_run:
                        self.stdout.write(
                            f"Would update annotation {annotation.id}: {modalities}"
                        )
                    else:
                        annotation.content_modalities = modalities
                        annotation.save(update_fields=["content_modalities"])
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Updated annotation {annotation.id}: {modalities}"
                            )
                        )
                    updated_count += 1

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Error processing annotation {annotation.id}: {e}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nComplete! Updated: {updated_count}, Errors: {error_count}"
            )
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes made"))

    def _determine_modalities(self, annotation):
        """
        Determine content modalities by examining annotation's tokens.

        Returns list of modalities: ["TEXT"], ["IMAGE"], or ["IMAGE", "TEXT"]
        """
        # If annotation has no document, we can't check tokens
        # Use the annotation label as a hint
        if not annotation.document or not annotation.document.pawls_parse_file:
            # Fallback: Use label text as hint
            label_text = annotation.annotation_label.text.lower()
            if any(
                keyword in label_text
                for keyword in ["image", "figure", "chart", "graph", "photo", "picture"]
            ):
                return ["IMAGE"]
            else:
                return ["TEXT"]

        # Get PAWLs data as canonical v2
        try:
            pawls_data = load_canonical_v2(annotation.document.pawls_parse_file)
        except Exception:
            # Can't read PAWLS data, use label as fallback
            label_text = annotation.annotation_label.text.lower()
            if any(
                keyword in label_text
                for keyword in ["image", "figure", "chart", "graph", "photo", "picture"]
            ):
                return ["IMAGE"]
            return ["TEXT"]

        pages = pawls_data.get("p") or []

        # Extract token references from the json field (handles v1 and v2 formats)
        all_token_refs = []
        for page in iter_page_annotations(
            annotation.json or {}, raw_text=annotation.raw_text or ""
        ):
            all_token_refs.extend(
                {"pageIndex": page.page_index, "tokenIndex": idx}
                for idx in page.token_indices
            )

        if not all_token_refs:
            # No tokens referenced, use label as hint
            label_text = annotation.annotation_label.text.lower()
            if any(
                keyword in label_text
                for keyword in ["image", "figure", "chart", "graph", "photo", "picture"]
            ):
                return ["IMAGE"]
            return ["TEXT"]

        # Analyze tokens
        has_text = False
        has_image = False

        for token_ref in all_token_refs:
            page_idx = token_ref.get("pageIndex", 0)
            token_idx = token_ref.get("tokenIndex")

            if token_idx is None:
                continue

            if page_idx >= len(pages):
                continue

            page_dict = pages[page_idx]
            if not isinstance(page_dict, dict):
                continue

            rows = page_dict.get("t") or []
            if token_idx >= len(rows):
                continue

            row = rows[token_idx]
            if not isinstance(row, list):
                continue

            token = TokenView(row)

            # Check if this token is an image
            if token.is_image:
                has_image = True
            else:
                # Text token (has non-empty text content)
                if token.text.strip():
                    has_text = True

        # Return appropriate modalities
        if has_image and has_text:
            return ["IMAGE", "TEXT"]
        elif has_image:
            return ["IMAGE"]
        elif has_text:
            return ["TEXT"]
        else:
            # Empty annotation, default to TEXT
            return ["TEXT"]
