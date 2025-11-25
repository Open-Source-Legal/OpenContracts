import { useCallback, useEffect, useState, useMemo } from "react";
import { gql, useReactiveVar } from "@apollo/client";
import {
  Button,
  Modal,
  Grid,
  Divider,
  Segment,
  Header,
  Icon,
} from "semantic-ui-react";
import _ from "lodash";

import Form from "@rjsf/semantic-ui";
import validator from "@rjsf/validator-ajv8";
import { DocumentUploadList } from "../../documents/DocumentUploadList";
import { HorizontallyCenteredDiv } from "../../layout/Wrappers";
import { newDocForm_Schema, newDocForm_Ui_Schema } from "../../forms/schemas";
import {
  ApolloError,
  useApolloClient,
  useMutation,
  useQuery,
} from "@apollo/client";
import {
  UploadDocumentInputProps,
  UploadDocumentOutputProps,
  UPLOAD_DOCUMENT,
} from "../../../graphql/mutations";
import { toBase64 } from "../../../utils/files";
import { toast } from "react-toastify";
import { CorpusType, DocumentType } from "../../../types/graphql-api";
import {
  GET_CORPUSES,
  GetCorpusesInputs,
  GetCorpusesOutputs,
} from "../../../graphql/queries";
import { CorpusSelector } from "../../corpuses/CorpusSelector";
import { uploadModalPreloadedFiles } from "../../../graphql/cache";
import { GET_DOCUMENTS } from "../../../graphql/queries";
import { GET_CORPUS_FOLDERS } from "../../../graphql/queries/folders";

export const NOT_STARTED = "NOT_STARTED";
export const SUCCESS = "SUCCESS";
export const FAILED = "FAILED";
export const UPLOADING = "UPLOADING";

export interface FileDetailsProps {
  title?: string;
  slug?: string;
  description?: string;
}

export interface FileUploadPackageProps {
  file: File;
  formData: FileDetailsProps;
}

interface RightColProps {
  files: FileUploadPackageProps[];
  selected_file_num: number;
  handleChange: (a: any) => void;
}

function RightCol({ files, selected_file_num, handleChange }: RightColProps) {
  if (files && files.length > 0 && selected_file_num >= 0) {
    return (
      <Segment style={{ height: "100%", width: "100%", padding: "2rem" }}>
        <Form
          schema={newDocForm_Schema}
          uiSchema={newDocForm_Ui_Schema}
          validator={validator}
          onChange={handleChange}
          formData={files[selected_file_num].formData}
        >
          <></>
        </Form>
      </Segment>
    );
  }
  return (
    <Segment
      placeholder
      style={{ height: "100%", width: "100%", padding: "2rem" }}
    >
      <Header icon>
        <Icon name="settings" />
        Click on a document to update default title and descriptions.
      </Header>
    </Segment>
  );
}

interface DocumentUploadModalProps {
  open: boolean;
  onClose: () => void;
  refetch?: (args?: any) => any | void;
  corpusId?: string | null;
  folderId?: string | null;
}

