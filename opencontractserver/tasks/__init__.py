from .agent_tasks import generate_agent_response, trigger_agent_responses_for_message
from .badge_tasks import check_auto_badges, check_badges_for_all_users
from .cleanup_tasks import (
    cleanup_orphaned_document_blobs_task,
    delete_analysis_and_annotations_task,
)
from .corpus_tasks import *  # noqa: F403, F401
from .data_extract_tasks import *  # noqa: F403, F401
from .doc_analysis_tasks import *  # noqa: F403, F401
from .doc_tasks import burn_doc_annotations
from .export_tasks import package_annotated_docs
from .extract_orchestrator_tasks import run_extract
from .fork_tasks import fork_corpus
from .import_tasks import (
    import_corpus,
    import_document_to_corpus,
    import_zip_with_folder_structure,
    process_documents_zip,
)
from .lookup_tasks import build_label_lookups_task
from .memory_tasks import check_conversations_for_curation, curate_corpus_memory

# Materialized view tasks removed - using direct queries instead
from .permissioning_tasks import make_analysis_public_task, make_corpus_public_task
from .research_tasks import reap_stalled_research, run_deep_research
from .stats_tasks import refresh_system_stats
from .telemetry_tasks import send_usage_heartbeat

# Great, quick guidance on how to restructure tasks into multiple modules:
# https://blog.sneawo.com/blog/2018/12/05/how-to-split-celery-tasks-file/
#
# A good idea is to split it on the smaller files, but Celery auto_discover
# by default search tasks in package.tasks

__all__ = [
    "run_extract",
    "package_annotated_docs",
    "burn_doc_annotations",
    "fork_corpus",
    "build_label_lookups_task",
    "import_corpus",
    "import_document_to_corpus",
    "import_zip_with_folder_structure",
    "process_documents_zip",
    "make_corpus_public_task",
    "make_analysis_public_task",
    "delete_analysis_and_annotations_task",
    "cleanup_orphaned_document_blobs_task",
    "check_auto_badges",
    "check_badges_for_all_users",
    "generate_agent_response",
    "trigger_agent_responses_for_message",
    "send_usage_heartbeat",
    "refresh_system_stats",
    "run_deep_research",
    "reap_stalled_research",
    "check_conversations_for_curation",
    "curate_corpus_memory",
]
