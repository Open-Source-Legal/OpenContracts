import React, { useState, useEffect, useCallback, useRef } from "react";
import { useApolloClient } from "@apollo/client";
import styled, { createGlobalStyle } from "styled-components";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
  Textarea,
  Spinner,
} from "@os-legal/ui";
import { Info, Image, Settings, Scale, PlusCircle, Pencil } from "lucide-react";
import { LabelSetSelector } from "../widgets/CRUD/LabelSetSelector";
import { EmbedderSelector } from "../widgets/CRUD/EmbedderSelector";
import { LicenseSelector } from "../widgets/CRUD/LicenseSelector";
import { FilePreviewAndUpload } from "../widgets/file-controls/FilePreviewAndUpload";
import { CategorySelector } from "./CategorySelector";
import { CorpusType, LabelSetType } from "../../types/graphql-api";
import { arraysEqualUnordered } from "../../utils/arrayUtils";
import {
  DEFAULT_NEW_CORPUS_LICENSE,
  MOBILE_VIEW_BREAKPOINT,
} from "../../assets/configurations/constants";
import {
  GET_CORPUS_CREATE_DEFAULTS,
  GetCorpusCreateDefaultsOutput,
} from "../../graphql/queries";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../../assets/configurations/osLegalStyles";
import {
  modalFooterBorder,
  modalFooterMobile,
} from "../widgets/modals/sharedModalStyles";

// Types
export type CorpusModalMode = "CREATE" | "EDIT" | "VIEW";

export interface CorpusFormData {
  id?: string;
  title?: string;
  slug?: string;
  description?: string;
  icon?: string | null;
  labelSet?: string | null;
  preferredEmbedder?: string | null;
  categories?: string[];
  license?: string;
  licenseLink?: string;
}

export interface CorpusModalProps {
  open: boolean;
  mode: CorpusModalMode;
  corpus?: CorpusType | null;
  loading?: boolean;
  onSubmit?: (data: CorpusFormData) => void;
  onClose: () => void;
}

// 1024px: point where the modal's two-column layout collapses to single-column
// (wider than TABLET_BREAKPOINT in constants.ts because the modal content needs more room)
const TWO_COLUMN_BREAKPOINT = 1024;

// Global styles for the corpus modal — Modal renders via portal outside the
// React tree, so we must use createGlobalStyle instead of wrapper descendant selectors.
// Scoped via .corpus-modal class to avoid leaking to other concurrent modals.
// Injected unconditionally when CorpusModal is mounted, but scoping prevents side effects.
const CorpusModalStyles = createGlobalStyle`
  .corpus-modal .oc-modal-body {
    background: var(--oc-bg-subtle, ${OS_LEGAL_COLORS.surfaceLight});
  }

  /* Ensure dropdown menus appear above modal content (still needed for SUI Dropdown inside LabelSetSelector/EmbedderSelector) */
  .corpus-modal .ui.dropdown .menu {
    z-index: 1000 !important;
  }

  .corpus-modal .oc-modal-footer {
    ${modalFooterBorder}
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .corpus-modal-overlay {
      padding: 0;
      align-items: flex-end;
    }

    .corpus-modal {
      max-width: 100%;
      max-height: 95vh;
      border-radius: var(--oc-radius-lg) var(--oc-radius-lg) 0 0;
      animation: oc-slide-up-fade 0.3s var(--oc-easing-spring);
    }

    .corpus-modal .oc-modal-body {
      padding: var(--oc-spacing-md);
      padding-bottom: calc(var(--oc-spacing-xl) + 80px);
    }

    .corpus-modal .oc-modal-footer {
      position: sticky;
      bottom: 0;
      flex-direction: column-reverse;
      gap: var(--oc-spacing-sm);
      padding-bottom: calc(
        var(--oc-spacing-lg) + env(safe-area-inset-bottom, 0px)
      );

      button {
        width: 100%;
        justify-content: center;
      }
    }
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) and (orientation: landscape) {
    .corpus-modal {
      max-height: 100vh;
      border-radius: 0;
    }
  }

  @media (max-width: ${TWO_COLUMN_BREAKPOINT}px) {
    .corpus-modal {
      max-width: 90vw;
    }
  }
`;

const FormSection = styled.div`
  background: var(--oc-bg-surface);
  border-radius: var(--oc-radius-lg);
  padding: var(--oc-spacing-lg);
  margin-bottom: var(--oc-spacing-md);
  box-shadow: var(--oc-shadow-sm);
  border: 1px solid var(--oc-border-default);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: var(--oc-spacing-md);
    margin-bottom: var(--oc-spacing-sm);
    border-radius: var(--oc-radius-md);
  }

  &:last-child {
    margin-bottom: 0;
  }
`;

