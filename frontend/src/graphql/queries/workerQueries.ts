import { gql } from "@apollo/client";

// ============================================================================
// Types
// ============================================================================

export interface WorkerAccountData {
  id: number;
  name: string;
  description: string;
  isActive: boolean;
  created: string;
  tokenCount: number;
  creatorUsername: string | null;
}

export interface CorpusAccessTokenData {
  id: number;
  keyPrefix: string;
  workerAccountName: string;
  corpusId: number;
  corpusTitle: string;
  expiresAt: string | null;
  isActive: boolean;
  rateLimitPerMinute: number;
  created: string;
  uploadCount: number;
}

export interface WorkerDocumentUploadData {
  id: string;
  status: string;
  corpusId: number;
  corpusTitle: string;
  workerAccountName: string | null;
  errorMessage: string;
  created: string;
  processingStarted: string | null;
  processingFinished: string | null;
}

// ============================================================================
// Queries
// ============================================================================

export interface GetWorkerAccountsOutput {
  workerAccounts: WorkerAccountData[];
}

export const GET_WORKER_ACCOUNTS = gql`
  query GetWorkerAccounts {
    workerAccounts {
      id
      name
      description
      isActive
      created
      tokenCount
      creatorUsername
    }
  }
`;

export interface GetCorpusAccessTokensInput {
  corpusId: number;
}

export interface GetCorpusAccessTokensOutput {
  corpusAccessTokens: CorpusAccessTokenData[];
}

export const GET_CORPUS_ACCESS_TOKENS = gql`
  query GetCorpusAccessTokens($corpusId: Int!) {
    corpusAccessTokens(corpusId: $corpusId) {
      id
      keyPrefix
      workerAccountName
      corpusId
      corpusTitle
      expiresAt
      isActive
      rateLimitPerMinute
      created
      uploadCount
    }
  }
`;

export interface GetWorkerDocumentUploadsInput {
  corpusId: number;
  status?: string;
}

export interface GetWorkerDocumentUploadsOutput {
  workerDocumentUploads: WorkerDocumentUploadData[];
}

export const GET_WORKER_DOCUMENT_UPLOADS = gql`
  query GetWorkerDocumentUploads($corpusId: Int!, $status: String) {
    workerDocumentUploads(corpusId: $corpusId, status: $status) {
      id
      status
      corpusId
      corpusTitle
      workerAccountName
      errorMessage
      created
      processingStarted
      processingFinished
    }
  }
`;

// ============================================================================
// Mutations
// ============================================================================

export interface CreateWorkerAccountInput {
  name: string;
  description?: string;
}

export interface CreateWorkerAccountOutput {
  createWorkerAccount: {
    ok: boolean;
    workerAccount: {
      id: number;
      name: string;
      description: string;
      isActive: boolean;
      created: string;
    };
  };
}

export const CREATE_WORKER_ACCOUNT = gql`
  mutation CreateWorkerAccount($name: String!, $description: String) {
    createWorkerAccount(name: $name, description: $description) {
      ok
      workerAccount {
        id
        name
        description
        isActive
        created
      }
    }
  }
`;

export interface DeactivateWorkerAccountInput {
  workerAccountId: number;
}

export interface DeactivateWorkerAccountOutput {
  deactivateWorkerAccount: {
    ok: boolean;
  };
}

export const DEACTIVATE_WORKER_ACCOUNT = gql`
  mutation DeactivateWorkerAccount($workerAccountId: Int!) {
    deactivateWorkerAccount(workerAccountId: $workerAccountId) {
      ok
    }
  }
`;

export interface CreateCorpusAccessTokenInput {
  workerAccountId: number;
  corpusId: number;
  expiresAt?: string;
  rateLimitPerMinute?: number;
}

export interface CreateCorpusAccessTokenOutput {
  createCorpusAccessToken: {
    ok: boolean;
    token: {
      id: number;
      key: string;
      workerAccountName: string;
      corpusId: number;
      expiresAt: string | null;
      rateLimitPerMinute: number;
      created: string;
    };
  };
}

export const CREATE_CORPUS_ACCESS_TOKEN = gql`
  mutation CreateCorpusAccessToken(
    $workerAccountId: Int!
    $corpusId: Int!
    $expiresAt: DateTime
    $rateLimitPerMinute: Int
  ) {
    createCorpusAccessToken(
      workerAccountId: $workerAccountId
      corpusId: $corpusId
      expiresAt: $expiresAt
      rateLimitPerMinute: $rateLimitPerMinute
    ) {
      ok
      token {
        id
        key
        workerAccountName
        corpusId
        expiresAt
        rateLimitPerMinute
        created
      }
    }
  }
`;

export interface RevokeCorpusAccessTokenInput {
  tokenId: number;
}

export interface RevokeCorpusAccessTokenOutput {
  revokeCorpusAccessToken: {
    ok: boolean;
  };
}

export const REVOKE_CORPUS_ACCESS_TOKEN = gql`
  mutation RevokeCorpusAccessToken($tokenId: Int!) {
    revokeCorpusAccessToken(tokenId: $tokenId) {
      ok
    }
  }
`;
