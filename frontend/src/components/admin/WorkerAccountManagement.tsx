import React, { useState } from "react";
import { gql, useQuery, useMutation, useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Table,
} from "@os-legal/ui";
import styled from "styled-components";
import { toast } from "react-toastify";
import { Upload, ArrowLeft } from "lucide-react";
import { StyledTextArea } from "../widgets/modals/styled";
import { FormField } from "../widgets/form/FormField";
import {
  ErrorMessage,
  InfoMessage,
  WarningMessage,
  LoadingState,
} from "../widgets/feedback";

import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import {
  MOBILE_VIEW_BREAKPOINT,
  WORKER_TABLE_MIN_WIDTH_PX,
} from "../../assets/configurations/constants";
import {
  CardSegment as StyledSegment,
  PageHeader as BasePageHeader,
  ScrollableTableWrapper,
} from "../layout/SharedSegments";
import { StatusBadge } from "../agents/AgentBadges";
import { backendUserObj } from "../../graphql/cache";

// ---------------------------------------------------------------------------
// GraphQL operations
// ---------------------------------------------------------------------------

const GET_WORKER_ACCOUNTS = gql`
  query GetWorkerAccounts {
    workerAccounts {
      id
      name
      description
      isActive
      tokenCount
      creatorName
      created
    }
  }
`;

const CREATE_WORKER_ACCOUNT = gql`
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

const DEACTIVATE_WORKER_ACCOUNT = gql`
  mutation DeactivateWorkerAccount($workerAccountId: Int!) {
    deactivateWorkerAccount(workerAccountId: $workerAccountId) {
      ok
    }
  }
`;

const REACTIVATE_WORKER_ACCOUNT = gql`
  mutation ReactivateWorkerAccount($workerAccountId: Int!) {
    reactivateWorkerAccount(workerAccountId: $workerAccountId) {
      ok
    }
  }
`;

// ---------------------------------------------------------------------------
// Styled components
// ---------------------------------------------------------------------------

const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
  }
`;

