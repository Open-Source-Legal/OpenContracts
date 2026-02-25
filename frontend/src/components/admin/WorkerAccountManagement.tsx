import React, { useState } from "react";
import { useQuery, useMutation } from "@apollo/client";
import {
  Button,
  Table,
  Header,
  Message,
  Dimmer,
  Loader,
  Icon,
  Modal,
  Form,
  Input,
  TextArea,
  Label,
} from "semantic-ui-react";
import styled from "styled-components";
import { toast } from "react-toastify";
import { ConfirmModal } from "../widgets/modals/ConfirmModal";
import {
  GET_WORKER_ACCOUNTS,
  GetWorkerAccountsOutput,
  WorkerAccountData,
  CREATE_WORKER_ACCOUNT,
  CreateWorkerAccountInput,
  CreateWorkerAccountOutput,
  DEACTIVATE_WORKER_ACCOUNT,
  DeactivateWorkerAccountInput,
  DeactivateWorkerAccountOutput,
} from "../../graphql/queries/workerQueries";

// ============================================================================
// Styled Components
// ============================================================================

const Container = styled.div`
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;

  @media (max-width: 768px) {
    padding: 1rem;
  }
`;

const PageHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;

  @media (max-width: 768px) {
    flex-direction: column;
    gap: 1rem;
    text-align: center;
  }
`;

const PageTitle = styled(Header)`
  &.ui.header {
    margin: 0;
    color: #1e293b;

    @media (max-width: 768px) {
      font-size: 1.5rem !important;
    }
  }
`;

const StyledSegment = styled.div`
  border-radius: 12px;
  background: white;
  border: 1px solid rgba(226, 232, 240, 0.8);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  overflow-x: auto;
  padding: 1rem;
`;

const StatusBadge = styled(Label)<{ $active: boolean }>`
  &.ui.label {
    background: ${(props) => (props.$active ? "#dcfce7" : "#fef3c7")};
    color: ${(props) => (props.$active ? "#166534" : "#92400e")};
    font-weight: 500;
  }
`;

const TokenCountBadge = styled(Label)`
  &.ui.label {
    background: #f1f5f9;
    color: #475569;
    font-weight: 500;
  }
