import { useState, useEffect } from "react";
import { MentionUser } from "../MentionPicker";

/**
 * Hook to fetch users for @mention autocomplete
 *
 * TODO: Replace with real GraphQL query when backend supports user search
 * For now, returns mock users for demonstration purposes
 */
export function useMentionUsers(query: string): MentionUser[] {
  const [users, setUsers] = useState<MentionUser[]>([]);

  useEffect(() => {
    // Mock users - in production, this would be a GraphQL query
    const mockUsers: MentionUser[] = [
      { id: "1", username: "admin", email: "admin@example.com" },
      { id: "2", username: "moderator", email: "moderator@example.com" },
      { id: "3", username: "analyst", email: "analyst@example.com" },
      { id: "4", username: "reviewer", email: "reviewer@example.com" },
      { id: "5", username: "contributor", email: "contributor@example.com" },
    ];

    // Filter users based on query
    const filtered = query
      ? mockUsers.filter(
          (user) =>
            user.username.toLowerCase().includes(query.toLowerCase()) ||
            user.email?.toLowerCase().includes(query.toLowerCase())
        )
      : mockUsers;

    setUsers(filtered.slice(0, 5)); // Limit to 5 results
  }, [query]);

  return users;
}
