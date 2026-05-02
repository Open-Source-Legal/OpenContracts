from typing import Any


# This was originally more complex, but I'm keeping it as a standalone, centralized function to be able to update
# file paths globally if desired
def calc_oc_file_path(instance: Any, filename: str, sub_folder: str) -> str:
    return f"uploadfiles/{sub_folder}/{filename}"