const BackLink = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  margin-bottom: 1.5rem;
  transition: color 0.15s ease;

  &:hover {
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const PageHeader = styled(BasePageHeader)`
  align-items: flex-start;
`;

const PageTitleGroup = styled.div``;

const PageTitle = styled.h1`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 1.75rem;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 0.5rem 0;
`;

const PageSubtitle = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 1rem;
  margin: 0;
  line-height: 1.5;
`;

const TruncatedCell = styled.span`
  display: inline-block;
  max-width: 250px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WorkerAccount {
  id: number;
  name: string;
  description: string | null;
  isActive: boolean;
  tokenCount: number;
  creatorName: string;
  created: string;
}

interface FormState {
  name: string;
  description: string;
}

const initialFormState: FormState = {
  name: "",
  description: "",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const WorkerAccountManagement: React.FC = () => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(backendUserObj);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [accountToDeactivate, setAccountToDeactivate] =
    useState<WorkerAccount | null>(null);

  const isSuperuser = currentUser?.isSuperuser === true;

  const { loading, error, data, refetch } = useQuery(GET_WORKER_ACCOUNTS, {
    skip: !isSuperuser,
  });

  const [createAccount, { loading: creating }] = useMutation(
    CREATE_WORKER_ACCOUNT,
    {
      onCompleted: (result) => {
        if (result.createWorkerAccount.ok) {
          toast.success("Worker account created successfully");
          setShowCreateModal(false);
          setFormState(initialFormState);
          refetch();
        } else {
          toast.error("Failed to create worker account");
        }
      },
      onError: (err) => toast.error(err.message),
    }
  );

  const [deactivateAccount] = useMutation(DEACTIVATE_WORKER_ACCOUNT, {
    onCompleted: (result) => {
      if (result.deactivateWorkerAccount.ok) {
        toast.success("Worker account deactivated");
        refetch();
      } else {
        toast.error("Failed to deactivate worker account");
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const [reactivateAccount] = useMutation(REACTIVATE_WORKER_ACCOUNT, {
    onCompleted: (result) => {
      if (result.reactivateWorkerAccount.ok) {
        toast.success("Worker account reactivated");
        refetch();
      } else {
        toast.error("Failed to reactivate worker account");
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const handleCreate = () => {
    createAccount({
      variables: {
        name: formState.name.trim(),
        description: formState.description.trim() || null,
      },
    });
  };

  const handleToggleActive = (account: WorkerAccount) => {
    if (account.isActive) {
      setAccountToDeactivate(account);
    } else {
      reactivateAccount({
        variables: { workerAccountId: account.id },
      });
    }
  };

  const handleConfirmDeactivate = () => {
    if (accountToDeactivate) {
      deactivateAccount({
        variables: { workerAccountId: accountToDeactivate.id },
      });
      setAccountToDeactivate(null);
    }
  };

  const accounts: WorkerAccount[] = data?.workerAccounts ?? [];

  if (!isSuperuser) {
    return (
      <Container>
        <WarningMessage title="Access Denied">
          Only administrators can manage worker accounts.
        </WarningMessage>
      </Container>
    );
  }

  if (loading) {
    return (
      <Container>
        <LoadingState message="Loading worker accounts..." />
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <ErrorMessage title="Error loading worker accounts">
          {error.message}
        </ErrorMessage>
      </Container>
    );
  }

  return (
    <Container>
      <BackLink onClick={() => navigate("/admin/settings")}>
        <ArrowLeft size={14} />
        Back to Admin Settings
      </BackLink>

      <PageHeader>
        <PageTitleGroup>
          <PageTitle>
            <Upload size={28} color={OS_LEGAL_COLORS.accent} />
            Worker Accounts
          </PageTitle>
          <PageSubtitle>
            Manage service accounts used by automated pipelines to upload and
            process documents.
          </PageSubtitle>
        </PageTitleGroup>
        <Button
          variant="primary"
          onClick={() => {
            setFormState(initialFormState);
            setShowCreateModal(true);
          }}
        >
          Create Account
        </Button>
      </PageHeader>

      <StyledSegment>
        {accounts.length === 0 ? (
          <InfoMessage title="No Worker Accounts">
            Create your first worker account to enable automated document upload
            pipelines.
          </InfoMessage>
        ) : (
          <ScrollableTableWrapper
            $minWidth={`${WORKER_TABLE_MIN_WIDTH_PX}px`}
            data-testid="worker-accounts-table-scroll"
          >
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>Name</Table.HeadCell>
                  <Table.HeadCell>Description</Table.HeadCell>
                  <Table.HeadCell>Status</Table.HeadCell>
                  <Table.HeadCell>Tokens</Table.HeadCell>
                  <Table.HeadCell>Creator</Table.HeadCell>
                  <Table.HeadCell>Created</Table.HeadCell>
                  <Table.HeadCell>Actions</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {accounts.map((account) => (
                  <Table.Row key={account.id}>
                    <Table.Cell>
                      <strong>{account.name}</strong>
                    </Table.Cell>
                    <Table.Cell>
                      <TruncatedCell>
                        {account.description || "-"}
                      </TruncatedCell>
                    </Table.Cell>
                    <Table.Cell>
                      <StatusBadge $active={account.isActive}>
                        {account.isActive ? "Active" : "Inactive"}
                      </StatusBadge>
                    </Table.Cell>
                    <Table.Cell>{account.tokenCount}</Table.Cell>
                    <Table.Cell>{account.creatorName}</Table.Cell>
                    <Table.Cell>
                      {new Date(account.created).toLocaleDateString()}
                    </Table.Cell>
                    <Table.Cell>
                      {account.isActive ? (
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => handleToggleActive(account)}
                        >
                          Deactivate
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="primary"
                          onClick={() => handleToggleActive(account)}
                        >
                          Activate
                        </Button>
                      )}
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>
        )}
      </StyledSegment>

      {/* Create Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        size="sm"
      >
        <ModalHeader
          title="Create Worker Account"
          onClose={() => setShowCreateModal(false)}
        />
        <ModalBody>
          <form>
            <FormField $required>
              <label>Name</label>
              <Input
                fullWidth
                placeholder="Worker account name"
                value={formState.name}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({ ...formState, name: e.target.value })
                }
              />
            </FormField>
            <FormField>
              <label>Description</label>
              <StyledTextArea
                placeholder="Optional description of this worker account"
                value={formState.description}
                onChange={(e) =>
                  setFormState({ ...formState, description: e.target.value })
                }
                rows={3}
              />
            </FormField>
          </form>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!formState.name.trim() || creating}
            loading={creating}
            onClick={handleCreate}
          >
            Create Account
          </Button>
        </ModalFooter>
      </Modal>

      {/* Deactivate Confirmation */}
      <Modal
        open={accountToDeactivate !== null}
        onClose={() => setAccountToDeactivate(null)}
        size="sm"
      >
        <ModalHeader
          title="Confirm Deactivation"
          onClose={() => setAccountToDeactivate(null)}
        />
        <ModalBody>
          Are you sure you want to deactivate &quot;
          {accountToDeactivate?.name}&quot;? This will invalidate all access
          tokens for this account.
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setAccountToDeactivate(null)}
          >
            Cancel
          </Button>
          <Button variant="danger" onClick={handleConfirmDeactivate}>
            Deactivate
          </Button>
        </ModalFooter>
      </Modal>
    </Container>
  );
};

export default WorkerAccountManagement;
