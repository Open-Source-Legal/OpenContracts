"""Atomic admission and fenced accounting; uncertain charges never free budget."""

import hashlib
import logging
from decimal import Decimal
from functools import partial
from typing import cast

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from opencontractserver.annotations.models import Annotation, Note, Relationship
from opencontractserver.constants.ingestion_runs import (
    MAX_OPERATION_ATTEMPTS,
    REPORT_EVENT_LIMIT,
    REPORT_PAGE_SIZE,
)
from opencontractserver.documents.models import Document
from opencontractserver.utils.embedding_identity import valid_embeddings
from opencontractserver.utils.embeddings import synthesize_relationship_block_text
from opencontractserver.utils.files import read_field_file_text
from opencontractserver.worker_uploads.run_models import (
    IngestionOperation,
    IngestionReservation,
    IngestionRun,
    IngestionRunEvent,
)
from opencontractserver.worker_uploads.run_policy import (
    RunPolicyError,
    bounded_text,
    build_policy,
    digest,
    money,
    token_cost,
    validate_execution,
)

logger = logging.getLogger(__name__)
TARGETS = {
    "document": Document,
    "annotation": Annotation,
    "relationship": Relationship,
    "note": Note,
}


def event(run, code, **detail):
    IngestionRunEvent.objects.create(run=run, code=code, detail=detail)


def runs_for_token(token):
    return IngestionRun.objects.filter(
        worker_account_id=token.worker_account_id, corpus_id=token.corpus_id
    )


def create_run(
    token,
    *,
    ceiling_usd,
    preparations,
    embedding_mode="prepared",
    fallback="forbid",
    run_id=None,
):
    policy = build_policy(
        token.corpus,
        preparations=preparations,
        embedding_mode=embedding_mode,
        fallback=fallback,
    )
    ceiling = money(ceiling_usd)
    policy["initial_ceiling_usd"] = format(ceiling.normalize(), "f")
    with transaction.atomic():
        # Scope creation/replays to the stable worker identity, not a token key.
        from opencontractserver.worker_uploads.models import WorkerAccount

        WorkerAccount.objects.select_for_update().get(pk=token.worker_account_id)
        if run_id:
            previous = IngestionRun.objects.filter(pk=run_id).first()
            if previous:
                if (
                    previous.worker_account_id != token.worker_account_id
                    or previous.corpus_id != token.corpus_id
                    or previous.policy_digest != digest(policy)
                ):
                    raise RunPolicyError("run_identity_conflict")
                return previous
        kwargs = {"id": run_id} if run_id else {}
        try:
            with transaction.atomic():
                run = IngestionRun.objects.create(
                    worker_account=token.worker_account,
                    corpus=token.corpus,
                    policy=policy,
                    policy_digest=digest(policy),
                    ceiling_usd=ceiling,
                    **kwargs,
                )
        except IntegrityError:
            raise RunPolicyError("run_identity_conflict") from None
        event(run, "created", ceiling_usd=str(ceiling))
        return run


def target_text(obj):
    if isinstance(obj, Document):
        return (
            read_field_file_text(obj.txt_extract_file) if obj.txt_extract_file else ""
        )
    if isinstance(obj, Annotation):
        return obj.raw_text or ""
    if isinstance(obj, Note):
        return obj.content or ""
    return synthesize_relationship_block_text(obj)


def target_runs(obj):
    if isinstance(obj, Document):
        return {obj.ingestion_run_id} if obj.ingestion_run_id else set()
    doc_id = getattr(obj, "document_id", None)
    struct_id = getattr(obj, "structural_set_id", None)
    docs = Document.objects.none()
    if doc_id:
        document = obj.document
        return {document.ingestion_run_id} if document.ingestion_run_id else set()
    elif struct_id:
        docs = Document.objects.filter(structural_annotation_set_id=struct_id)
    return set(
        docs.exclude(ingestion_run_id=None).values_list("ingestion_run_id", flat=True)
    )


def validate_target(run, operation, obj):
    if (
        target_runs(obj) != {run.pk}
        or hashlib.sha256(bounded_text(target_text(obj)).encode()).hexdigest()
        != operation.input_digest
    ):
        raise RunPolicyError("operation_input_changed")
    if isinstance(obj, Annotation) and set(obj.content_modalities or ["TEXT"]) - {
        "TEXT"
    }:
        raise RunPolicyError("prohibited_multimodal_fallback")


