"""Fail-closed automation operation policy, checked before ANY resolver runs.

Root fields are explicit capabilities. Selections may read scalar payloads and
the listed DTO/connection edges, never arbitrary ORM relationships. Checking
the selected operation's entire AST prevents mixed mutations from partially
executing before a later denied field is encountered. Aliases, fragments,
directives and coerced variables use graphql-core's execution helpers.
"""

from graphql import (
    ExecutionResult,
    GraphQLError,
    GraphQLIncludeDirective,
    GraphQLSkipDirective,
    get_named_type,
    get_operation_ast,
)
from graphql.execution.values import (
    get_argument_values,
    get_directive_values,
    get_variable_values,
)
from graphql.language import FieldNode, FragmentDefinitionNode, FragmentSpreadNode
from rest_framework.exceptions import PermissionDenied
from strawberry.extensions import SchemaExtension

from opencontractserver.enrichment.services.authority_permissions import (
    is_authority_admin,
)
from opencontractserver.users.services.automation_credentials import (
    DENIED,
    Scope,
    require_scope,
)

# (scope, corpus argument). None means system-wide/unbound and therefore
# requires explicit all-corpus authorization. Existing service checks still run.
OPERATIONS = {
    "Query": {
        "corpus": (Scope.CORPUS_READ, "id"),
        "corpuses": (Scope.CORPUS_READ, "id"),
        "adminDocumentIngestion": (Scope.INGESTION_READ, None),
        "adminWorkerUploads": (Scope.INGESTION_READ, None),
        "adminCorpusImports": (Scope.INGESTION_READ, None),
        "adminBulkImportSessions": (Scope.INGESTION_READ, None),
        "authorityPacks": (Scope.AUTHORITY_ADMIN, None),
        "authorityPackPreflight": (Scope.AUTHORITY_ADMIN, None),
        "authorityNamespaces": (Scope.AUTHORITY_ADMIN, None),
        "authorityKeyEquivalences": (Scope.AUTHORITY_ADMIN, None),
        "authorityFrontier": (Scope.AUTHORITY_ADMIN, None),
    },
    "Mutation": {
        "createCorpus": (Scope.CORPUS_CREATE, None),
        "updateCorpus": (Scope.CORPUS_CONFIGURE, "id"),
        "updateCorpusDescription": (Scope.CORPUS_CONFIGURE, "corpusId"),
        "setCorpusVisibility": (Scope.CORPUS_PUBLISH, "corpusId"),
        "reEmbedCorpus": (Scope.INGESTION_REPAIR, "corpusId"),
        # Document retry affects the document globally, so it requires an
        # unrestricted corpus boundary as well as the resolver's document EDIT.
        "retryDocumentProcessing": (Scope.INGESTION_REPAIR, None),
        "installAuthorityPack": (Scope.AUTHORITY_ADMIN, None),
        "createAuthorityNamespace": (Scope.AUTHORITY_ADMIN, None),
        "updateAuthorityNamespace": (Scope.AUTHORITY_ADMIN, None),
        "setAuthorityNamespaceAliases": (Scope.AUTHORITY_ADMIN, None),
        "deleteAuthorityNamespace": (Scope.AUTHORITY_ADMIN, None),
        "createAuthorityKeyEquivalence": (Scope.AUTHORITY_ADMIN, None),
        "updateAuthorityKeyEquivalence": (Scope.AUTHORITY_ADMIN, None),
        "deleteAuthorityKeyEquivalence": (Scope.AUTHORITY_ADMIN, None),
        "requeueAuthorityFrontier": (Scope.AUTHORITY_ADMIN, None),
        "resetAuthorityFrontier": (Scope.AUTHORITY_ADMIN, None),
        "rerouteAuthorityFrontier": (Scope.AUTHORITY_ADMIN, None),
        "approveAuthorityFrontier": (Scope.AUTHORITY_ADMIN, None),
        "deleteAuthorityFrontier": (Scope.AUTHORITY_ADMIN, None),
        "runAuthorityDiscovery": (Scope.AUTHORITY_ADMIN, None),
    },
}

# Corpus fields can contain implicit relations even when their return type is
# scalar (e.g. aggregate counts). Limit reads to this metadata contract.
CORPUS_FIELDS = frozenset(
    {
        "id",
        "title",
        "slug",
        "description",
        "created",
        "modified",
        "isPublic",
        "backendLock",
        "preferredEmbedder",
        "preferredLlm",
        "license",
        "licenseLink",
        "corpusAgentInstructions",
        "documentAgentInstructions",
        "myPermissions",
    }
)