const SectionTitle = styled.h3`
  font-size: var(--oc-font-size-xs);
  font-weight: 600;
  color: var(--oc-fg-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 var(--oc-spacing-md) 0;
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-sm);

  svg {
    width: 14px;
    height: 14px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 11px;
    margin-bottom: var(--oc-spacing-sm);
  }
`;

const CorpusFormField = styled.div`
  margin-bottom: var(--oc-spacing-md);

  &:last-child {
    margin-bottom: 0;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin-bottom: var(--oc-spacing-sm);
  }

  /* Ensure @os-legal/ui inputs are full width and have proper mobile sizing */
  .oc-input-wrapper,
  .oc-textarea-wrapper {
    width: 100%;
  }

  .oc-input-container--lg {
    min-height: 48px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .oc-input,
    .oc-textarea {
      font-size: 16px; /* Prevent iOS zoom */
    }
  }
`;

// Two-column layout for desktop
const FormRow = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--oc-spacing-md);

  @media (max-width: ${TWO_COLUMN_BREAKPOINT}px) {
    grid-template-columns: 1fr;
  }
`;

const IconUploadWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-xl);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    flex-direction: column;
    text-align: center;
    gap: var(--oc-spacing-md);
  }
`;

const IconPreview = styled.div`
  flex-shrink: 0;
  width: 140px;
  height: 140px;
  position: relative;
  border-radius: var(--oc-radius-lg);
  overflow: hidden;
  background: var(--oc-bg-subtle);
  border: 2px dashed var(--oc-border-default);
  transition: all 0.2s ease;

  &:hover {
    border-color: var(--oc-accent);
    /* Very subtle accent tint on hover — intentionally lighter than accentLight (0.1) */
    background: ${accentAlpha(0.03)};
  }

  /* Completely restyle the FilePreviewAndUpload component */
  .ui.segment {
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    width: 100% !important;
    height: 100% !important;
    border-radius: 0 !important;
  }

  /* Make image fill the container nicely */
  img {
    width: 100% !important;
    height: 140px !important;
    object-fit: contain !important;
    padding: var(--oc-spacing-md) !important;
    background: transparent !important;
  }

  /* Style the edit overlay */
  > div > div:last-child {
    border-radius: var(--oc-radius-lg) !important;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    width: 120px;
    height: 120px;

    img {
      height: 120px !important;
      padding: var(--oc-spacing-sm) !important;
    }
  }
`;

const IconHelpText = styled.div`
  flex: 1;

  h4 {
    margin: 0 0 var(--oc-spacing-xs) 0;
    font-size: var(--oc-font-size-sm);
    font-weight: 600;
    color: var(--oc-fg-primary);
  }

  p {
    margin: 0;
    font-size: var(--oc-font-size-sm);
    color: var(--oc-fg-secondary);
    line-height: var(--oc-line-height-relaxed);
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    h4 {
      font-size: var(--oc-font-size-xs);
    }

    p {
      font-size: var(--oc-font-size-xs);
    }
  }
`;

const LoadingOverlay = styled.div<{ $visible: boolean }>`
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(2px);
  display: ${(props) => (props.$visible ? "flex" : "none")};
  align-items: center;
  justify-content: center;
  z-index: 100;
  border-radius: var(--oc-radius-lg);
`;

const HeaderIcon = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--oc-radius-md);
  background: linear-gradient(
    135deg,
    var(--oc-accent) 0%,
    var(--oc-accent-hover) 100%
  );
  color: white;
  margin-right: var(--oc-spacing-sm);

  svg {
    width: 18px;
    height: 18px;
  }
