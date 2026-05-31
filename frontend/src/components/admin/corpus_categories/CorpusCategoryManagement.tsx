import React, { useMemo, useState, useCallback } from "react";
import { useQuery, useMutation, useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import {
  Button,
  IconButton,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Table,
} from "@os-legal/ui";
import {
  Plus,
  Pencil,
  Trash2,
  Save,
  ChevronLeft,
  Tag,
  ShieldAlert,
} from "lucide-react";
import { toast } from "react-toastify";
import styled from "styled-components";

import { backendUserObj } from "../../../graphql/cache";
import { StyledTextArea } from "../../widgets/modals/styled";
import { ErrorMessage, LoadingState } from "../../widgets/feedback";
import { ConfirmModal } from "../../widgets/modals/ConfirmModal";
import {
  GradientSegment as StyledSegment,
  PageHeader as BasePageHeader,
  ScrollableTableWrapper,
} from "../../layout/SharedSegments";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  MOBILE_VIEW_BREAKPOINT,
  DEFAULT_CATEGORY_ICON as DEFAULT_ICON,
  DEFAULT_CATEGORY_COLOR as DEFAULT_COLOR,
  MAX_CATEGORY_DESCRIPTION_LENGTH,
} from "../../../assets/configurations/constants";
import { resolveLucideIcon } from "./iconResolver";
import {
  GET_ADMIN_CORPUS_CATEGORIES,
  CREATE_CORPUS_CATEGORY,
  UPDATE_CORPUS_CATEGORY,
  DELETE_CORPUS_CATEGORY,
  AdminCorpusCategoriesResult,
  CreateCorpusCategoryInputs,
  CreateCorpusCategoryOutput,
  UpdateCorpusCategoryInputs,
  UpdateCorpusCategoryOutput,
  DeleteCorpusCategoryInputs,
  DeleteCorpusCategoryOutput,
  ManagedCorpusCategory,
} from "./graphql";

const Container = styled.div`
  padding: 2rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
  }
`;

const PageHeader = styled(BasePageHeader)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;

  h2 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
  }
`;

const BackButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  background: none;
  border: none;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  font-size: 0.875rem;
  margin-bottom: 1rem;
  padding: 0;

  &:hover {
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const ColorSwatch = styled.span<{ $color: string }>`
  display: inline-block;
  width: 1rem;
  height: 1rem;
  border-radius: 50%;
  background: ${(props) => props.$color};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  vertical-align: middle;
  margin-right: 0.5rem;
`;

const FormField = styled.div`
  margin-bottom: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
`;

const FormLabel = styled.label`
  font-weight: 600;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const HelperText = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const ColorInputRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const ColorPickerInput = styled.input`
  width: 40px;
  height: 36px;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
`;

const Centered = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  text-align: center;
  padding: 4rem 2rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const IconCell = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
