/**
 * The single frontend authority-admin gate, mirroring the backend
 * ``is_authority_admin``. Returns ``ready=false`` while the ``backendUserObj``
 * reactive var is still loading (``null``) so the console never flashes an
 * "Access Denied" warning for an admin mid-load — the same wait-on-null pattern
 * the existing authority panels use. Widen the role here (and in the backend
 * ``authority_permissions`` peer) when a finer-grained law-librarian role lands.
 */
import { useReactiveVar } from "@apollo/client";

import { backendUserObj } from "../../../../graphql/cache";

export interface AuthorityAdminState {
  /** True once the reactive var has resolved (admin or not). */
  ready: boolean;
  /** True iff the current user may administer authority data. */
  isAdmin: boolean;
}

export function useIsAuthorityAdmin(): AuthorityAdminState {
  const currentUser = useReactiveVar(backendUserObj);
  if (currentUser === null) {
    return { ready: false, isAdmin: false };
  }
  return { ready: true, isAdmin: currentUser?.isSuperuser === true };
}
