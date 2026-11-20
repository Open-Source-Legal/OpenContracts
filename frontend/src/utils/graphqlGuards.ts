/**
 * GraphQL Query Guard Utilities
 * Ensures GraphQL queries are never made with invalid or missing required variables
 */

import { DocumentNode } from "@apollo/client";
import { isValidGraphQLId } from "./idValidation";

/**
 * Guards a GraphQL query to ensure required variables are present and valid
 */
export interface GuardedQueryOptions<TVariables> {
  query: DocumentNode;
  variables: TVariables;
  requiredFields?: Array<keyof TVariables>;
  idFields?: Array<keyof TVariables>;
  onError?: (errors: string[]) => void;
}

/**
 * Result of a guarded query check
 */
export interface GuardedQueryResult<TVariables> {
  canExecute: boolean;
  variables: TVariables;
  errors: string[];
}

/**
 * Guards a GraphQL query to ensure it has valid variables
 */
export function guardGraphQLQuery<TVariables extends Record<string, any>>({
  variables,
  requiredFields = [],
  idFields = [],
  onError,
}: Omit<
  GuardedQueryOptions<TVariables>,
  "query"
>): GuardedQueryResult<TVariables> {
  const errors: string[] = [];
  const safeVariables = { ...variables };

  // Check required fields
  for (const field of requiredFields) {
    const value = variables[field as string];
    if (value === undefined || value === null || value === "") {
      errors.push(`Missing required field: ${String(field)}`);
      // Provide a safe default to prevent GraphQL errors
      (safeVariables as any)[field as string] = "";
    }
  }

  // Validate ID fields
  for (const field of idFields) {
    const value = variables[field as string];
    if (value && !isValidGraphQLId(value)) {
      errors.push(`Invalid GraphQL ID for field ${String(field)}: ${value}`);
      // Don't execute query with invalid IDs
      if (onError) {
        onError(errors);
      }
      return {
        canExecute: false,
        variables: safeVariables,
        errors,
      };
    }
  }

  if (errors.length > 0 && onError) {
    onError(errors);
  }

  // Only execute if all ID fields are valid (required fields can have defaults)
  const canExecute = idFields.every((field) => {
    const value = variables[field as string];
    return !value || isValidGraphQLId(value);
  });

  return {
    canExecute,
    variables: safeVariables,
    errors,
  };
}

/**
 * Creates a safe query executor that validates before executing
 */
export function createSafeQueryExecutor<
  TData,
  TVariables extends Record<string, any>,
>(
  queryFn: (options: {
    variables: TVariables;
  }) => Promise<{ data?: TData; error?: any }>,
  config: {
    requiredFields?: Array<keyof TVariables>;
    idFields?: Array<keyof TVariables>;
    onValidationError?: (errors: string[]) => void;
  }
) {
  return async (
    variables: TVariables
  ): Promise<{ data?: TData; error?: any; skipped?: boolean }> => {
    const guardResult = guardGraphQLQuery({
      variables,
      requiredFields: config.requiredFields,
      idFields: config.idFields,
      onError: config.onValidationError,
    });

    if (!guardResult.canExecute) {
      console.warn(
        "Query execution blocked due to validation errors:",
        guardResult.errors
      );
      return {
        skipped: true,
        error: new Error(
          `Query validation failed: ${guardResult.errors.join(", ")}`
        ),
      };
    }

    try {
      return await queryFn({ variables: guardResult.variables });
    } catch (error) {
      console.error("Query execution error:", error);
      return { error };
    }
  };
}

/**
 * Hook-like utility to ensure corpus ID is valid before querying
 */
export function ensureValidCorpusId(
  corpus: { id?: string | null } | null | undefined
): { id: string | undefined; isValid: boolean } {
  const id = corpus?.id;

  if (!id) {
    return { id: undefined, isValid: false };
  }

  if (!isValidGraphQLId(id)) {
    console.warn(`Invalid corpus ID detected: ${id}`);
    return { id: undefined, isValid: false };
  }

  return { id, isValid: true };
}

/**
 * Hook-like utility to ensure document ID is valid before querying
 */
export function ensureValidDocumentId(
  document: { id?: string | null } | null | undefined
): { id: string | undefined; isValid: boolean } {
  const id = document?.id;

  if (!id) {
    return { id: undefined, isValid: false };
  }

  if (!isValidGraphQLId(id)) {
    console.warn(`Invalid document ID detected: ${id}`);
    return { id: undefined, isValid: false };
  }

  return { id, isValid: true };
}

/**
 * Ensures variables object has valid IDs for all specified fields
 */
export function ensureValidIdVariables<T extends Record<string, any>>(
  variables: T,
  idFields: Array<keyof T>
): T {
  const cleaned = { ...variables };

  for (const field of idFields) {
    const value = cleaned[field as string];
    if (value && !isValidGraphQLId(value)) {
      console.warn(`Removing invalid ID from field ${String(field)}: ${value}`);
      delete cleaned[field as string];
    }
  }

  return cleaned;
}
