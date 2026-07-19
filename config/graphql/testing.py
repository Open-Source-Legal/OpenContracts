"""GraphQL test client for the strawberry schema.

Drop-in replacement for ``graphene.test.Client`` — same constructor and
``execute`` signature, same result dict shape (``{"data": ..., "errors":
[...]}``, errors formatted with message/locations/path) — so the existing
test suite keeps its substantive assertions unchanged.
"""

from __future__ import annotations

import json
from typing import Any

from django.test import TestCase


class Client:
    """Synchronous GraphQL test client (graphene-test-compatible API)."""

    def __init__(self, schema: Any, context_value: Any = None, **defaults: Any):
        self.schema = schema
        self.context_value = context_value
        self.defaults = defaults

    def execute(
        self,
        query: str,
        variables: dict | None = None,
        variable_values: dict | None = None,
        context_value: Any = None,
        context: Any = None,
        operation_name: str | None = None,
        **kwargs: Any,
    ) -> dict:
        # ``context`` is graphene's alias for ``context_value`` — accept both
        # so existing tests written against ``graphene.test.Client`` keep
        # working unchanged.
        ctx = context_value if context_value is not None else context
        result = self.schema.execute_sync(
            query,
            variable_values=variables if variables is not None else variable_values,
            context_value=(ctx if ctx is not None else self.context_value),
            operation_name=operation_name,
        )
        formatted: dict = {}
        if result.errors:
            formatted["errors"] = [error.formatted for error in result.errors]
        formatted["data"] = result.data
        return formatted


def graphql_query(
    query: str,
    operation_name: str | None = None,
    input_data: dict | None = None,
    variables: dict | None = None,
    headers: dict | None = None,
    client: Any = None,
    graphql_url: str = "/graphql/",
):
    """HTTP-level GraphQL POST helper (port of
    ``graphene_django.utils.testing.graphql_query``)."""
    from django.test import Client as DjangoClient

    if client is None:
        client = DjangoClient()

    body: dict = {"query": query}
    if operation_name:
        body["operationName"] = operation_name
    if variables:
        body["variables"] = variables
    if input_data:
        if "variables" in body:
            body["variables"]["input"] = input_data
        else:
            body["variables"] = {"input": input_data}
    if headers:
        return client.post(
            graphql_url,
            json.dumps(body),
            content_type="application/json",
            headers=headers,
        )
    return client.post(graphql_url, json.dumps(body), content_type="application/json")


class GraphQLTestCase(TestCase):
    """Endpoint-level GraphQL test case (port of
    ``graphene_django.utils.testing.GraphQLTestCase`` against the
    strawberry view)."""

    GRAPHQL_URL = "/graphql/"

    def query(
        self,
        query: str,
        operation_name: str | None = None,
        input_data: dict | None = None,
        variables: dict | None = None,
        headers: dict | None = None,
    ):
        return graphql_query(
            query,
            operation_name=operation_name,
            input_data=input_data,
            variables=variables,
            headers=headers,
            client=self.client,
            graphql_url=self.GRAPHQL_URL,
        )

    def assertResponseNoErrors(self, resp, msg: str | None = None):
        content = json.loads(resp.content)
        self.assertEqual(resp.status_code, 200, msg or content)
        self.assertNotIn("errors", list(content.keys()), msg or content)

    def assertResponseHasErrors(self, resp, msg: str | None = None):
        content = json.loads(resp.content)
        self.assertIn("errors", list(content.keys()), msg or content)
