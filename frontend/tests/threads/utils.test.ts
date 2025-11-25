import { test, expect } from "@playwright/test";
import {
  buildMessageTree,
  flattenMessageTree,
  findMessageInTree,
} from "../../src/components/threads/utils";
import { createMockMessage } from "./utils/mockThreadData";

test.describe("Thread Utils", () => {
  test("buildMessageTree creates correct hierarchy", () => {
    const msg1 = createMockMessage({
      id: "msg-1",
      content: "Root message",
      parentMessage: null,
    });

    const msg2 = createMockMessage({
      id: "msg-2",
      content: "Reply to root",
      parentMessage: { id: "msg-1" } as any,
    });

    const msg3 = createMockMessage({
      id: "msg-3",
      content: "Nested reply",
      parentMessage: { id: "msg-2" } as any,
    });

    const tree = buildMessageTree([msg1, msg2, msg3]);

    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("msg-1");
    expect(tree[0].depth).toBe(0);
    expect(tree[0].children).toHaveLength(1);
    expect(tree[0].children[0].id).toBe("msg-2");
    expect(tree[0].children[0].depth).toBe(1);
    expect(tree[0].children[0].children).toHaveLength(1);
    expect(tree[0].children[0].children[0].id).toBe("msg-3");
    expect(tree[0].children[0].children[0].depth).toBe(2);
  });

  test("buildMessageTree handles multiple root messages", () => {
    const msg1 = createMockMessage({ id: "msg-1", parentMessage: null });
    const msg2 = createMockMessage({ id: "msg-2", parentMessage: null });

    const tree = buildMessageTree([msg1, msg2]);

    expect(tree).toHaveLength(2);
    expect(tree[0].id).toBe("msg-1");
    expect(tree[1].id).toBe("msg-2");
  });

  test("buildMessageTree caps depth at maxDepth", () => {
    const messages = [];
    for (let i = 1; i <= 15; i++) {
      messages.push(
        createMockMessage({
          id: `msg-${i}`,
          parentMessage: i > 1 ? ({ id: `msg-${i - 1}` } as any) : null,
        })
      );
    }

    const tree = buildMessageTree(messages, 10);

    // Flatten to check all depths
    const flatTree = flattenMessageTree(tree);
    const maxDepth = Math.max(...flatTree.map((node) => node.depth));

    expect(maxDepth).toBe(10);
  });

  test("flattenMessageTree returns all messages", () => {
    const msg1 = createMockMessage({ id: "msg-1", parentMessage: null });
    const msg2 = createMockMessage({
      id: "msg-2",
      parentMessage: { id: "msg-1" } as any,
    });
    const msg3 = createMockMessage({
      id: "msg-3",
      parentMessage: { id: "msg-2" } as any,
    });

    const tree = buildMessageTree([msg1, msg2, msg3]);
    const flat = flattenMessageTree(tree);

    expect(flat).toHaveLength(3);
    expect(flat.map((n) => n.id)).toEqual(["msg-1", "msg-2", "msg-3"]);
  });

  test("findMessageInTree locates correct message", () => {
    const msg1 = createMockMessage({ id: "msg-1", parentMessage: null });
    const msg2 = createMockMessage({
      id: "msg-2",
      parentMessage: { id: "msg-1" } as any,
    });
    const msg3 = createMockMessage({
      id: "msg-3",
      parentMessage: { id: "msg-2" } as any,
    });

    const tree = buildMessageTree([msg1, msg2, msg3]);
    const found = findMessageInTree(tree, "msg-3");

    expect(found).not.toBeNull();
    expect(found?.id).toBe("msg-3");
    expect(found?.depth).toBe(2);
  });

  test("findMessageInTree returns null when not found", () => {
    const msg1 = createMockMessage({ id: "msg-1", parentMessage: null });
    const tree = buildMessageTree([msg1]);

    const found = findMessageInTree(tree, "non-existent");
    expect(found).toBeNull();
  });

  test("buildMessageTree handles empty array", () => {
    const tree = buildMessageTree([]);
    expect(tree).toHaveLength(0);
  });

  test("buildMessageTree handles orphaned messages", () => {
    // Message with parent that doesn't exist
    const msg1 = createMockMessage({
      id: "msg-1",
      parentMessage: { id: "non-existent" } as any,
    });

    const tree = buildMessageTree([msg1]);

    // Should treat as root since parent not found
    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("msg-1");
    expect(tree[0].depth).toBe(0);
  });
});