export function DocumentUploadModal(props: DocumentUploadModalProps) {
  const client = useApolloClient();

  const { open, onClose, refetch, corpusId, folderId } = props;
  const [files, setFiles] = useState<FileUploadPackageProps[]>([]);
  const preloadedFiles = useReactiveVar(uploadModalPreloadedFiles);
  const [upload_state, setUploadState] = useState<
    ("NOT_STARTED" | "SUCCESS" | "FAILED" | "UPLOADING")[]
  >([]);
  const [selected_file_num, selectFileNum] = useState<number>(-1);
  const [step, setStep] = useState<"upload" | "edit" | "corpus" | "uploading">(
    "upload"
  );
  const [selected_corpus, setSelectedCorpus] = useState<CorpusType | null>(
    null
  );
  const [search_term, setSearchTerm] = useState("");

  useEffect(() => {
    if (open && preloadedFiles.length > 0) {
      setFiles(preloadedFiles);
      uploadModalPreloadedFiles([]); // Clear the preloaded files
    }
  }, [open, preloadedFiles]);

  useEffect(() => {
    if (!open) {
      setUploadState([]);
      setFiles([]);
      selectFileNum(-1);
      setStep("upload");
      setSelectedCorpus(null);
      setSearchTerm("");
    }
  }, [open]);

  const [uploadDocument] =
    useMutation<UploadDocumentOutputProps>(UPLOAD_DOCUMENT);

  // CRITICAL: Memoize variables to prevent new object on every render causing Apollo refetch
  const corpusesVariables = useMemo(
    () => ({ textSearch: search_term }),
    [search_term]
  );

  const {
    refetch: refetch_corpuses,
    loading: corpus_loading,
    data: corpus_load_data,
    error: corpus_load_error,
  } = useQuery<GetCorpusesOutputs, GetCorpusesInputs>(GET_CORPUSES, {
    variables: corpusesVariables,
    notifyOnNetworkStatusChange: true,
    skip: !open, // CRITICAL: Only fetch when modal is open to prevent cache conflicts
  });

  const corpuses = corpus_load_data?.corpuses?.edges
    ? corpus_load_data.corpuses.edges
        .map((edge) => (edge ? edge.node : undefined))
        .filter((item): item is CorpusType => !!item)
    : [];

  const updateSearch = useCallback(
    _.debounce(setSearchTerm, 400, { maxWait: 1000 }),
    []
  );

  useEffect(() => {
    refetch_corpuses();
  }, [search_term]);

  const toggleSelectedDoc = (new_index: number) => {
    selectFileNum(new_index === selected_file_num ? -1 : new_index);
  };

  const addFile = (file_package: FileUploadPackageProps) => {
    setFiles((files) => [
      ...(files ? files : []),
      {
        ...file_package,
        formData: {
          slug: "",
          description: file_package.formData.description,
          title: file_package.formData.title,
        },
        status: NOT_STARTED,
      },
    ]);
    setUploadState((statuses) => [...statuses, NOT_STARTED]);
  };

  const uploadFiles = async () => {
    console.log(
      "[UPLOAD] Starting upload with folderId:",
      folderId,
      "corpusId:",
      corpusId
    );
    toast.info("Starting upload...");
    setStep("uploading");
    let uploads: Promise<any>[] = [];
    if (files) {
      // IMPORTANT: Use for...of instead of forEach to properly handle async/await
      // forEach doesn't wait for async callbacks, causing uploads array to be empty
      for (const [file_index, file_package] of files.entries()) {
        setFileStatus(UPLOADING, file_index);
        var base_64_str = await toBase64(file_package.file);
        if (typeof base_64_str === "string" || base_64_str instanceof String) {
          const uploadVariables = {
            base64FileString: base_64_str.split(",")[1],
            filename: file_package.file.name,
            customMeta: {},
            description: file_package.formData.description,
            title: file_package.formData.title,
            slug: file_package.formData.slug,
            addToCorpusId: corpusId || selected_corpus?.id,
            addToFolderId: folderId,
            makePublic: false,
          };
          console.log(
            "[UPLOAD] Uploading file:",
            file_package.file.name,
            "with variables:",
            {
              addToCorpusId: uploadVariables.addToCorpusId,
              addToFolderId: uploadVariables.addToFolderId,
            }
          );
          uploads.push(
            uploadDocument({
              variables: uploadVariables,
              // Skip cache update - rely on refetch to get correct folder-filtered results
              // Manual cache updates don't account for folder filtering and cause temporary display issues
            })
              .then(({ data, errors }) => {
                console.log(
                  "[UPLOAD] Upload mutation response for:",
                  file_package.file.name
                );
                console.log("[UPLOAD]   - data:", data);
                console.log("[UPLOAD]   - errors:", errors);
                console.log("[UPLOAD]   - ok:", data?.uploadDocument?.ok);
                console.log(
                  "[UPLOAD]   - message:",
                  data?.uploadDocument?.message
                );
                console.log(
                  "[UPLOAD]   - document:",
                  data?.uploadDocument?.document
                );

                if (data?.uploadDocument?.ok) {
                  setFileStatus(SUCCESS, file_index);
                } else {
                  console.error(
                    "[UPLOAD] Upload mutation returned ok=false or undefined"
                  );
                  setFileStatus(FAILED, file_index);
                  toast.error(
                    data?.uploadDocument?.message ||
                      "Upload failed - check authentication"
                  );
                }
              })
              .catch((upload_error: ApolloError) => {
                console.error(
                  "[UPLOAD] Upload mutation threw error for:",
                  file_package.file.name
                );
                console.error("[UPLOAD]   - message:", upload_error.message);
                console.error(
                  "[UPLOAD]   - networkError:",
                  upload_error.networkError
                );
                console.error(
                  "[UPLOAD]   - graphQLErrors:",
                  upload_error.graphQLErrors
                );
                toast.error(
                  upload_error.message || "Upload failed - check authentication"
                );
                setFileStatus(FAILED, file_index);
              })
          );
        }
      }
    }
    console.log(
      "[UPLOAD] All upload promises created, waiting for completion..."
    );
    await Promise.all(uploads);
    console.log("[UPLOAD] All uploads complete, triggering refetch...");

    // Refetch documents and folders to get correct folder-filtered results
    // This must happen AFTER all uploads complete to avoid race conditions
    await client.refetchQueries({
      include: [GET_DOCUMENTS, GET_CORPUS_FOLDERS],
    });
    console.log("[UPLOAD] Refetch complete, closing modal");

    onClose();
    if (refetch) {
      refetch();
    }
  };

  const removeFile = (file_index: number) => {
    setFiles((files) =>
      files?.filter((file_package, index) => index !== file_index)
    );
  };

  const handleChange = ({ formData }: { formData: FileDetailsProps }) => {
    setFiles((files) =>
      files.map((file_package, index) =>
        index === selected_file_num
          ? { ...file_package, formData }
          : file_package
      )
    );
  };

  const setFileStatus = (
    doc_status: "NOT_STARTED" | "SUCCESS" | "FAILED" | "UPLOADING",
    doc_index: number
  ) => {
    setUploadState((states) =>
      states.map((state, state_index) =>
        state_index === doc_index ? doc_status : state
      )
    );
  };

  const upload_status = upload_state.reduce((previousValue, currentValue) => {
    return previousValue === FAILED || currentValue === FAILED
      ? FAILED
      : previousValue === UPLOADING || currentValue === UPLOADING
      ? UPLOADING
      : previousValue === SUCCESS && currentValue === SUCCESS
      ? SUCCESS
      : NOT_STARTED;
  }, NOT_STARTED);

  const renderUploadStep = () => (
    <div>
      <DocumentUploadList
        selected_file_num={selected_file_num}
        documents={files}
        statuses={upload_state}
        onAddFile={addFile}
        onRemove={removeFile}
        onSelect={toggleSelectedDoc}
      />
    </div>
  );

  const renderEditStep = () => (
    <Grid columns={2} stackable textAlign="center">
      <Divider vertical>Details:</Divider>
      <Grid.Row verticalAlign="middle">
        <Grid.Column style={{ paddingRight: "2rem" }}>
          <DocumentUploadList
            selected_file_num={selected_file_num}
            documents={files}
            statuses={upload_state}
            onAddFile={addFile}
            onRemove={removeFile}
            onSelect={toggleSelectedDoc}
          />
        </Grid.Column>
        <Grid.Column style={{ paddingLeft: "2rem" }}>
          <div style={{ height: "100%", width: "100%" }}>
            <div
              style={{
                height: "40vh",
                width: "100%",
                padding: "1rem",
              }}
            >
              <RightCol
                files={files}
                selected_file_num={selected_file_num}
                handleChange={handleChange}
              />
            </div>
          </div>
        </Grid.Column>
      </Grid.Row>
    </Grid>
  );

  const renderCorpusStep = () => (
    <CorpusSelector
      selected_corpus={selected_corpus}
      onClick={setSelectedCorpus}
      searchCorpus={refetch_corpuses}
      setSearchTerm={updateSearch}
      search_term={search_term}
      loading={corpus_loading}
      corpuses={corpuses}
    />
  );

  const renderUploadingStep = () => (
    <div>
      <DocumentUploadList
        selected_file_num={selected_file_num}
        documents={files}
        statuses={upload_state}
        onAddFile={addFile}
        onRemove={removeFile}
        onSelect={toggleSelectedDoc}
      />
    </div>
  );

  return (
    <Modal open={open} onClose={() => onClose()}>
      <HorizontallyCenteredDiv>
        <div style={{ marginTop: "1rem", textAlign: "left" }}>
          <Header as="h2">
            <Icon name="file pdf outline" />
            <Header.Content>
              Upload Your Documents
              <Header.Subheader>
                {step === "upload" && "Select New Document Files to Upload"}
                {step === "edit" && "Edit Document Details"}
                {step === "corpus" && "Select a Corpus (Optional)"}
                {step === "uploading" && "Uploading Documents"}
              </Header.Subheader>
            </Header.Content>
          </Header>
        </div>
      </HorizontallyCenteredDiv>
      <Modal.Content>
        {step === "upload" && renderUploadStep()}
        {step === "edit" && renderEditStep()}
        {step === "corpus" && !corpusId && renderCorpusStep()}
        {step === "uploading" && renderUploadingStep()}
      </Modal.Content>
      <Modal.Actions>
        <Button basic color="grey" onClick={() => onClose()}>
          <Icon name="remove" /> Close
        </Button>
        {step === "upload" && files.length > 0 && (
          <Button color="green" inverted onClick={() => setStep("edit")}>
            <Icon name="checkmark" /> Next
          </Button>
        )}
        {step === "edit" && (
          <>
            <Button color="grey" inverted onClick={() => setStep("upload")}>
              <Icon name="arrow left" /> Back
            </Button>
            {corpusId ? (
              <Button color="green" inverted onClick={() => uploadFiles()}>
                <Icon name="checkmark" /> Upload
              </Button>
            ) : (
              <>
                <Button color="blue" inverted onClick={() => uploadFiles()}>
                  <Icon name="arrow right" /> Skip
                </Button>
                <Button
                  color="green"
                  inverted
                  onClick={() => setStep("corpus")}
                >
                  <Icon name="checkmark" /> Next
                </Button>
              </>
            )}
          </>
        )}
        {step === "corpus" && !corpusId && (
          <>
            <Button color="grey" inverted onClick={() => setStep("edit")}>
              <Icon name="arrow left" /> Back
            </Button>
            <Button color="blue" inverted onClick={() => uploadFiles()}>
              <Icon name="arrow right" /> Skip
            </Button>
            <Button color="green" inverted onClick={() => uploadFiles()}>
              <Icon name="checkmark" /> Upload
            </Button>
          </>
        )}
      </Modal.Actions>
    </Modal>
  );
}
