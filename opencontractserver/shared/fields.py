import json
import logging
from typing import Any, Optional

from django.db.models import JSONField as DbJSONField
from django.forms.fields import InvalidJSONInput, JSONField
from drf_extra_fields.fields import Base64FileField
from filetype import filetype

# Logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# Field to accept base64-encoded file strings for PDF only as a field on our serializers
class PDFBase64File(Base64FileField):

    ALLOWED_TYPES = ("pdf",)

    def get_file_extension(self, filename: str, decoded_file: bytes) -> Optional[str]:

        # Check file type
        kind = filetype.guess(decoded_file)
        if kind is None:
            logger.warning("Could not determine valid filetype")
            return None
        elif kind.mime != "application/pdf":
            logger.warning(f"Not a PDF: {kind.mime}")
            return None
        else:
            return "pdf"


# Needed to override the default JSONField due to some undesired validation behavior where an empty dict throws a
# validation error for JSONField.
# See: https://stackoverflow.com/questions/55147169/django-admin-jsonfield-default-empty-dict-wont-save-in-admin


# Combined a couple things into a single custom JSON Field...
#
# FIRST:
#
# Needed to override the default JSONField due to some undesired validation behavior where an empty dict throws a
# validation error for JSONField.
# See: https://stackoverflow.com/questions/55147169/django-admin-jsonfield-default-empty-dict-wont-save-in-admin
#
# SECOND:
#
# UTF-8 DOES NOT RENDER PROPERLY IN DJANGO ADMIN - incorporated this solution
# http://blog.qax.io/unescaped-utf-8-in-djangos-admin-with-jsonfield/
class UTF8JSONFormField(JSONField):

    empty_values = [None, "", [], (), {}]

    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, InvalidJSONInput):
            return value
        return json.dumps(value, ensure_ascii=False)


# The default JSONField validations in admin don't allow blank JSON obj unless you override JSONField
# and forms.JsonField
class NullableJSONField(DbJSONField):
    """
    JSONField for postgres databases.
    Displays UTF-8 characters directly in the admin, i.e. äöü instead of
    unicode escape sequences.
    Also lets you have null inputs, which otherwise throw a validation error...
    """

    empty_values = [None, "", [], (), {}]

    def formfield(self, **kwargs: Any) -> Any:  # type: ignore[override]
        return super().formfield(**{"form_class": UTF8JSONFormField, **kwargs})
