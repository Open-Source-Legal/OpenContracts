import { describe, it, expect } from "vitest";
import { renderHook, act } from "../../test-utils/renderHook";
import { useAgentMentionTrigger } from "../useAgentMentionTrigger";

describe("useAgentMentionTrigger", () => {
  it("opens on typed @ followed by a letter", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    act(() => {
      result.current.onValueChange("hello @r", 8);
    });
    expect(result.current.isOpen).toBe(true);
    expect(result.current.fragment).toBe("r");
  });

  it("opens immediately after typing just '@'", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    act(() => {
      result.current.onValueChange("hello @", 7);
    });
    expect(result.current.isOpen).toBe(true);
    expect(result.current.fragment).toBe("");
  });

  it("closes when caret leaves the trigger fragment", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    act(() => result.current.onValueChange("hello @r", 8));
    expect(result.current.isOpen).toBe(true);
    // User moves caret elsewhere (after "world")
    act(() => result.current.onValueChange("hello @r world", 14));
    expect(result.current.isOpen).toBe(false);
  });

  it("closes on space without a selection", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    act(() => result.current.onValueChange("hello @r ", 9));
    expect(result.current.isOpen).toBe(false);
  });

  it("only triggers when @ is at start-of-text or after whitespace", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    // Email-like: @ follows a letter, should NOT trigger
    act(() => result.current.onValueChange("email@foo", 9));
    expect(result.current.isOpen).toBe(false);
  });

  it("triggers when @ is the very first character", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    act(() => result.current.onValueChange("@res", 4));
    expect(result.current.isOpen).toBe(true);
    expect(result.current.fragment).toBe("res");
  });

  it("onSelect returns the new text with the markdown link inserted", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    act(() => result.current.onValueChange("hello @res", 10));
    let returned;
    act(() => {
      returned = result.current.onSelect({
        slug: "research-bot",
        name: "Research Bot",
        url: "/agents/research-bot",
      });
    });
    expect(returned).toEqual({
      value: "hello [@research-bot](/agents/research-bot) ",
      caretPos: "hello [@research-bot](/agents/research-bot) ".length,
    });
  });

  it("onDismiss closes immediately", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    act(() => result.current.onValueChange("hello @r", 8));
    expect(result.current.isOpen).toBe(true);
    act(() => result.current.onDismiss());
    expect(result.current.isOpen).toBe(false);
  });

  it("isOpen is false initially", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    expect(result.current.isOpen).toBe(false);
    expect(result.current.fragment).toBe("");
  });

  it("preserves text after the caret on selection", () => {
    const { result } = renderHook(() => useAgentMentionTrigger());
    // User types "@res" with their caret in the middle of "hello world"
    act(() => result.current.onValueChange("hello @res world", 10));
    let returned;
    act(() => {
      returned = result.current.onSelect({
        slug: "research-bot",
        name: "Research Bot",
        url: "/agents/research-bot",
      });
    });
    expect(returned).toEqual({
      value: "hello [@research-bot](/agents/research-bot)  world",
      caretPos: "hello [@research-bot](/agents/research-bot) ".length,
    });
  });
});
