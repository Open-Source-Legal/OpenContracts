from django.contrib import admin

from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.shared.admin import GuardedModelAdmin


@admin.register(Fieldset)
class FieldsetAdmin(GuardedModelAdmin):
    list_display = ["id", "name", "description"]


@admin.register(Column)
class ColumnAdmin(GuardedModelAdmin):
    list_display = ["id", "query", "match_text", "output_type"]


@admin.register(Extract)
class ExtractAdmin(GuardedModelAdmin):
    list_display = ["id", "name"]


@admin.register(Datacell)
class DatacellAdmin(GuardedModelAdmin):
    list_display = ["id", "extract", "column"]