`;

// ============================================================================
// Component
// ============================================================================

export const WorkerAccountManagement: React.FC = () => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [accountToDeactivate, setAccountToDeactivate] =
    useState<WorkerAccountData | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const { loading, error, data, refetch } =
    useQuery<GetWorkerAccountsOutput>(GET_WORKER_ACCOUNTS);

  const [createAccount, { loading: creating }] = useMutation<
    CreateWorkerAccountOutput,
    CreateWorkerAccountInput
  >(CREATE_WORKER_ACCOUNT, {
    onCompleted: (data) => {
      if (data.createWorkerAccount.ok) {
        toast.success("Worker account created successfully");
        setShowCreateModal(false);
        setName("");
        setDescription("");
        refetch();
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const [deactivateAccount, { loading: deactivating }] = useMutation<
    DeactivateWorkerAccountOutput,
    DeactivateWorkerAccountInput
  >(DEACTIVATE_WORKER_ACCOUNT, {
    onCompleted: (data) => {
      if (data.deactivateWorkerAccount.ok) {
        toast.success("Worker account deactivated");
        setDeactivateModalOpen(false);
        setAccountToDeactivate(null);
        refetch();
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const handleCreate = () => {
    if (!name.trim()) {
      toast.error("Name is required");
      return;
    }
    createAccount({
      variables: {
        name: name.trim(),
        description: description.trim() || undefined,
      },
    });
  };

  const accounts: WorkerAccountData[] = data?.workerAccounts || [];

  if (loading) {
    return (
      <Container>
        <Dimmer active inverted>
          <Loader>Loading worker accounts...</Loader>
        </Dimmer>
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <Message negative>
          <Message.Header>Error loading worker accounts</Message.Header>
          <p>{error.message}</p>
        </Message>
      </Container>
    );
  }

  return (
    <Container>
      <PageHeader>
        <PageTitle as="h1">
          <Icon name="server" /> Worker Account Management
        </PageTitle>
        <Button
          primary
          icon
          labelPosition="left"
          onClick={() => {
            setName("");
            setDescription("");
            setShowCreateModal(true);
          }}
        >
          <Icon name="plus" />
          Create Worker Account
        </Button>
      </PageHeader>

      <StyledSegment>
        {accounts.length === 0 ? (
          <Message info>
            <Message.Header>No Worker Accounts</Message.Header>
            <p>
              Create a worker account to allow external document processing
              workers to upload pre-processed documents.
            </p>
          </Message>
        ) : (
          <Table basic="very" striped>
            <Table.Header>
              <Table.Row>
                <Table.HeaderCell>Name</Table.HeaderCell>
                <Table.HeaderCell>Status</Table.HeaderCell>
                <Table.HeaderCell>Creator</Table.HeaderCell>
                <Table.HeaderCell>Tokens</Table.HeaderCell>
                <Table.HeaderCell>Created</Table.HeaderCell>
                <Table.HeaderCell textAlign="right">Actions</Table.HeaderCell>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {accounts.map((account) => (
                <Table.Row key={account.id}>
                  <Table.Cell>
                    <strong>{account.name}</strong>
                    {account.description && (
                      <div style={{ color: "#64748b", fontSize: "0.875rem" }}>
                        {account.description}
                      </div>
                    )}
                  </Table.Cell>
                  <Table.Cell>
                    <StatusBadge $active={account.isActive}>
                      {account.isActive ? "Active" : "Inactive"}
                    </StatusBadge>
                  </Table.Cell>
                  <Table.Cell>{account.creatorUsername || "—"}</Table.Cell>
                  <Table.Cell>
                    <TokenCountBadge>
                      <Icon name="key" />
                      {account.tokenCount}
                    </TokenCountBadge>
                  </Table.Cell>
                  <Table.Cell>
                    {new Date(account.created).toLocaleDateString()}
                  </Table.Cell>
                  <Table.Cell textAlign="right">
                    {account.isActive && (
                      <Button
                        size="small"
                        color="orange"
                        icon
                        labelPosition="left"
                        onClick={() => {
                          setAccountToDeactivate(account);
                          setDeactivateModalOpen(true);
                        }}
                      >
                        <Icon name="ban" />
                        Deactivate
                      </Button>
                    )}
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        )}
      </StyledSegment>

      {/* Create Worker Account Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        size="small"
      >
        <Modal.Header>
          <Icon name="server" /> Create Worker Account
        </Modal.Header>
        <Modal.Content>
          <Form>
            <Form.Field required>
              <label>Name</label>
              <Input
                placeholder="e.g., docling-worker-1"
                value={name}
                onChange={(_, d) => setName(d.value)}
              />
            </Form.Field>
            <Form.Field>
              <label>Description</label>
              <TextArea
                placeholder="Optional description of this worker account"
                value={description}
                onChange={(_, d) => setDescription(d.value as string)}
              />
            </Form.Field>
          </Form>
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={() => setShowCreateModal(false)}>Cancel</Button>
          <Button
            primary
            loading={creating}
            disabled={!name.trim() || creating}
            onClick={handleCreate}
          >
            Create Account
          </Button>
        </Modal.Actions>
      </Modal>

      {/* Deactivate Confirmation */}
      <ConfirmModal
        visible={deactivateModalOpen}
        message={`Are you sure you want to deactivate worker account "${accountToDeactivate?.name}"? This will implicitly revoke all its access tokens.`}
        yesAction={() => {
          if (accountToDeactivate) {
            deactivateAccount({
              variables: { workerAccountId: accountToDeactivate.id },
            });
          }
        }}
        noAction={() => {
          setAccountToDeactivate(null);
        }}
        toggleModal={() => {
          setDeactivateModalOpen(false);
        }}
      />
    </Container>
  );
};

export default WorkerAccountManagement;
