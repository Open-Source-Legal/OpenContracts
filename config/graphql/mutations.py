"""
GraphQL mutation composition for the OpenContracts platform.

This module imports mutation classes from domain-specific modules and
composes them into the root Mutation class used by the GraphQL schema.
"""

import graphene
import graphql_jwt
from django.conf import settings

# Import agent mutations
from config.graphql.agent_mutations import (
    CreateAgentConfigurationMutation,
    DeleteAgentConfigurationMutation,
    UpdateAgentConfigurationMutation,
)

# Import analysis mutations
from config.graphql.analysis_mutations import (
    DeleteAnalysisMutation,
    MakeAnalysisPublic,
    StartDocumentAnalysisMutation,
)

# Import annotation mutations
from config.graphql.annotation_mutations import (
    AddAnnotation,
    AddDocTypeAnnotation,
    AddRelationship,
    ApproveAnnotation,
    CreateNote,
    DeleteNote,
    RejectAnnotation,
    RemoveAnnotation,
    RemoveRelationship,
    RemoveRelationships,
    UpdateAnnotation,
    UpdateNote,
    UpdateRelations,
    UpdateRelationship,
)

# Import badge mutations
from config.graphql.badge_mutations import (
    AwardBadgeMutation,
    CreateBadgeMutation,
    DeleteBadgeMutation,
    RevokeBadgeMutation,
    UpdateBadgeMutation,
)

# Import conversation mutations
from config.graphql.conversation_mutations import (
    CreateThreadMessageMutation,
    CreateThreadMutation,
    DeleteConversationMutation,
    DeleteMessageMutation,
    ReplyToMessageMutation,
    UpdateMessageMutation,
)

# Import corpus folder mutations
from config.graphql.corpus_folder_mutations import (
    CreateCorpusFolderMutation,
    DeleteCorpusFolderMutation,
    MoveCorpusFolderMutation,
    MoveDocumentsToFolderMutation,
    MoveDocumentToFolderMutation,
    UpdateCorpusFolderMutation,
)

# Import corpus mutations
from config.graphql.corpus_mutations import (
    AddDocumentsToCorpus,
    AddTemplateToCorpus,
    CreateCorpusAction,
    CreateCorpusMutation,
    DeleteCorpusAction,
    DeleteCorpusMutation,
    ReEmbedCorpus,
    RemoveDocumentsFromCorpus,
    RunCorpusAction,
    SetCorpusVisibility,
    StartCorpusFork,
    ToggleCorpusMemory,
    UpdateCorpusAction,
    UpdateCorpusDescription,
    UpdateCorpusMutation,
)

# Import document mutations
from config.graphql.document_mutations import (
    DeleteDocument,
    DeleteExport,
    DeleteMultipleDocuments,
    EmptyTrash,
    ImportZipToCorpus,
    PermanentlyDeleteDocument,
    RestoreDeletedDocument,
    RestoreDocumentToVersion,
    RetryDocumentProcessing,
    StartCorpusExport,
    UpdateDocument,
    UpdateDocumentSummary,
    UploadAnnotatedDocument,
    UploadCorpusImportZip,
    UploadDocument,
    UploadDocumentsZip,
)

# Import document relationship mutations
from config.graphql.document_relationship_mutations import (
    CreateDocumentRelationship,
    DeleteDocumentRelationship,
    DeleteDocumentRelationships,
    UpdateDocumentRelationship,
)

# Import extract mutations
from config.graphql.extract_mutations import (
    AddDocumentsToExtract,
    ApproveDatacell,
    CreateColumn,
    CreateExtract,
    CreateExtractIteration,
    CreateFieldset,
    CreateMetadataColumn,
    DeleteColumn,
    DeleteExtract,
    DeleteMetadataValue,
    EditDatacell,
    RejectDatacell,
    RemoveDocumentsFromExtract,
    SetMetadataValue,
    StartDocumentExtract,
    StartExtract,
    UpdateColumnMutation,
    UpdateExtractMutation,
    UpdateMetadataColumn,
)

# Import ingestion source mutations
from config.graphql.ingestion_source_mutations import (
    CreateIngestionSourceMutation,
    DeleteIngestionSourceMutation,
    UpdateIngestionSourceMutation,
)

