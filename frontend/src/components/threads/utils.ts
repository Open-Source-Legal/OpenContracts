import { ChatMessageType } from "../../types/graphql-api";

/**
 * Extended message node with children and depth for tree rendering
 */
export interface MessageNode extends ChatMessageType {
  children: MessageNode[];
  depth: number;
}

/**
 * Builds a hierarchical message tree from flat list of messages
 * Handles nested replies up to maxDepth levels
 *
 * @param messages - Flat array of messages
 * @param maxDepth - Maximum nesting depth (default 10)
 * @returns Array of root-level message nodes with children
 */
export function buildMessageTree(
  messages: ChatMessageType[],
  maxDepth: number = 10
): MessageNode[] {
  if (!messages || messages.length === 0) {
    return [];
  }

  // Create map of message ID to message with children array
  const messageMap = new Map<string, MessageNode>();

  messages.forEach((msg) => {
    messageMap.set(msg.id, {
      ...msg,
      children: [],
      depth: 0,
    });
  });

  // Build tree by linking children to parents
  const rootMessages: MessageNode[] = [];

  // Sort by creation time to maintain chronological order
  const sortedMessages = [...messages].sort(
    (a, b) => new Date(a.created).getTime() - new Date(b.created).getTime()
  );

  sortedMessages.forEach((msg) => {
    const node = messageMap.get(msg.id);
    if (!node) return;

    if (msg.parentMessage?.id) {
      const parent = messageMap.get(msg.parentMessage.id);
      if (parent) {
        // Set depth, capping at maxDepth
        node.depth = Math.min(parent.depth + 1, maxDepth);
        parent.children.push(node);
      } else {
        // Parent not found (might be deleted), treat as root
        rootMessages.push(node);
      }
    } else {
      // Top-level message
      rootMessages.push(node);
    }
  });

  return rootMessages;
}

/**
 * Flattens message tree back to array (for searching/filtering)
 */
export function flattenMessageTree(nodes: MessageNode[]): MessageNode[] {
  const result: MessageNode[] = [];

  function traverse(node: MessageNode) {
    result.push(node);
    node.children.forEach(traverse);
  }

  nodes.forEach(traverse);
  return result;
}

/**
 * Finds a message node by ID in the tree
 */
export function findMessageInTree(
  nodes: MessageNode[],
  messageId: string
): MessageNode | null {
  for (const node of nodes) {
    if (node.id === messageId) {
      return node;
    }
    const found = findMessageInTree(node.children, messageId);
    if (found) {
      return found;
    }
  }
  return null;
}

/**
 * Calculates total upvotes for a thread (sum of all message upvotes)
 */
export function calculateThreadUpvotes(messages: ChatMessageType[]): number {
  return messages.reduce((sum, msg) => sum + (msg.upvoteCount || 0), 0);
}

/**
 * Gets the last activity timestamp for a thread
 * (most recent message creation time)
 */
export function getLastActivityTime(messages: ChatMessageType[]): Date | null {
  if (!messages || messages.length === 0) return null;

  const timestamps = messages
    .map((msg) => new Date(msg.created))
    .sort((a, b) => b.getTime() - a.getTime());

  return timestamps[0];
}
