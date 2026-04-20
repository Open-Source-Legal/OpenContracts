import { describe, it, expect } from "vitest";
import type { DocumentNode } from "graphql";
import {
  GET_GLOBAL_AGENTS,
  CREATE_GLOBAL_AGENT_CONFIGURATION,
  UPDATE_GLOBAL_AGENT_CONFIGURATION,
  DELETE_GLOBAL_AGENT_CONFIGURATION,
} from "../global_agent_management.graphql";

/**
 * Minimal smoke tests that exist so v8 (the unit-test coverage provider)
 * records a hit for every module-level statement in the shared GraphQL
 * document file. The Playwright CT suites exercise these documents via
 * real mutations, but Istanbul instrumentation at the CT layer only
 * reports a DA entry on the first line of each `gql\`...\`` expression —
 * leaving the rest of the diff block looking "missing" in Codecov's
 * patch calc. Importing here makes v8 cover the entire module.
 */

function opName(doc: DocumentNode): string | undefined {
  for (const def of doc.definitions) {
    if (def.kind === "OperationDefinition" && def.name) {
      return def.name.value;
    }
  }
  return undefined;
}

describe("global_agent_management.graphql documents", () => {
  it("exports a named GetGlobalAgents query", () => {
    expect(GET_GLOBAL_AGENTS).toBeDefined();
    expect(opName(GET_GLOBAL_AGENTS)).toBe("GetGlobalAgents");
  });

  it("exports a named CreateGlobalAgentConfiguration mutation", () => {
    expect(CREATE_GLOBAL_AGENT_CONFIGURATION).toBeDefined();
    expect(opName(CREATE_GLOBAL_AGENT_CONFIGURATION)).toBe(
      "CreateGlobalAgentConfiguration"
    );
  });

  it("exports a named UpdateGlobalAgentConfiguration mutation", () => {
    expect(UPDATE_GLOBAL_AGENT_CONFIGURATION).toBeDefined();
    expect(opName(UPDATE_GLOBAL_AGENT_CONFIGURATION)).toBe(
      "UpdateGlobalAgentConfiguration"
    );
  });

  it("exports a named DeleteGlobalAgentConfiguration mutation", () => {
    expect(DELETE_GLOBAL_AGENT_CONFIGURATION).toBeDefined();
    expect(opName(DELETE_GLOBAL_AGENT_CONFIGURATION)).toBe(
      "DeleteGlobalAgentConfiguration"
    );
  });
});