# Import label mutations
from config.graphql.label_mutations import (
    CreateLabelForLabelsetMutation,
    CreateLabelMutation,
    CreateLabelset,
    DeleteLabelMutation,
    DeleteLabelset,
    DeleteMultipleLabelMutation,
    RemoveLabelsFromLabelsetMutation,
    UpdateLabelMutation,
    UpdateLabelset,
)

# Import moderation mutations
from config.graphql.moderation_mutations import (
    AddModeratorMutation,
    DeleteThreadMutation,
    LockThreadMutation,
    PinThreadMutation,
    RemoveModeratorMutation,
    RestoreThreadMutation,
    RollbackModerationActionMutation,
    UnlockThreadMutation,
    UnpinThreadMutation,
    UpdateModeratorPermissionsMutation,
)

# Import notification mutations
from config.graphql.notification_mutations import (
    DeleteNotificationMutation,
    MarkAllNotificationsReadMutation,
    MarkNotificationReadMutation,
    MarkNotificationUnreadMutation,
)

# Import pipeline settings mutations
from config.graphql.pipeline_settings_mutations import (
    DeleteComponentSecretsMutation,
    DeleteToolSecretsMutation,
    ResetPipelineSettingsMutation,
    UpdateComponentSecretsMutation,
    UpdatePipelineSettingsMutation,
    UpdateToolSecretsMutation,
)

# Import smart label mutations
from config.graphql.smart_label_mutations import (
    SmartLabelListMutation,
    SmartLabelSearchOrCreateMutation,
)

# Import user mutations
from config.graphql.user_mutations import (
    AcceptCookieConsent,
    DismissGettingStarted,
    ObtainJSONWebTokenWithUser,
    UpdateMe,
)

# Import voting mutations
from config.graphql.voting_mutations import (
    RemoveConversationVoteMutation,
    RemoveVoteMutation,
    VoteConversationMutation,
    VoteMessageMutation,
)

# Import worker mutations
from config.graphql.worker_mutations import (
    CreateCorpusAccessTokenMutation,
    CreateWorkerAccount,
    DeactivateWorkerAccount,
    ReactivateWorkerAccount,
    RevokeCorpusAccessTokenMutation,
)


