import graphene
from django.conf import settings
from graphql.validation import specified_rules

from config.graphql.mutations import Mutation
from config.graphql.queries import Query
from config.graphql.security import DepthLimitValidationRule, DisableIntrospection

# Build validation rules: the FULL GraphQL spec rule set, plus depth limiting
# always and introspection disabling in production.
#
# The spec rules MUST be listed explicitly: graphql-core's
# ``validate(schema, document, rules)`` REPLACES the default rule set when
# ``rules`` is provided. Passing only the custom hardening rules silently
# disabled every standard validation (unknown arguments/fields, variable
# type checks, ...) on the served endpoint — invalid queries executed with
# the bogus parts ignored instead of erroring, which let ~26 invalid
# frontend documents ship unnoticed. Pinned by
# ``test_security_hardening.TestServedValidationRulesIncludeSpecRules``; the
# frontend documents themselves are swept by
# ``tests/architecture/test_frontend_graphql_documents.py`` (and
# ``scripts/validate_frontend_graphql.py`` for ad-hoc runs).
#
# NOTE: This list is built at import time. Tests that override settings.DEBUG
# after import must use graphql-core's validate() directly with the rule classes.
validation_rules: list = [*specified_rules, DepthLimitValidationRule]
if not settings.DEBUG:
    validation_rules.append(DisableIntrospection)

# Create schema with auto_camelcase for consistency
schema = graphene.Schema(
    mutation=Mutation,
    query=Query,
    auto_camelcase=True,
)
