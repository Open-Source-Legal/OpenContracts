/**
 * API Client for E2E test fixtures
 *
 * Provides direct GraphQL access for test setup/teardown
 * without going through the UI.
 */

interface GraphQLResponse<T> {
  data?: T;
  errors?: Array<{ message: string }>;
}

export class ApiClient {
  private baseUrl: string;
  private authToken: string | null = null;

  constructor(baseUrl?: string) {
    this.baseUrl =
      baseUrl || process.env.E2E_API_URL || "http://localhost:8000";
  }

  /**
   * Set authentication token for subsequent requests
   */
  setAuthToken(token: string) {
    this.authToken = token;
  }

  /**
   * Execute a GraphQL query/mutation
   */
  async graphql<T>(
    query: string,
    variables?: Record<string, unknown>
  ): Promise<GraphQLResponse<T>> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };

    if (this.authToken) {
      headers["Authorization"] = `Bearer ${this.authToken}`;
    }

    const response = await fetch(`${this.baseUrl}/graphql/`, {
      method: "POST",
      headers,
      body: JSON.stringify({ query, variables }),
    });

    if (!response.ok) {
      throw new Error(`GraphQL request failed: ${response.status}`);
    }

    return response.json();
  }

  /**
   * Login and get auth token
   */
  async login(username: string, password: string): Promise<string> {
    const query = `
      mutation Login($username: String!, $password: String!) {
        tokenAuth(username: $username, password: $password) {
          token
        }
      }
    `;

    const result = await this.graphql<{ tokenAuth: { token: string } }>(query, {
      username,
      password,
    });

    if (result.errors) {
      throw new Error(`Login failed: ${result.errors[0].message}`);
    }

    const token = result.data?.tokenAuth?.token;
    if (!token) {
      throw new Error("No token returned from login");
    }

    this.authToken = token;
    return token;
  }

  /**
   * Create a corpus for testing
   */
  async createCorpus(
    title: string,
    description?: string
  ): Promise<{ id: string; title: string }> {
    const query = `
      mutation CreateCorpus($title: String!, $description: String) {
        createCorpus(title: $title, description: $description) {
          ok
          message
          obj {
            id
            title
          }
        }
      }
    `;

    const result = await this.graphql<{
      createCorpus: {
        ok: boolean;
        message: string;
        obj: { id: string; title: string };
      };
    }>(query, { title, description: description || `Test corpus: ${title}` });

    if (result.errors) {
      throw new Error(`Create corpus failed: ${result.errors[0].message}`);
    }

    if (!result.data?.createCorpus?.ok) {
      throw new Error(
        `Create corpus failed: ${result.data?.createCorpus?.message}`
      );
    }

    return result.data.createCorpus.obj;
  }

  /**
   * Create a folder in a corpus
   */
  async createFolder(
    corpusId: string,
    name: string,
    parentId?: string
  ): Promise<{ id: string; name: string }> {
    const query = `
      mutation CreateFolder($corpusId: ID!, $name: String!, $parentId: ID) {
        createCorpusFolder(corpusId: $corpusId, name: $name, parentId: $parentId) {
          ok
          message
          obj {
            id
            name
          }
        }
      }
    `;

    const result = await this.graphql<{
      createCorpusFolder: {
        ok: boolean;
        message: string;
        obj: { id: string; name: string };
      };
    }>(query, { corpusId, name, parentId });

    if (result.errors) {
      throw new Error(`Create folder failed: ${result.errors[0].message}`);
    }

    if (!result.data?.createCorpusFolder?.ok) {
      throw new Error(
        `Create folder failed: ${result.data?.createCorpusFolder?.message}`
      );
    }

    return result.data.createCorpusFolder.obj;
  }

  /**
   * Delete a corpus (cleanup)
   */
  async deleteCorpus(corpusId: string): Promise<boolean> {
    const query = `
      mutation DeleteCorpus($corpusId: ID!) {
        deleteCorpus(corpusId: $corpusId) {
          ok
          message
        }
      }
    `;

    const result = await this.graphql<{
      deleteCorpus: { ok: boolean; message: string };
    }>(query, { corpusId });

    if (result.errors) {
      console.warn(`Delete corpus warning: ${result.errors[0].message}`);
      return false;
    }

    return result.data?.deleteCorpus?.ok ?? false;
  }

  /**
   * Get current user info
   */
  async getCurrentUser(): Promise<{
    id: string;
    username: string;
    email: string;
  } | null> {
    const query = `
      query CurrentUser {
        me {
          id
          username
          email
        }
      }
    `;

    const result = await this.graphql<{
      me: { id: string; username: string; email: string } | null;
    }>(query);

    if (result.errors) {
      return null;
    }

    return result.data?.me ?? null;
  }
}

/**
 * Singleton API client for tests
 */
let apiClient: ApiClient | null = null;

export function getApiClient(): ApiClient {
  if (!apiClient) {
    apiClient = new ApiClient();
  }
  return apiClient;
}
