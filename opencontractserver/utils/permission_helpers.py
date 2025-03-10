def user_has_effective_permission(user, obj, perm_codename):
    """
    Check if a user has effective permission on an object by:
    1. Checking direct object permission
    2. If not found, checking parent corpus permission
    3. If not found, checking public/creator status

    This avoids permission propagation entirely.
    """
    from guardian.shortcuts import get_perms

    # Superuser always has permission
    if user.is_authenticated and user.is_superuser:
        return True

    # 1. Check direct object permission
    if perm_codename in get_perms(user, obj):
        return True

    # 2. Check corpus inheritance if applicable
    corpus = getattr(obj, "corpus", None)
    if corpus:
        corpus_perm = perm_codename.split("_")[0] + "_corpus"  # e.g., 'view_corpus'
        if corpus_perm in get_perms(user, corpus):
            return True

    # 3. Check public status or creator ownership
    if getattr(obj, "is_public", False):
        return True

    if user.is_authenticated and getattr(obj, "creator", None) == user:
        return True

    return False
