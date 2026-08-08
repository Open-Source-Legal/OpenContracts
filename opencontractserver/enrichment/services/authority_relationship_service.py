"""Idempotent canonical-key authority relationship reconciliation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from django.db import transaction

from opencontractserver.annotations.models import AuthorityRelationship
from opencontractserver.enrichment.authority_sources import SourceRelationship


class AuthorityRelationshipService:
    """Converge pack/provider edges while preserving hand-curated rows."""

    @classmethod
    @transaction.atomic
    def upsert_for_source(
        cls,
        *,
        source_key: str,
        relationships: Iterable[SourceRelationship],
        origin: str,
        baseline: bool = False,
        replace: bool = False,
    ) -> dict[str, int]:
        """Converge stable-key edges without deleting another owner's rows.

        Relationship identity is deliberately independent of Document rows.
        The same pack can be installed by more than one owner, so a single
        global source/target Document cache would be ambiguous. Consumers
        resolve visible current documents through DocumentPath at query time.

        When ``replace`` is true, the supplied relationships are authoritative
        for this exact ``(source_key, source, origin)`` ownership slice. Managed
        rows in that slice which are absent from the input are deleted; manual,
        baseline/provider rows of the other source class, and foreign origins
        remain untouched.
        """

        created = updated = unchanged = preserved_manual = preserved_baseline = 0
        skipped_foreign = deleted = 0
        desired_source = "baseline" if baseline else "provider"
        desired_identities: set[tuple[str, str]] = set()
        for relationship in relationships:
            desired_identities.add(
                (
                    str(relationship.relationship_type),
                    relationship.target_key,
                )
            )
            (
                row,
                was_created,
            ) = AuthorityRelationship.objects.select_for_update().get_or_create(
                source_key=source_key,
                relationship_type=str(relationship.relationship_type),
                target_key=relationship.target_key,
                defaults={
                    "source": desired_source,
                    "origin": origin,
                    "verified": relationship.verified,
                    "metadata": dict(relationship.metadata),
                },
            )
            if was_created:
                created += 1
                continue
            if row.source == "manual":
                preserved_manual += 1
                continue
            # Managed rows are owned by their first non-empty origin. A later
            # writer must not silently seize the same edge identity.
            if row.origin and row.origin != origin:
                skipped_foreign += 1
                continue
            # Pack declarations outrank runtime provider refreshes, including
            # when both use the same origin label. A provider may enrich its
            # own rows, but it cannot downgrade a baseline edge to provider
            # ownership.
            if row.source == "baseline" and not baseline:
                preserved_baseline += 1
                continue

            # The owning managed writer may revoke an erroneous verification;
            # only a row explicitly converted to ``source="manual"`` freezes
            # the curator's legal determination. Provider metadata owns only
            # its declared keys; curator overrides can live alongside it.
            merged_metadata = (
                dict(row.metadata) if isinstance(row.metadata, Mapping) else {}
            )
            curator_overrides = merged_metadata.get("curator_overrides", {})
            if not isinstance(curator_overrides, Mapping):
                curator_overrides = {}
            for key, value in relationship.metadata.items():
                if key not in curator_overrides:
                    merged_metadata[key] = value
            merged_metadata.update(curator_overrides)
            desired = {
                "source": desired_source,
                "origin": origin,
                "verified": relationship.verified,
                "metadata": merged_metadata,
            }
            changed = [
                field_name
                for field_name, value in desired.items()
                if getattr(row, field_name) != value
            ]
            if not changed:
                unchanged += 1
                continue
            for field_name in changed:
                setattr(row, field_name, desired[field_name])
            row.save(update_fields=[*changed, "modified"])
            updated += 1

        if replace:
            owned_rows = list(
                AuthorityRelationship.objects.select_for_update()
                .filter(
                    source_key=source_key,
                    source=desired_source,
                    origin=origin,
                )
                .values_list("pk", "relationship_type", "target_key")
            )
            stale_pks = [
                pk
                for pk, relationship_type, target_key in owned_rows
                if (relationship_type, target_key) not in desired_identities
            ]
            if stale_pks:
                _, deleted_by_model = AuthorityRelationship.objects.filter(
                    pk__in=stale_pks
                ).delete()
                deleted = deleted_by_model.get(
                    AuthorityRelationship._meta.label,
                    0,
                )

        return {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "preserved_manual": preserved_manual,
            "preserved_baseline": preserved_baseline,
            "skipped_foreign": skipped_foreign,
            "deleted": deleted,
        }

    @classmethod
    def load_declarations(
        cls, declarations: Iterable[Mapping[str, object]], *, origin: str
    ) -> dict[str, int]:
        """Converge one pack's validated relationship baseline.

        The declarations are authoritative only for baseline rows owned by
        ``origin``. Rows owned by curators, providers, or another pack remain
        untouched, while baseline edges removed from this pack are deleted.
        """

        totals = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "preserved_manual": 0,
            "preserved_baseline": 0,
            "skipped_foreign": 0,
            "deleted": 0,
        }
        grouped: dict[str, list[SourceRelationship]] = {}
        desired_identities: set[tuple[str, str, str]] = set()
        for declaration in declarations:
            source_key = str(declaration["source_key"])
            metadata = declaration.get("metadata", {})
            if not isinstance(metadata, Mapping):
                raise ValueError("relationship metadata must be a mapping")
            verified = declaration.get("verified", False)
            if not isinstance(verified, bool):
                raise ValueError(f"verified must be true or false; got {verified!r}")
            relationship = SourceRelationship(
                target_key=str(declaration["target_key"]),
                relationship_type=str(declaration["relationship_type"]),
                verified=verified,
                metadata=metadata,
            )
            grouped.setdefault(source_key, []).append(relationship)
            desired_identities.add(
                (
                    source_key,
                    str(relationship.relationship_type),
                    relationship.target_key,
                )
            )
        with transaction.atomic():
            for source_key, relationships in grouped.items():
                result = cls.upsert_for_source(
                    source_key=source_key,
                    relationships=relationships,
                    origin=origin,
                    baseline=True,
                )
                for key in result:
                    totals[key] += result[key]

            owned_rows = list(
                AuthorityRelationship.objects.select_for_update()
                .filter(source="baseline", origin=origin)
                .values_list(
                    "pk",
                    "source_key",
                    "relationship_type",
                    "target_key",
                )
            )
            stale_pks = [
                pk
                for pk, source_key, relationship_type, target_key in owned_rows
                if (source_key, relationship_type, target_key) not in desired_identities
            ]
            if stale_pks:
                _, deleted_by_model = AuthorityRelationship.objects.filter(
                    pk__in=stale_pks
                ).delete()
                totals["deleted"] += deleted_by_model.get(
                    AuthorityRelationship._meta.label,
                    0,
                )
        return totals
