"""Worker/corpus-scoped run policy and accounting endpoints."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from opencontractserver.worker_uploads.auth import WorkerTokenAuthentication
from opencontractserver.worker_uploads.run_models import IngestionOperation
from opencontractserver.worker_uploads.run_policy import RunPolicyError
from opencontractserver.worker_uploads.run_services import (
    control_run,
    create_run,
    run_report,
    runs_for_token,
)
from opencontractserver.worker_uploads.views import IsValidWorkerToken


class RunCreateSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    ceiling_usd = serializers.CharField()
    preparations = serializers.JSONField()
    embedding_mode = serializers.ChoiceField(
        choices=["prepared", "server"], default="prepared"
    )
    fallback = serializers.ChoiceField(choices=["forbid"], default="forbid")


class RunControlSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["pause", "resume", "cancel", "retry_operation", "cancel_operation"]
    )
    ceiling_usd = serializers.CharField(required=False)
    operation_id = serializers.UUIDField(required=False)


class RunReportSerializer(serializers.Serializer):
    offset = serializers.IntegerField(min_value=0, default=0)


class IngestionRunCreateView(APIView):
    authentication_classes = [WorkerTokenAuthentication]
    permission_classes = [IsValidWorkerToken]

    def post(self, request):
        serializer = RunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data["run_id"] = data.pop("id", None)
        try:
            run = create_run(request.auth, **data)
        except RunPolicyError as exc:
            return Response(
                {"error": str(exc)},
                status=409 if str(exc) == "run_identity_conflict" else 400,
            )
        return Response(run_report(run), status=status.HTTP_201_CREATED)


class IngestionRunView(APIView):
    authentication_classes = [WorkerTokenAuthentication]
    permission_classes = [IsValidWorkerToken]

    def get(self, request, run_id):
        run = get_object_or_404(runs_for_token(request.auth), pk=run_id)
        query = RunReportSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(run_report(run, **query.validated_data))

    def post(self, request, run_id):
        run = get_object_or_404(runs_for_token(request.auth), pk=run_id)
        serializer = RunControlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["action"].endswith("_operation"):
            get_object_or_404(IngestionOperation, run=run, pk=data.get("operation_id"))
        try:
            run = control_run(run.pk, **data)
        except RunPolicyError as exc:
            return Response({"error": str(exc)}, status=409)
        return Response(run_report(run))