def lock_target(operation):
    obj = cast(
        Document | Annotation | Relationship | Note,
        TARGETS[operation.target_type]
        .objects.select_for_update()
        .get(pk=operation.target_id),
    )
    if isinstance(obj, Relationship):
        # The relationship row's FOR UPDATE lock blocks FK checks for new M2M
        # endpoints. Lock existing through rows against deletion and endpoint
        # annotations against text edits until publication commits.
        endpoint_ids: set[int] = set()
        for manager in (obj.source_annotations, obj.target_annotations):
            endpoint_ids.update(
                manager.through.objects.select_for_update()
                .filter(relationship_id=obj.pk)
                .order_by("pk")
                .values_list("annotation_id", flat=True)
            )
        list(
            Annotation.objects.select_for_update()
            .filter(pk__in=endpoint_ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
    return obj


def suppress_stage(doc_id, stage):
    """Execution backstop for stages with no bounded run adapter."""
    run_id = (
        Document.objects.filter(pk=doc_id)
        .values_list("ingestion_run_id", flat=True)
        .first()
    )
    if not run_id:
        return False
    # Fixed codes only: exception messages/provider settings may contain secrets.
    IngestionRunEvent.objects.get_or_create(
        run_id=run_id, code=f"suppressed_{stage}", detail={"document_id": int(doc_id)}
    )
    return True


def route_embedding(obj, corpus_id=None):
    """Return whether the run owns this work, not whether a vector was stored.

    This includes queued, suppressed and violated work: none may fall through to
    legacy providers. Run status and readiness report the actual outcome.
    """
    if not isinstance(obj, (Document, Annotation, Relationship, Note)):
        return False
    run_ids = target_runs(obj)
    if not run_ids:
        return False
    for run in IngestionRun.objects.filter(pk__in=run_ids):
        if len(run_ids) != 1:
            policy_violation(run.pk, "ambiguous_run_context")
            continue
        if corpus_id is not None and int(corpus_id) != run.corpus_id:
            # Copies retain their binding. A destination corpus cannot select
            # another provider or pause the source run's approved work.
            IngestionRunEvent.objects.get_or_create(
                run=run,
                code="suppressed_corpus_embedding",
                detail={"corpus_id": int(corpus_id)},
            )
            continue
        if run.policy["embedding_mode"] == "prepared":
            continue
        if (
            valid_embeddings(
                run.policy["provider"]["path"],
                run.policy["provider"]["dimension"],
                run.policy["provider"]["configuration"],
            )
            .filter(**obj.get_embedding_reference_kwargs())
            .exists()
        ):
            continue
        if isinstance(obj, Annotation) and set(obj.content_modalities or ["TEXT"]) - {
            "TEXT"
        }:
            policy_violation(run.pk, "prohibited_multimodal_fallback")
            continue
        text = bounded_text(target_text(obj))
        if not text.strip():
            continue
        target_type = next(
            name for name, cls in TARGETS.items() if isinstance(obj, cls)
        )
        input_digest = hashlib.sha256(text.encode()).hexdigest()
        key = digest([target_type, obj.pk, input_digest, run.policy_digest])
        with transaction.atomic():
            run = IngestionRun.objects.select_for_update().get(pk=run.pk)
            operation, _ = IngestionOperation.objects.get_or_create(
                run=run,
                key=key,
                defaults={
                    "target_type": target_type,
                    "target_id": obj.pk,
                    "input_digest": input_digest,
                    "estimated_usd": token_cost(run.policy, len(text.encode())),
                },
            )
            _admit_locked(run, operation)
    return True


def route_embedding_batch(model, ids, corpus_id, result):
    bound = (
        model.objects.filter(pk__in=ids)
        .filter(
            Q(document__ingestion_run__isnull=False)
            | Q(structural_set__documents__ingestion_run__isnull=False)
        )
        .select_related("document")
        .distinct()
    )
    routed = set()
    for obj in bound:
        if route_embedding(obj, corpus_id):
            routed.add(obj.pk)
    if routed:
        result["policy_routed"] = len(routed)
    return [pk for pk in ids if pk not in routed]


def queue_document_operations(doc_id):
    doc = Document.objects.get(pk=doc_id)
    route_embedding(doc)
    query = Q(document_id=doc.pk)
    if doc.structural_annotation_set_id:
        query |= Q(structural_set_id=doc.structural_annotation_set_id)
    for model in (Annotation, Relationship):
        for obj in model.objects.filter(query).iterator():
            route_embedding(obj)


def policy_violation(run_id, code):
    with transaction.atomic():
        run = IngestionRun.objects.select_for_update().get(pk=run_id)
        _violate_locked(run, code)


def _violate_locked(run, code):
    if run.status != IngestionRun.Status.CANCELLED:
        run.status = IngestionRun.Status.POLICY_VIOLATION
    run.last_error = code
    run.save(update_fields=["status", "last_error"])
    event(run, code)


def _nudge(reservation_id):
    from opencontractserver.worker_uploads.run_tasks import process_ingestion_operation

    try:
        process_ingestion_operation.delay(str(reservation_id))
    except Exception:
        logger.warning("Ingestion reservation awaits periodic drain")


def _admit_locked(run, operation):
    if (
        operation.status != IngestionOperation.Status.WAITING
        or run.status != IngestionRun.Status.ACTIVE
    ):
        return
    try:
        validate_execution(run)
    except RunPolicyError as exc:
        operation.error_code = str(exc)
        operation.save(update_fields=["error_code"])
        _violate_locked(run, str(exc))
        return
    if operation.attempt_count >= MAX_OPERATION_ATTEMPTS:
        operation.error_code = "retry_exhausted"
        operation.save(update_fields=["error_code"])
        return
    if run.accounted_usd + run.reserved_usd + operation.estimated_usd > run.ceiling_usd:
        run.status = IngestionRun.Status.BUDGET_EXHAUSTED
        run.last_error = "budget_exhausted"
        run.save(update_fields=["status", "last_error"])
        operation.error_code = "budget_exhausted"
        operation.save(update_fields=["error_code"])
        event(run, "budget_exhausted")
        return
    operation.attempt_count += 1
    reservation = IngestionReservation.objects.create(
        operation=operation,
        attempt=operation.attempt_count,
        amount_usd=operation.estimated_usd,
    )
    run.reserved_usd += reservation.amount_usd
    run.save(update_fields=["reserved_usd"])
    operation.status = IngestionOperation.Status.QUEUED
    operation.error_code = ""
    operation.save(update_fields=["attempt_count", "status", "error_code"])
    transaction.on_commit(lambda: _nudge(reservation.pk))


def execute_reservation(reservation_id):
    """A persisted STARTED claim precedes the only possible provider request.

    A crash/redelivery cannot repeat it. An explicit retry needs another full
    reservation while the uncertain original remains charged to the allowance.
    """
    reference = IngestionReservation.objects.select_related("operation").get(
        pk=reservation_id
    )
    with transaction.atomic():
        run = IngestionRun.objects.select_for_update().get(
            pk=reference.operation.run_id
        )
        reservation = IngestionReservation.objects.select_for_update().get(
            pk=reservation_id
        )
        operation = IngestionOperation.objects.get(pk=reservation.operation_id)
        if (
            reservation.status != IngestionReservation.Status.RESERVED
            or run.status
            not in (IngestionRun.Status.ACTIVE, IngestionRun.Status.BUDGET_EXHAUSTED)
        ):
            return
        try:
            provider = validate_execution(run)
            obj = cast(
                Document | Annotation | Relationship | Note,
                TARGETS[operation.target_type].objects.get(pk=operation.target_id),
            )
            text = bounded_text(target_text(obj))
            validate_target(run, operation, obj)
        except (
            RunPolicyError,
            Document.DoesNotExist,
            Annotation.DoesNotExist,
            Note.DoesNotExist,
            Relationship.DoesNotExist,
        ) as exc:
            code = (
                str(exc)
                if isinstance(exc, RunPolicyError)
                else "operation_target_missing"
            )
            _violate_locked(run, code)
            return
        reservation.status = IngestionReservation.Status.STARTED
        reservation.started = timezone.now()
        reservation.save(update_fields=["status", "started"])
        operation.status = IngestionOperation.Status.RUNNING
        operation.save(update_fields=["status"])

    try:
        vector, tokens = provider.embed_text_accounted(text)
        if type(tokens) is not int or not 0 <= tokens <= len(text.encode()):
            raise RunPolicyError("invalid_usage_receipt")
        actual = token_cost(run.policy, tokens)
        with transaction.atomic():
            run = IngestionRun.objects.select_for_update().get(pk=run.pk)
            reservation = IngestionReservation.objects.select_for_update().get(
                pk=reservation_id
            )
            operation = IngestionOperation.objects.get(pk=operation.pk)
            if reservation.status == IngestionReservation.Status.SETTLED:
                return
            if actual > reservation.amount_usd:
                raise RunPolicyError("usage_exceeds_reservation")
            # Late attempts account their real usage, but cannot overwrite a
            # newer attempt's output or resurrect a cancelled operation/run.
            if (
                operation.attempt_count == reservation.attempt
                and operation.status != IngestionOperation.Status.CANCELLED
                and run.status != IngestionRun.Status.CANCELLED
            ):
                try:
                    # Output is optional; the known usage receipt must settle
                    # even if validation or storage fails. A savepoint isolates
                    # storage errors from the accounting transaction.
                    with transaction.atomic():
                        obj = lock_target(operation)
                        validate_target(run, operation, obj)
                        if len(vector) != run.policy["provider"][
                            "dimension"
                        ] or not obj.add_embedding(
                            run.policy["provider"]["path"],
                            vector,
                            configuration=run.policy["provider"]["configuration"],
                        ):
                            raise RunPolicyError("invalid_embedding_result")
                    operation.status = IngestionOperation.Status.COMPLETED
                    operation.error_code = ""
                except Exception as exc:
                    if isinstance(exc, RunPolicyError):
                        code = str(exc)
                    elif isinstance(exc, ObjectDoesNotExist):
                        code = "operation_target_missing"
                    else:
                        code = "embedding_publication_failed"
                    operation.status = IngestionOperation.Status.FAILED
                    operation.error_code = code
                    if code in (
                        "operation_input_changed",
                        "prohibited_multimodal_fallback",
                    ):
                        _violate_locked(run, code)
                    else:
                        run.status = IngestionRun.Status.PAUSED
                        run.last_error = code
                        run.save(update_fields=["status", "last_error"])
                        event(run, code, operation_id=str(operation.pk))
                operation.save(update_fields=["status", "error_code"])
            reservation.status = IngestionReservation.Status.SETTLED
            reservation.accounted_usd = actual
            reservation.accounted_tokens = tokens
            reservation.save(
                update_fields=["status", "accounted_usd", "accounted_tokens"]
            )
            run.reserved_usd -= reservation.amount_usd
            run.accounted_usd += actual
            run.save(update_fields=["reserved_usd", "accounted_usd"])
    except Exception as exc:
        # Never log a provider exception: SDK errors can contain credentials,
        # endpoints or source content. The outstanding bound remains reserved.
        code = (
            str(exc) if isinstance(exc, RunPolicyError) else "provider_outcome_unknown"
        )
        with transaction.atomic():
            run = IngestionRun.objects.select_for_update().get(pk=run.pk)
            reservation = IngestionReservation.objects.select_for_update().get(
                pk=reservation_id
            )
            if reservation.status == IngestionReservation.Status.SETTLED:
                return
            reservation.status = IngestionReservation.Status.UNCERTAIN
            reservation.save(update_fields=["status"])
            operation = IngestionOperation.objects.get(pk=operation.pk)
            if (
                operation.attempt_count == reservation.attempt
                and operation.status != IngestionOperation.Status.CANCELLED
            ):
                operation.status = IngestionOperation.Status.UNCERTAIN
                operation.error_code = code
                operation.save(update_fields=["status", "error_code"])
            if run.status != IngestionRun.Status.CANCELLED:
                run.status = IngestionRun.Status.PAUSED
                run.last_error = code
                run.save(update_fields=["status", "last_error"])
            event(run, code, reservation_id=str(reservation.pk))


def _cancel_locked(run, operation):
    unused = operation.reservations.filter(status=IngestionReservation.Status.RESERVED)
    release = unused.aggregate(amount=Sum("amount_usd"))["amount"] or Decimal(0)
    unused.update(status=IngestionReservation.Status.CANCELLED)
    run.reserved_usd -= release
    run.save(update_fields=["reserved_usd"])
    operation.status = IngestionOperation.Status.CANCELLED
    operation.save(update_fields=["status"])


def control_run(run_id, action, *, ceiling_usd=None, operation_id=None):
    with transaction.atomic():
        run = IngestionRun.objects.select_for_update().get(pk=run_id)
        if run.status == IngestionRun.Status.CANCELLED:
            raise RunPolicyError("run_cancelled")
        if action == "pause":
            run.status = IngestionRun.Status.PAUSED
        elif action == "cancel":
            run.status = IngestionRun.Status.CANCELLED
            for operation in run.operations.exclude(
                status=IngestionOperation.Status.COMPLETED
            ):
                _cancel_locked(run, operation)
        elif action == "resume":
            validate_execution(run)
            if ceiling_usd is not None:
                ceiling = money(ceiling_usd)
                if ceiling < run.ceiling_usd:
                    raise RunPolicyError("ceiling_cannot_decrease")
                event(
                    run,
                    "ceiling_increased",
                    previous=str(run.ceiling_usd),
                    current=str(ceiling),
                )
                run.ceiling_usd = ceiling
            run.status = IngestionRun.Status.ACTIVE
            run.last_error = ""
        elif action in ("retry_operation", "cancel_operation"):
            operation = run.operations.get(pk=operation_id)
            if action == "cancel_operation":
                _cancel_locked(run, operation)
            else:
                if operation.status not in (
                    IngestionOperation.Status.UNCERTAIN,
                    IngestionOperation.Status.RUNNING,
                    IngestionOperation.Status.FAILED,
                ):
                    raise RunPolicyError("operation_not_retryable")
                if operation.attempt_count >= MAX_OPERATION_ATTEMPTS:
                    raise RunPolicyError("retry_exhausted")
                # Never release a started attempt, even when the caller believes
                # its worker crashed. Late completion is separately fenced.
                operation.reservations.filter(
                    status=IngestionReservation.Status.STARTED
                ).update(status=IngestionReservation.Status.UNCERTAIN)
                operation.status = IngestionOperation.Status.WAITING
                operation.save(update_fields=["status"])
        else:
            raise RunPolicyError("invalid_run_action")
        run.save(update_fields=["status", "last_error", "ceiling_usd"])
        event(run, action, operation_id=str(operation_id) if operation_id else None)
        if run.status == IngestionRun.Status.ACTIVE:
            for operation in run.operations.filter(
                status=IngestionOperation.Status.WAITING
            ).order_by("created"):
                _admit_locked(run, operation)
            for reservation_id in IngestionReservation.objects.filter(
                operation__run=run, status=IngestionReservation.Status.RESERVED
            ).values_list("pk", flat=True):
                transaction.on_commit(partial(_nudge, reservation_id))
        return run


@transaction.atomic
def run_report(run, *, offset=0):
    # Every monetary mutation holds this same lock; totals and detail therefore
    # describe one committed state, even while provider requests finish.
    run = IngestionRun.objects.select_for_update().get(pk=run.pk)
    operation_count = run.operations.count()
    operations = list(
        run.operations.order_by("created", "pk")[offset : offset + REPORT_PAGE_SIZE]
    )
    reservations = IngestionReservation.objects.filter(operation__run=run)
    uncertain = reservations.filter(
        status__in=[
            IngestionReservation.Status.STARTED,
            IngestionReservation.Status.UNCERTAIN,
        ]
    ).aggregate(amount=Sum("amount_usd"))["amount"] or Decimal(0)
    waiting = run.operations.filter(status=IngestionOperation.Status.WAITING).aggregate(
        amount=Sum("estimated_usd")
    )["amount"] or Decimal(0)

    def rows(query):
        return [
            {
                k: (
                    str(v)
                    if v is not None
                    and (k.endswith("_usd") or k in ("id", "operation_id"))
                    else v
                )
                for k, v in row.items()
            }
            for row in query
        ]

    return {
        "id": str(run.pk),
        "status": run.status,
        "policy": run.policy,
        "policy_digest": run.policy_digest,
        "last_error": run.last_error,
        "ceiling_usd": str(run.ceiling_usd),
        "accounted_usd": str(run.accounted_usd),
        "reserved_usd": str(run.reserved_usd),
        "remaining_usd": str(run.ceiling_usd - run.accounted_usd - run.reserved_usd),
        "in_flight_or_uncertain_usd": str(uncertain),
        "waiting_estimate_usd": str(waiting),
        "operation_count": operation_count,
        "offset": offset,
        "next_offset": (
            offset + REPORT_PAGE_SIZE
            if offset + REPORT_PAGE_SIZE < operation_count
            else None
        ),
        "operations": rows(
            run.operations.filter(pk__in=[op.pk for op in operations])
            .order_by("created", "pk")
            .values(
                "id",
                "target_type",
                "target_id",
                "status",
                "estimated_usd",
                "attempt_count",
                "error_code",
            )
        ),
        "reservations": rows(
            reservations.filter(operation__in=operations)
            .order_by("created", "pk")
            .values(
                "id",
                "operation_id",
                "attempt",
                "status",
                "amount_usd",
                "accounted_usd",
                "accounted_tokens",
            )
        ),
        "events": list(
            run.events.order_by("-created").values("code", "detail", "created")[
                :REPORT_EVENT_LIMIT
            ]
        ),
    }
