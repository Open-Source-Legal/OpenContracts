import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { persistentVar } from "../persistentVar";

describe("persistentVar", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it("uses the default value when nothing is stored", () => {
    const rv = persistentVar<number>("persistent.counter", 7);
    expect(rv()).toBe(7);
  });

  it("hydrates from sessionStorage when a value exists", () => {
    sessionStorage.setItem("persistent.saved", JSON.stringify({ n: 3 }));
    const rv = persistentVar<{ n: number }>("persistent.saved", { n: 0 });
    expect(rv()).toEqual({ n: 3 });
  });

  it("persists changes back to sessionStorage", () => {
    const rv = persistentVar<string>("persistent.text", "initial");
    rv("updated");
    expect(sessionStorage.getItem("persistent.text")).toBe(
      JSON.stringify("updated")
    );
  });

  it("removes the storage entry when value is set to null or undefined", () => {
    sessionStorage.setItem("persistent.clearable", JSON.stringify("keep"));
    const rv = persistentVar<string | null>("persistent.clearable", "keep");
    rv(null);
    expect(sessionStorage.getItem("persistent.clearable")).toBeNull();
  });

  it("falls back to default value on malformed stored JSON", () => {
    sessionStorage.setItem("persistent.bad", "{not json");
    const rv = persistentVar<string>("persistent.bad", "fallback");
    expect(rv()).toBe("fallback");
  });

  it("treats literal 'undefined' and 'null' strings as missing", () => {
    sessionStorage.setItem("persistent.undef", "undefined");
    const rv = persistentVar<string>("persistent.undef", "default");
    expect(rv()).toBe("default");

    sessionStorage.setItem("persistent.nul", "null");
    const rv2 = persistentVar<string>("persistent.nul", "default");
    expect(rv2()).toBe("default");
  });
});
