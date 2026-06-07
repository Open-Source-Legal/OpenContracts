- **Deleting a folder now removes its whole sub-tree and moves the documents to
  Trash instead of stranding sub-folders at the corpus root.** Previously the
  folder-delete UI reparented sub-folders to the grandparent and moved only the
  top folder's direct documents to root, so emptying the trash never cleared the
  orphaned sub-folders. `FolderCRUDService.delete_folder`
  (`opencontractserver/corpuses/services/folders.py`) now, when
  `move_children_to_parent=False` (the `deleteContents=True` path the UI uses),
  soft-deletes every document in the folder and all of its descendants (reusing
  `Corpus.remove_document`, so they stay restorable) and then cascade-deletes the
  folder sub-tree. The reparent branch (`move_children_to_parent=True`) is
  unchanged; its document-relocation logic was extracted verbatim into
  `_relocate_folder_documents_to_root`. `DeleteFolderModal` now sends
  `deleteContents: true` and its confirmation copy reflects the Trash behavior.
