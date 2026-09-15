"""Durable versions and the atomically activated authority-pack version."""

from django.conf import settings
from django.db import models


class AuthorityPackArtifact(models.Model):
    pack_id = models.CharField(max_length=64, db_index=True)
    fingerprint = models.CharField(max_length=71)
    digest = models.CharField(max_length=64)
    version = models.CharField(max_length=128)
    directory_name = models.CharField(max_length=128)
    archive = models.FileField(upload_to="authority_pack_artifacts/%Y/%m/")
    contains_code = models.BooleanField(default=False)
    declarations = models.JSONField(default=list)
    charters = models.JSONField(default=dict)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)


class AuthorityPackActivation(models.Model):
    pack_id = models.CharField(max_length=64, unique=True)
    active_artifact = models.ForeignKey(
        AuthorityPackArtifact, null=True, on_delete=models.PROTECT
    )
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    corpus_ids = models.JSONField(default=list)
    last_error = models.TextField(blank=True, default="")
    attempted_fingerprint = models.CharField(max_length=71, blank=True, default="")
    modified = models.DateTimeField(auto_now=True)