# Explicit object-valued edges that stay inside the authorized result. All
# other nested objects/relationships are denied, including Node traversal.
OBJECT_FIELDS = {
    "CorpusTypeConnection": {"edges", "pageInfo"},
    "CorpusTypeEdge": {"node"},
    "UpdateCorpusDescription": {"obj"},
    "AuthorityPack": {"corpora"},
    "InstallAuthorityPackMutation": {"pack"},
    "AuthorityNamespaceNodeConnection": {"edges", "pageInfo"},
    "AuthorityNamespaceNodeEdge": {"node"},
    "AuthorityKeyEquivalenceNodeConnection": {"edges", "pageInfo"},
    "AuthorityKeyEquivalenceNodeEdge": {"node"},
    "AuthorityFrontierNodeConnection": {"edges", "pageInfo"},
    "AuthorityFrontierNodeEdge": {"node"},
    "CreateAuthorityNamespaceMutation": {"obj"},
    "UpdateAuthorityNamespaceMutation": {"obj"},
    "SetAuthorityNamespaceAliasesMutation": {"obj"},
    "CreateAuthorityKeyEquivalenceMutation": {"obj"},
    "UpdateAuthorityKeyEquivalenceMutation": {"obj"},
    "AdminDocumentIngestionPageType": {"items"},
    "AdminWorkerUploadPageType": {"items"},
    "AdminCorpusImportPageType": {"items"},
    "AdminBulkImportSessionPageType": {"items"},
}


def _selections(selection_set, fragments, variables):
    for node in selection_set.selections:
        skip = get_directive_values(GraphQLSkipDirective, node, variables)
        include = get_directive_values(GraphQLIncludeDirective, node, variables)
        if (skip and skip["if"]) or (include and not include["if"]):
            continue
        if isinstance(node, FieldNode):
            yield node
        else:
            fragment = (
                fragments[node.name.value]
                if isinstance(node, FragmentSpreadNode)
                else node
            )
            yield from _selections(fragment.selection_set, fragments, variables)


def _check(user, parent, selection_set, fragments, variables, *, root=False):
    for node in _selections(selection_set, fragments, variables):
        name = node.name.value
        if name == "__typename":
            continue
        field = parent.fields.get(name)
        if field is None:
            raise PermissionDenied(DENIED)
        if root:
            policy = OPERATIONS.get(parent.name, {}).get(name)
            if policy is None:
                raise PermissionDenied(DENIED)
            scope, corpus_arg = policy
            args = get_argument_values(field, node, variables)
            require_scope(user, scope, args.get(corpus_arg) if corpus_arg else None)
            if scope == Scope.AUTHORITY_ADMIN and not is_authority_admin(user):
                raise PermissionDenied(DENIED)
            if name == "installAuthorityPack":
                require_scope(user, Scope.CORPUS_CREATE)
                require_scope(user, Scope.CORPUS_CONFIGURE)
                if args.get("publish"):
                    require_scope(user, Scope.CORPUS_PUBLISH)
        elif parent.name == "CorpusType" and name not in CORPUS_FIELDS:
            raise PermissionDenied(DENIED)
        if node.selection_set:
            if not root and name not in OBJECT_FIELDS.get(parent.name, set()):
                raise PermissionDenied(DENIED)
            _check(
                user,
                get_named_type(field.type),
                node.selection_set,
                fragments,
                variables,
            )


class AutomationScopeExtension(SchemaExtension):
    def on_execute(self):
        context = self.execution_context
        user = getattr(context.context, "user", None)
        if getattr(user, "automation_credential", None) is not None:
            document = context.graphql_document
            # Strawberry only enters execution after parsing and validation.
            assert document is not None
            schema = context.schema._schema
            operation = get_operation_ast(document, context.operation_name)
            if operation is None:
                context.result = ExecutionResult(
                    data=None, errors=[GraphQLError(DENIED)]
                )
            else:
                variables = get_variable_values(
                    schema,
                    operation.variable_definitions or (),
                    context.variables or {},
                )
                if isinstance(variables, list):
                    context.result = ExecutionResult(data=None, errors=variables)
                else:
                    fragments = {
                        node.name.value: node
                        for node in document.definitions
                        if isinstance(node, FragmentDefinitionNode)
                    }
                    try:
                        parent = schema.get_root_type(operation.operation)
                        _check(
                            user,
                            parent,
                            operation.selection_set,
                            fragments,
                            variables,
                            root=True,
                        )
                    except PermissionDenied:
                        context.result = ExecutionResult(
                            data=None, errors=[GraphQLError(DENIED)]
                        )
        yield