class Mutation(graphene.ObjectType):
    # TOKEN MUTATIONS (IF WE'RE NOT OUTSOURCING JWT CREATION TO AUTH0) #######
    if not settings.USE_AUTH0:
        token_auth = ObtainJSONWebTokenWithUser.Field()
    else:
        token_auth = graphql_jwt.ObtainJSONWebToken.Field()

    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()

    # ANNOTATION MUTATIONS ######################################################
    add_annotation = AddAnnotation.Field()
    remove_annotation = RemoveAnnotation.Field()
    update_annotation = UpdateAnnotation.Field()
    add_doc_type_annotation = AddDocTypeAnnotation.Field()
    remove_doc_type_annotation = RemoveAnnotation.Field()
    approve_annotation = ApproveAnnotation.Field()
    reject_annotation = RejectAnnotation.Field()

    # RELATIONSHIP MUTATIONS #####################################################
    add_relationship = AddRelationship.Field()
    remove_relationship = RemoveRelationship.Field()
    remove_relationships = RemoveRelationships.Field()
    update_relationship = UpdateRelationship.Field()
    update_relationships = UpdateRelations.Field()

    # DOCUMENT RELATIONSHIP MUTATIONS ############################################
    create_document_relationship = CreateDocumentRelationship.Field()
    update_document_relationship = UpdateDocumentRelationship.Field()
    delete_document_relationship = DeleteDocumentRelationship.Field()
    delete_document_relationships = DeleteDocumentRelationships.Field()

    # LABELSET MUTATIONS #######################################################
    create_labelset = CreateLabelset.Field()
    update_labelset = UpdateLabelset.Field()
    delete_labelset = DeleteLabelset.Field()

    # LABEL MUTATIONS ##########################################################
    create_annotation_label = CreateLabelMutation.Field()
    update_annotation_label = UpdateLabelMutation.Field()
    delete_annotation_label = DeleteLabelMutation.Field()
    delete_multiple_annotation_labels = DeleteMultipleLabelMutation.Field()
    create_annotation_label_for_labelset = CreateLabelForLabelsetMutation.Field()
    remove_annotation_labels_from_labelset = RemoveLabelsFromLabelsetMutation.Field()

    # SMART LABEL MUTATIONS (search/create with auto labelset management)
    smart_label_search_or_create = SmartLabelSearchOrCreateMutation.Field()
    smart_label_list = SmartLabelListMutation.Field()

    # DOCUMENT MUTATIONS #######################################################
    upload_document = UploadDocument.Field()  # Limited by user.is_usage_capped
    update_document = UpdateDocument.Field()
    update_document_summary = UpdateDocumentSummary.Field()
    delete_document = DeleteDocument.Field()
    delete_multiple_documents = DeleteMultipleDocuments.Field()
    upload_documents_zip = UploadDocumentsZip.Field()  # Bulk document upload via zip
    retry_document_processing = (
        RetryDocumentProcessing.Field()
    )  # Retry failed documents

    # DOCUMENT VERSIONING MUTATIONS ############################################
    restore_deleted_document = RestoreDeletedDocument.Field()
    restore_document_to_version = RestoreDocumentToVersion.Field()
    permanently_delete_document = PermanentlyDeleteDocument.Field()
    empty_trash = EmptyTrash.Field()

    # CORPUS MUTATIONS #########################################################
    fork_corpus = StartCorpusFork.Field()
    re_embed_corpus = ReEmbedCorpus.Field()
    set_corpus_visibility = SetCorpusVisibility.Field()
    create_corpus = CreateCorpusMutation.Field()
    update_corpus = UpdateCorpusMutation.Field()
    update_me = UpdateMe.Field()
    update_corpus_description = UpdateCorpusDescription.Field()
    delete_corpus = DeleteCorpusMutation.Field()
    link_documents_to_corpus = AddDocumentsToCorpus.Field()
    remove_documents_from_corpus = RemoveDocumentsFromCorpus.Field()
    create_corpus_action = CreateCorpusAction.Field()
    update_corpus_action = UpdateCorpusAction.Field()
    delete_corpus_action = DeleteCorpusAction.Field()
    run_corpus_action = RunCorpusAction.Field()
    add_template_to_corpus = AddTemplateToCorpus.Field()
    toggle_corpus_memory = ToggleCorpusMemory.Field()

    # CORPUS FOLDER MUTATIONS ##################################################
    create_corpus_folder = CreateCorpusFolderMutation.Field()
    update_corpus_folder = UpdateCorpusFolderMutation.Field()
    move_corpus_folder = MoveCorpusFolderMutation.Field()
    delete_corpus_folder = DeleteCorpusFolderMutation.Field()
    move_document_to_folder = MoveDocumentToFolderMutation.Field()
    move_documents_to_folder = MoveDocumentsToFolderMutation.Field()

    # IMPORT MUTATIONS #########################################################
    import_open_contracts_zip = UploadCorpusImportZip.Field()
    import_annotated_doc_to_corpus = UploadAnnotatedDocument.Field()
    import_zip_to_corpus = (
        ImportZipToCorpus.Field()
    )  # Bulk import with folder structure

    # EXPORT MUTATIONS #########################################################
    export_corpus = StartCorpusExport.Field()  # Limited by user.is_usage_capped
    delete_export = DeleteExport.Field()

    # USER PREFERENCE MUTATIONS #################################################
    accept_cookie_consent = AcceptCookieConsent.Field()
    dismiss_getting_started = DismissGettingStarted.Field()

    # ANALYSIS MUTATIONS #########################################################
    start_analysis_on_doc = StartDocumentAnalysisMutation.Field()
    delete_analysis = DeleteAnalysisMutation.Field()
    make_analysis_public = MakeAnalysisPublic.Field()

    # EXTRACT MUTATIONS ##########################################################
    create_fieldset = CreateFieldset.Field()

    create_column = CreateColumn.Field()
    update_column = UpdateColumnMutation.Field()
    delete_column = DeleteColumn.Field()

    create_extract = CreateExtract.Field()
    create_extract_iteration = CreateExtractIteration.Field()
    start_extract = StartExtract.Field()
    delete_extract = DeleteExtract.Field()
    update_extract = UpdateExtractMutation.Field()
    add_docs_to_extract = AddDocumentsToExtract.Field()
    remove_docs_from_extract = RemoveDocumentsFromExtract.Field()
    approve_datacell = ApproveDatacell.Field()
    reject_datacell = RejectDatacell.Field()
    edit_datacell = EditDatacell.Field()
    start_extract_for_doc = StartDocumentExtract.Field()
    update_note = UpdateNote.Field()
    delete_note = DeleteNote.Field()
    create_note = CreateNote.Field()

    # NEW METADATA MUTATIONS (Column/Datacell based) ################################
    create_metadata_column = CreateMetadataColumn.Field()
    update_metadata_column = UpdateMetadataColumn.Field()
    set_metadata_value = SetMetadataValue.Field()
    delete_metadata_value = DeleteMetadataValue.Field()

    # BADGE MUTATIONS #############################################################
    create_badge = CreateBadgeMutation.Field()
    update_badge = UpdateBadgeMutation.Field()
    delete_badge = DeleteBadgeMutation.Field()
    award_badge = AwardBadgeMutation.Field()
    revoke_badge = RevokeBadgeMutation.Field()

    # CONVERSATION/THREAD MUTATIONS ##############################################
    create_thread = CreateThreadMutation.Field()
    create_thread_message = CreateThreadMessageMutation.Field()
    reply_to_message = ReplyToMessageMutation.Field()
    update_message = UpdateMessageMutation.Field()
    delete_conversation = DeleteConversationMutation.Field()
    delete_message = DeleteMessageMutation.Field()

    # MODERATION MUTATIONS #######################################################
    lock_thread = LockThreadMutation.Field()
    unlock_thread = UnlockThreadMutation.Field()
    pin_thread = PinThreadMutation.Field()
    unpin_thread = UnpinThreadMutation.Field()
    delete_thread = DeleteThreadMutation.Field()
    restore_thread = RestoreThreadMutation.Field()
    add_moderator = AddModeratorMutation.Field()
    remove_moderator = RemoveModeratorMutation.Field()
    update_moderator_permissions = UpdateModeratorPermissionsMutation.Field()
    rollback_moderation_action = RollbackModerationActionMutation.Field()

    # VOTING MUTATIONS ###########################################################
    vote_message = VoteMessageMutation.Field()
    remove_vote = RemoveVoteMutation.Field()
    vote_conversation = VoteConversationMutation.Field()
    remove_conversation_vote = RemoveConversationVoteMutation.Field()

    # NOTIFICATION MUTATIONS #####################################################
    mark_notification_read = MarkNotificationReadMutation.Field()
    mark_notification_unread = MarkNotificationUnreadMutation.Field()
    mark_all_notifications_read = MarkAllNotificationsReadMutation.Field()
    delete_notification = DeleteNotificationMutation.Field()

    # AGENT CONFIGURATION MUTATIONS ##############################################
    create_agent_configuration = CreateAgentConfigurationMutation.Field()
    update_agent_configuration = UpdateAgentConfigurationMutation.Field()
    delete_agent_configuration = DeleteAgentConfigurationMutation.Field()

    # INGESTION SOURCE MUTATIONS ###################################################
    create_ingestion_source = CreateIngestionSourceMutation.Field()
    update_ingestion_source = UpdateIngestionSourceMutation.Field()
    delete_ingestion_source = DeleteIngestionSourceMutation.Field()

    # PIPELINE SETTINGS MUTATIONS (Superuser only) ###############################
    update_pipeline_settings = UpdatePipelineSettingsMutation.Field()
    reset_pipeline_settings = ResetPipelineSettingsMutation.Field()
    update_component_secrets = UpdateComponentSecretsMutation.Field()
    delete_component_secrets = DeleteComponentSecretsMutation.Field()
    update_tool_secrets = UpdateToolSecretsMutation.Field()
    delete_tool_secrets = DeleteToolSecretsMutation.Field()

    # WORKER UPLOAD MUTATIONS ########################################################
    create_worker_account = CreateWorkerAccount.Field()
    deactivate_worker_account = DeactivateWorkerAccount.Field()
    reactivate_worker_account = ReactivateWorkerAccount.Field()
    create_corpus_access_token = CreateCorpusAccessTokenMutation.Field()
    revoke_corpus_access_token = RevokeCorpusAccessTokenMutation.Field()