`;

interface CategoryFormState {
  name: string;
  description: string;
  icon: string;
  color: string;
  sortOrder: string;
}

const EMPTY_FORM: CategoryFormState = {
  name: "",
  description: "",
  icon: DEFAULT_ICON,
  color: DEFAULT_COLOR,
  sortOrder: "0",
};

const HEX_COLOR_RE = /^#[0-9A-Fa-f]{6}$/;

export const CorpusCategoryManagement: React.FC = () => {
  const navigate = useNavigate();
  const backendUser = useReactiveVar(backendUserObj);
  const isSuperuser = backendUser?.isSuperuser === true;

  const { data, loading, error, refetch } =
    useQuery<AdminCorpusCategoriesResult>(GET_ADMIN_CORPUS_CATEGORIES, {
      fetchPolicy: "cache-and-network",
    });

  // Modal + form state
  const [showFormModal, setShowFormModal] = useState(false);
  const [editingCategory, setEditingCategory] =
    useState<ManagedCorpusCategory | null>(null);
  const [form, setForm] = useState<CategoryFormState>(EMPTY_FORM);
  const [categoryToDelete, setCategoryToDelete] =
    useState<ManagedCorpusCategory | null>(null);

  const refetchAndToast = useCallback(
    (message: string) => {
      toast.success(message);
      setShowFormModal(false);
      setEditingCategory(null);
      refetch();
    },
    [refetch]
  );

  const [createCategory, { loading: creating }] = useMutation<
    CreateCorpusCategoryOutput,
    CreateCorpusCategoryInputs
  >(CREATE_CORPUS_CATEGORY, {
    onCompleted: (result) => {
      if (result.createCorpusCategory?.ok) {
        refetchAndToast("Category created");
      } else {
        toast.error(
          result.createCorpusCategory?.message || "Failed to create category"
        );
      }
    },
    onError: (err) => toast.error(`Error creating category: ${err.message}`),
  });

  const [updateCategory, { loading: updating }] = useMutation<
    UpdateCorpusCategoryOutput,
    UpdateCorpusCategoryInputs
  >(UPDATE_CORPUS_CATEGORY, {
    onCompleted: (result) => {
      if (result.updateCorpusCategory?.ok) {
        refetchAndToast("Category updated");
      } else {
        toast.error(
          result.updateCorpusCategory?.message || "Failed to update category"
        );
      }
    },
    onError: (err) => toast.error(`Error updating category: ${err.message}`),
  });

  const [deleteCategory, { loading: deleting }] = useMutation<
    DeleteCorpusCategoryOutput,
    DeleteCorpusCategoryInputs
  >(DELETE_CORPUS_CATEGORY, {
    // The confirm modal stays open (caller-closed) while the delete is
    // in-flight so its spinner is visible, so every outcome must clear the
    // pending category to dismiss it.
    onCompleted: (result) => {
      setCategoryToDelete(null);
      if (result.deleteCorpusCategory?.ok) {
        toast.success("Category deleted");
        refetch();
      } else {
        toast.error(
          result.deleteCorpusCategory?.message || "Failed to delete category"
        );
      }
    },
    onError: (err) => {
      setCategoryToDelete(null);
      toast.error(`Error deleting category: ${err.message}`);
    },
  });

  const categories = useMemo<ManagedCorpusCategory[]>(
    () =>
      (data?.corpusCategories?.edges?.map((edge) => edge.node) || [])
        // The query has no orderBy arg, so order client-side by sortOrder to
        // match the column the table displays (ties fall back to name).
        .slice()
        .sort(
          (a, b) =>
            (a.sortOrder ?? 0) - (b.sortOrder ?? 0) ||
            (a.name ?? "").localeCompare(b.name ?? "")
        ),
    [data]
  );

  const openCreateModal = useCallback(() => {
    setEditingCategory(null);
    setForm(EMPTY_FORM);
    setShowFormModal(true);
  }, []);

  const openEditModal = useCallback((category: ManagedCorpusCategory) => {
    setEditingCategory(category);
    setForm({
      name: category.name ?? "",
      description: category.description ?? "",
      icon: category.icon ?? DEFAULT_ICON,
      color: category.color ?? DEFAULT_COLOR,
      sortOrder: String(category.sortOrder ?? 0),
    });
    setShowFormModal(true);
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmedName = form.name.trim();
    if (!trimmedName) {
      toast.error("Category name is required");
      return;
    }
    if (form.color && !HEX_COLOR_RE.test(form.color)) {
      toast.error("Color must be a hex value like #3B82F6");
      return;
    }
    const parsedSortOrder = parseInt(form.sortOrder, 10);
    const sortOrder = Number.isNaN(parsedSortOrder) ? 0 : parsedSortOrder;

    if (editingCategory) {
      updateCategory({
        variables: {
          id: editingCategory.id,
          name: trimmedName,
          description: form.description,
          icon: form.icon || DEFAULT_ICON,
          color: form.color || DEFAULT_COLOR,
          sortOrder,
        },
      });
    } else {
      createCategory({
        variables: {
          name: trimmedName,
          description: form.description,
          icon: form.icon || DEFAULT_ICON,
          color: form.color || DEFAULT_COLOR,
          sortOrder,
        },
      });
    }
  }, [form, editingCategory, createCategory, updateCategory]);

  const handleConfirmDelete = useCallback(() => {
    if (categoryToDelete) {
      deleteCategory({ variables: { id: categoryToDelete.id } });
    }
  }, [categoryToDelete, deleteCategory]);

  // Superuser gate. Backend mutations also enforce this, but we render a
  // friendly message rather than letting a non-superuser hit failing calls.
  if (!isSuperuser) {
    return (
      <Container>
        <BackButton onClick={() => navigate("/admin/settings")}>
          <ChevronLeft size={16} />
          Back to Admin Settings
        </BackButton>
        <Centered>
          <ShieldAlert size={40} color={OS_LEGAL_COLORS.danger} />
          <h3>Superuser access required</h3>
          <p>You do not have permission to manage corpus categories.</p>
        </Centered>
      </Container>
    );
  }

  if (loading && categories.length === 0) {
    return (
      <Container>
        <LoadingState message="Loading categories..." />
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <ErrorMessage title="Error loading categories">
          {error.message}
        </ErrorMessage>
      </Container>
    );
  }

  return (
    <Container>
      <BackButton onClick={() => navigate("/admin/settings")}>
        <ChevronLeft size={16} />
        Back to Admin Settings
      </BackButton>

      <StyledSegment>
        <PageHeader>
          <h2>
            <Tag size={22} />
            Corpus Categories
          </h2>
          <Button
            variant="primary"
            leftIcon={<Plus size={14} />}
            onClick={openCreateModal}
          >
            New Category
          </Button>
        </PageHeader>

        {categories.length === 0 ? (
          <Centered>
            <Tag size={40} color={OS_LEGAL_COLORS.textTertiary} />
            <h3>No categories yet</h3>
            <p>Create your first corpus category to start tagging corpuses.</p>
          </Centered>
        ) : (
          <ScrollableTableWrapper $minWidth="720px">
            <Table variant="bordered">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>Order</Table.HeadCell>
                  <Table.HeadCell>Name</Table.HeadCell>
                  <Table.HeadCell>Icon</Table.HeadCell>
                  <Table.HeadCell>Description</Table.HeadCell>
                  <Table.HeadCell>Corpuses</Table.HeadCell>
                  <Table.HeadCell>Actions</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {categories.map((category) => {
                  const IconComponent = resolveLucideIcon(category.icon);
                  return (
                    <Table.Row key={category.id}>
                      <Table.Cell>{category.sortOrder ?? 0}</Table.Cell>
                      <Table.Cell>
                        <ColorSwatch $color={category.color || DEFAULT_COLOR} />
                        {category.name}
                      </Table.Cell>
                      <Table.Cell>
                        <IconCell>
                          <IconComponent size={16} />
                          {category.icon}
                        </IconCell>
                      </Table.Cell>
                      <Table.Cell>{category.description}</Table.Cell>
                      <Table.Cell>{category.corpusCount ?? 0}</Table.Cell>
                      <Table.Cell>
                        <IconButton
                          aria-label={`Edit ${category.name}`}
                          onClick={() => openEditModal(category)}
                        >
                          <Pencil size={16} />
                        </IconButton>
                        <IconButton
                          aria-label={`Delete ${category.name}`}
                          onClick={() => setCategoryToDelete(category)}
                        >
                          <Trash2 size={16} color={OS_LEGAL_COLORS.danger} />
                        </IconButton>
                      </Table.Cell>
                    </Table.Row>
                  );
                })}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>
        )}
      </StyledSegment>

      {/* Create / Edit Modal */}
      <Modal
        open={showFormModal}
        onClose={() => setShowFormModal(false)}
        size="md"
      >
        <ModalHeader
          title={editingCategory ? "Edit Category" : "New Category"}
          onClose={() => setShowFormModal(false)}
        />
        <ModalBody>
          <FormField>
            <FormLabel htmlFor="category-name">Name</FormLabel>
            <Input
              id="category-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Case Law"
              fullWidth
            />
          </FormField>

          <FormField>
            <FormLabel htmlFor="category-description">Description</FormLabel>
            <StyledTextArea
              id="category-description"
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
              placeholder="Short description shown in tooltips"
              rows={3}
              maxLength={MAX_CATEGORY_DESCRIPTION_LENGTH}
            />
          </FormField>

          <FormField>
            <FormLabel htmlFor="category-icon">Icon</FormLabel>
            <Input
              id="category-icon"
              value={form.icon}
              onChange={(e) => setForm({ ...form, icon: e.target.value })}
              placeholder="e.g. gavel"
              fullWidth
            />
            <HelperText>
              Lucide icon name in kebab-case (e.g. <code>file-text</code>,{" "}
              <code>gavel</code>, <code>scroll</code>). See lucide.dev/icons.
            </HelperText>
          </FormField>

          <FormField>
            <FormLabel htmlFor="category-color">Color</FormLabel>
            <ColorInputRow>
              <ColorPickerInput
                type="color"
                aria-label="Color picker"
                value={
                  HEX_COLOR_RE.test(form.color) ? form.color : DEFAULT_COLOR
                }
                onChange={(e) => setForm({ ...form, color: e.target.value })}
              />
              <Input
                id="category-color"
                value={form.color}
                onChange={(e) => setForm({ ...form, color: e.target.value })}
                placeholder="#3B82F6"
              />
            </ColorInputRow>
            <HelperText>Hex color used for the category badge.</HelperText>
          </FormField>

          <FormField>
            <FormLabel htmlFor="category-sort-order">Sort order</FormLabel>
            <Input
              id="category-sort-order"
              type="number"
              value={form.sortOrder}
              onChange={(e) => setForm({ ...form, sortOrder: e.target.value })}
              placeholder="0"
            />
            <HelperText>Lower numbers appear first.</HelperText>
          </FormField>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setShowFormModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            loading={creating || updating}
            leftIcon={<Save size={16} />}
          >
            {editingCategory ? "Save Changes" : "Create Category"}
          </Button>
        </ModalFooter>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmModal
        visible={categoryToDelete !== null}
        message={
          categoryToDelete
            ? `Delete the "${
                categoryToDelete.name
              }" category? It will be removed from ${
                categoryToDelete.corpusCount ?? 0
              } corpus(es). This cannot be undone.`
            : ""
        }
        yesAction={handleConfirmDelete}
        // noAction is a no-op: cancelling (or overlay/escape) closes the dialog
        // via toggleModal, which clears the pending category.
        noAction={() => {}}
        toggleModal={() => setCategoryToDelete(null)}
        confirmLabel="Delete"
        // Supplying this opts the modal into caller-controlled close so the
        // spinner stays visible until the mutation settles (see the delete
        // mutation's onCompleted/onError, which clear the pending category).
        confirmLoading={deleting}
      />
    </Container>
  );
};

export default CorpusCategoryManagement;
