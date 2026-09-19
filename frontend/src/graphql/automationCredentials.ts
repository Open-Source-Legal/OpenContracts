import { gql } from "@apollo/client";

export interface AutomationCredential {
  id: string;
  userId: string;
  username: string;
  name: string;
  scopes: string[];
  corpusIds: string[] | null;
  expiresAt: string | null;
  revokedAt: string | null;
  createdAt: string;
  rotatedAt: string | null;
  status: string;
}

const METADATA = gql`
  fragment CredentialMetadata on AutomationCredentialMetadata {
    id
    userId
    username
    name
    scopes
    corpusIds
    expiresAt
    revokedAt
    createdAt
    rotatedAt
    status
  }
`;

export const GET_AUTOMATION_CREDENTIALS = gql`
  query AutomationCredentials($offset: Int!) {
    automationCredentials(offset: $offset) {
      totalCount
      items {
        ...CredentialMetadata
      }
    }
  }
  ${METADATA}
`;

export const GET_AUTOMATION_CREDENTIAL = gql`
  query AutomationCredential($id: UUID!) {
    automationCredential(id: $id) {
      ...CredentialMetadata
    }
  }
  ${METADATA}
`;

export const GET_AUTOMATION_SCOPES = gql`
  query AutomationCredentialScopes {
    automationCredentialScopes
  }
`;

export const GET_AUTOMATION_CHOICES = gql`
  query AutomationCredentialChoices(
    $kind: String!
    $search: String!
    $offset: Int!
  ) {
    automationCredentialChoices(kind: $kind, search: $search, offset: $offset) {
      totalCount
      items {
        id
        label
      }
    }
  }
`;

export const MINT_AUTOMATION_CREDENTIAL = gql`
  mutation MintAutomationCredential(
    $name: String!
    $scopes: [String!]!
    $corpusIds: [ID!]
    $allCorpuses: Boolean!
    $expiresDays: Int!
  ) {
    mintAutomationCredential(
      name: $name
      scopes: $scopes
      corpusIds: $corpusIds
      allCorpuses: $allCorpuses
      expiresDays: $expiresDays
    ) {
      token
    }
  }
`;

export const ROTATE_AUTOMATION_CREDENTIAL = gql`
  mutation RotateAutomationCredential($id: UUID!) {
    rotateAutomationCredential(id: $id) {
      token
    }
  }
`;

export const REVOKE_AUTOMATION_CREDENTIAL = gql`
  mutation RevokeAutomationCredential($id: UUID!) {
    revokeAutomationCredential(id: $id) {
      id
      status
    }
  }
`;