`;

/**
 * CorpusModal - A modern, mobile-friendly modal for creating and editing corpuses.
 *
 * Features:
 * - Clean, responsive design using @os-legal/ui components
 * - Tablet and mobile breakpoints with proper safe area handling
 * - Two-column layout on desktop for better space utilization
 * - Supports Create, Edit, and View modes
 * - Integrates with LabelSetSelector, EmbedderSelector, and icon upload
 */
export const CorpusModal: React.FC<CorpusModalProps> = ({
  open,
  mode,
  corpus,
  loading = false,
  onSubmit,
  onClose,
}) => {
  const isReadOnly = mode === "VIEW";
  const isCreate = mode === "CREATE";

  // Form state
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState<string | null>(null);
  const [labelSetId, setLabelSetId] = useState<string | null>(null);
  const [labelSetObj, setLabelSetObj] = useState<LabelSetType | undefined>(
    undefined
  );
  const [preferredEmbedder, setPreferredEmbedder] = useState<string | null>(
    null
  );
  const [categories, setCategories] = useState<string[]>([]);
  const [license, setLicense] = useState("");
  const [licenseLink, setLicenseLink] = useState("");

  // Track original values for change detection in EDIT mode
  const [originalValues, setOriginalValues] = useState<{
    title: string;
    slug: string;
    description: string;
    icon: string | null;
    labelSetId: string | null;
    preferredEmbedder: string | null;
    categories: string[];
    license: string;
    licenseLink: string;
  } | null>(null);

  // Track the previous open state to detect modal open transitions
  // This prevents re-initializing form when user is typing on mobile
  // Initialize to false so that if modal starts open, we still initialize the form
  const prevOpenRef = useRef(false);

  const apolloClient = useApolloClient();

  // Pre-fill defaults (default embedder + default labelset) from the backend
  // when the modal opens in CREATE mode.  Runs as a side-effect so we don't
  // block first paint of the modal — fields populate as the response lands.
  // Only one in-flight fetch per modal-open, since the form-init effect
  // resets state every time `open` flips on.
  const fetchCreateDefaults = useCallback(async () => {
    try {
      const { data } = await apolloClient.query<GetCorpusCreateDefaultsOutput>({
        query: GET_CORPUS_CREATE_DEFAULTS,
        fetchPolicy: "cache-first",
      });
      if (data?.pipelineSettings?.defaultEmbedder) {
        setPreferredEmbedder(
          (current) => current ?? data.pipelineSettings.defaultEmbedder ?? null
        );
      }
      if (data?.defaultLabelset) {
        const ls = data.defaultLabelset;
        setLabelSetId((current) => current ?? ls.id);
        setLabelSetObj(
          (current) =>
            current ??
            ({
              id: ls.id,
              title: ls.title,
              description: ls.description ?? "",
              icon: ls.icon ?? "",
              isPublic: ls.isPublic,
            } as LabelSetType)
        );
      }
    } catch {
      // Silent fallback — empty fields are still acceptable.
    }
  }, [apolloClient]);

  // Initialize form from corpus data only when modal opens (not on every render)
  useEffect(() => {
    // Only initialize form when modal transitions from closed to open
    const justOpened = open && !prevOpenRef.current;
    prevOpenRef.current = open;

    if (!justOpened) {
      return;
    }

    if (corpus) {
      const corpusTitle = corpus.title || "";
      const corpusSlug = corpus.slug || "";
      const corpusDescription = corpus.description || "";
      const corpusIcon = corpus.icon || null;
      const corpusLabelSetId = corpus.labelSet?.id || null;
      const corpusPreferredEmbedder = corpus.preferredEmbedder || null;
      const corpusCategories =
        corpus.categories?.map((category) => category.id).filter(Boolean) || [];
      const corpusLicense = corpus.license || "";
      const corpusLicenseLink = corpus.licenseLink || "";

      setTitle(corpusTitle);
      setSlug(corpusSlug);
      setDescription(corpusDescription);
      setIcon(corpusIcon);
      setLabelSetId(corpusLabelSetId);
      setLabelSetObj(corpus.labelSet || undefined);
      setPreferredEmbedder(corpusPreferredEmbedder);
      setCategories(corpusCategories);
      setLicense(corpusLicense);
      setLicenseLink(corpusLicenseLink);

      // Store original values for change detection
      setOriginalValues({
        title: corpusTitle,
        slug: corpusSlug,
        description: corpusDescription,
        icon: corpusIcon,
        labelSetId: corpusLabelSetId,
        preferredEmbedder: corpusPreferredEmbedder,
        categories: corpusCategories,
        license: corpusLicense,
        licenseLink: corpusLicenseLink,
      });
    } else {
      // Reset for create mode and pre-fill defaults.  Pre-selected values
      // are intentionally pure UX nudges — the user can clear them, and the
      // backend independently applies defaults at save time.
      setTitle("");
      setSlug("");
      setDescription("");
      setIcon(null);
      setLabelSetId(null);
      setLabelSetObj(undefined);
      setPreferredEmbedder(null);
      setCategories([]);
      setLicense(DEFAULT_NEW_CORPUS_LICENSE);
      setLicenseLink("");
      setOriginalValues(null);
      void fetchCreateDefaults();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    // corpus intentionally omitted - we only want to initialize on modal open,
    // not when corpus prop changes (which would overwrite user edits mid-form)
  }, [open]);

  // Handle form field changes
  const handleTitleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setTitle(e.target.value);
    },
    []
  );

  const handleSlugChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSlug(e.target.value);
    },
    []
  );

  const handleDescriptionChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setDescription(e.target.value);
    },
    []
  );

  const handleIconChange = useCallback(
    ({ data }: { data: string | ArrayBuffer; filename: string }) => {
      // FilePreviewAndUpload uses readAsDataURL which returns a string (base64)
      // but the type allows ArrayBuffer for flexibility
      if (typeof data === "string") {
        setIcon(data);
      }
    },
    []
  );

  const handleLabelSetChange = useCallback((values: any) => {
    setLabelSetId(values.labelSet || null);
  }, []);

  const handleEmbedderChange = useCallback((values: any) => {
    setPreferredEmbedder(values.preferredEmbedder || null);
  }, []);

  // Form validation - title and description are required;
  // CUSTOM license also requires a license URL.
  // NOTE: This validation is intentionally duplicated in Corpus.clean() (backend model)
  // and CorpusSerializer.validate() (GraphQL serializer) for defense-in-depth.
  const isFormValid =
    title.trim().length > 0 &&
    description.trim().length > 0 &&
    (license !== "CUSTOM" || licenseLink.trim().length > 0);

  // Compute isDirty by comparing current values against original values
  // For CREATE mode, form is "dirty" (has submittable content) when valid
  // For EDIT mode, compare each field against original values
  const isDirty = isCreate
    ? isFormValid
    : originalValues !== null &&
      (title !== originalValues.title ||
        slug !== originalValues.slug ||
        description !== originalValues.description ||
        icon !== originalValues.icon ||
        labelSetId !== originalValues.labelSetId ||
        preferredEmbedder !== originalValues.preferredEmbedder ||
        !arraysEqualUnordered(categories, originalValues.categories) ||
        license !== originalValues.license ||
        licenseLink !== originalValues.licenseLink);

  const canSubmit = isFormValid && isDirty && !loading;

  // Handle submit
  const handleSubmit = useCallback(() => {
    if (!canSubmit || !onSubmit) return;

    const formData: CorpusFormData = {};

    if (mode === "EDIT" && corpus && originalValues) {
      // Only include changed fields for edit mode
      formData.id = corpus.id;

      if (title.trim() !== originalValues.title) {
        formData.title = title.trim();
      }
      if (slug.trim() !== originalValues.slug) {
        formData.slug = slug.trim();
      }
      if (description.trim() !== originalValues.description) {
        formData.description = description.trim();
      }
      if (icon !== originalValues.icon) {
        formData.icon = icon;
      }
      if (labelSetId !== originalValues.labelSetId) {
        formData.labelSet = labelSetId;
      }
      if (preferredEmbedder !== originalValues.preferredEmbedder) {
        formData.preferredEmbedder = preferredEmbedder;
      }
      if (!arraysEqualUnordered(categories, originalValues.categories)) {
        formData.categories = categories;
      }
      if (license !== originalValues.license) {
        formData.license = license;
        // Clear stale license_link when switching away from CUSTOM
        if (originalValues.license === "CUSTOM" && license !== "CUSTOM") {
          formData.licenseLink = "";
        }
      }
      if (licenseLink !== originalValues.licenseLink) {
        formData.licenseLink = licenseLink;
      }
    } else {
      // Include all for create mode
      formData.title = title.trim();
      formData.slug = slug.trim() || undefined;
      formData.description = description.trim();
      formData.icon = icon;
      formData.labelSet = labelSetId;
      formData.preferredEmbedder = preferredEmbedder;
      formData.categories = categories;
      formData.license = license;
      formData.licenseLink = licenseLink;
    }

    onSubmit(formData);
  }, [
    canSubmit,
    onSubmit,
    mode,
    corpus,
    originalValues,
    title,
    slug,
    description,
    icon,
    labelSetId,
    preferredEmbedder,
    categories,
    license,
    licenseLink,
  ]);

  // Get header text based on mode
  const getHeaderText = () => {
    switch (mode) {
      case "CREATE":
        return "Create New Corpus";
      case "EDIT":
        return "Edit Corpus";
      case "VIEW":
        return "View Corpus";
      default:
        return "Corpus";
    }
  };

  const getSubtitle = () => {
    switch (mode) {
      case "CREATE":
        return "Set up a new corpus to organize your documents";
      case "EDIT":
        return title || "Update corpus details";
      case "VIEW":
        return title || "Viewing corpus details";
      default:
        return "";
    }
  };

  const headerTitle = (
    <>
      <HeaderIcon>{isCreate ? <PlusCircle /> : <Pencil />}</HeaderIcon>
      {getHeaderText()}
    </>
  );

  return (
    <>
      <CorpusModalStyles />
      <Modal
        open={open}
        onClose={onClose}
        size="lg"
        closeOnEscape={!loading}
        className="corpus-modal"
        overlayClassName="corpus-modal-overlay"
      >
        <ModalHeader
          title={headerTitle}
          subtitle={getSubtitle()}
          onClose={onClose}
          showCloseButton={!loading}
        />

        <ModalBody style={{ position: "relative" }}>
          <LoadingOverlay $visible={loading}>
            <Spinner size={32} />
          </LoadingOverlay>

          {/* Basic Info Section */}
          <FormSection>
            <SectionTitle>
              <Info />
              Basic Information
            </SectionTitle>

            <FormRow>
              <CorpusFormField>
                <Input
                  id="corpus-title"
                  label="Title *"
                  placeholder="Enter corpus title"
                  value={title}
                  onChange={handleTitleChange}
                  disabled={loading || isReadOnly}
                  size="lg"
                  fullWidth
                />
              </CorpusFormField>

              <CorpusFormField>
                <Input
                  id="corpus-slug"
                  label="Slug"
                  placeholder="my-corpus-slug (auto-generated if blank)"
                  value={slug}
                  onChange={handleSlugChange}
                  disabled={loading || isReadOnly}
                  helperText="Case-sensitive. Allowed: A-Z, a-z, 0-9, hyphen (-)"
                  size="lg"
                  fullWidth
                />
              </CorpusFormField>
            </FormRow>

            <CorpusFormField>
              <Textarea
                id="corpus-description"
                label="Description *"
                placeholder="Describe what this corpus is about..."
                value={description}
                onChange={handleDescriptionChange}
                disabled={loading || isReadOnly}
                fullWidth
                autoResize
                maxRows={6}
              />
            </CorpusFormField>
          </FormSection>

          {/* Icon Section */}
          <FormSection>
            <SectionTitle>
              <Image />
              Corpus Icon
            </SectionTitle>
            <IconUploadWrapper>
              <IconPreview>
                <FilePreviewAndUpload
                  isImage={true}
                  acceptedTypes="image/*"
                  file={icon || ""}
                  readOnly={isReadOnly}
                  disabled={loading}
                  onChange={handleIconChange}
                />
              </IconPreview>
              <IconHelpText>
                <h4>Upload an Icon</h4>
                <p>
                  Choose an image to help identify this corpus. Square images
                  work best (256x256px or larger recommended).
                </p>
              </IconHelpText>
            </IconUploadWrapper>
          </FormSection>

          {/* License Section */}
          <FormSection>
            <SectionTitle>
              <Scale />
              License
            </SectionTitle>

            <CorpusFormField>
              <LicenseSelector
                license={license}
                onChange={setLicense}
                disabled={isReadOnly || loading}
              />
            </CorpusFormField>

            {license === "CUSTOM" && (
              <CorpusFormField>
                <Input
                  id="corpus-license-link"
                  label="License URL *"
                  placeholder="https://example.com/license"
                  value={licenseLink}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setLicenseLink(e.target.value)
                  }
                  disabled={loading || isReadOnly}
                  helperText="Link to the full text of your custom license"
                  size="lg"
                  fullWidth
                />
              </CorpusFormField>
            )}
          </FormSection>

          {/* Settings Section */}
          <FormSection>
            <SectionTitle>
              <Settings />
              Settings
            </SectionTitle>

            <CorpusFormField>
              <CategorySelector
                selectedIds={categories}
                onChange={setCategories}
                disabled={isReadOnly || loading}
              />
            </CorpusFormField>

            <CorpusFormField>
              <LabelSetSelector
                read_only={isReadOnly || loading}
                labelSet={labelSetObj}
                onChange={handleLabelSetChange}
                upward
              />
            </CorpusFormField>

            <CorpusFormField>
              <EmbedderSelector
                read_only={isReadOnly || loading}
                preferredEmbedder={preferredEmbedder || undefined}
                onChange={handleEmbedderChange}
                upward
              />
            </CorpusFormField>
          </FormSection>
        </ModalBody>

        <ModalFooter>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            {isReadOnly ? "Close" : "Cancel"}
          </Button>
          {!isReadOnly && onSubmit && (
            <Button
              variant="primary"
              onClick={handleSubmit}
              disabled={!canSubmit}
              loading={loading}
            >
              {isCreate ? "Create Corpus" : "Save Changes"}
            </Button>
          )}
        </ModalFooter>
      </Modal>
    </>
  );
};

export default CorpusModal;
