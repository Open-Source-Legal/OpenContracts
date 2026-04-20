import { describe, it, expect } from "vitest";
import { parseOutputType, parsePydanticModel } from "../parseOutputType";

describe("parseOutputType", () => {
  describe("primitive types", () => {
    it("parses int", () => {
      expect(parseOutputType("int")).toEqual({ type: "number" });
    });

    it("parses float", () => {
      expect(parseOutputType("float")).toEqual({ type: "number" });
    });

    it("parses str", () => {
      expect(parseOutputType("str")).toEqual({ type: "string" });
    });

    it("parses bool", () => {
      expect(parseOutputType("bool")).toEqual({ type: "boolean" });
    });

    it("trims whitespace", () => {
      expect(parseOutputType("  str  ")).toEqual({ type: "string" });
    });
  });

  describe("object types", () => {
    it("parses a single-line object with typed fields", () => {
      expect(parseOutputType("name: str")).toEqual({
        type: "object",
        properties: { name: { type: "string" } },
      });
    });

    it("parses a multi-line object with mixed primitives", () => {
      const schema = parseOutputType("age: int\nname: str\nactive: bool");
      expect(schema).toEqual({
        type: "object",
        properties: {
          age: { type: "number" },
          name: { type: "string" },
          active: { type: "boolean" },
        },
      });
    });

    it("skips blank lines", () => {
      const schema = parseOutputType("\nname: str\n\nage: int\n");
      expect(schema).toEqual({
        type: "object",
        properties: {
          name: { type: "string" },
          age: { type: "number" },
        },
      });
    });

    it("defaults unknown types to string", () => {
      const schema = parseOutputType("field: Decimal");
      expect(schema).toEqual({
        type: "object",
        properties: { field: { type: "string" } },
      });
    });
  });

  describe("error cases", () => {
    it("rejects default values", () => {
      expect(() => parseOutputType("name: str = 'foo'")).toThrow(
        /default values/
      );
    });

    it("rejects lines with too many colons", () => {
      expect(() => parseOutputType("a: b: c")).toThrow(/line 1/);
    });

    it("rejects bare primitives that are unknown", () => {
      expect(() => parseOutputType("nonsense")).toThrow(
        /Invalid model or primitive type/
      );
    });
  });
});

describe("parsePydanticModel", () => {
  it("returns an empty list for empty input", () => {
    expect(parsePydanticModel("")).toEqual([]);
  });

  it("skips class declarations and returns typed fields", () => {
    const model = `class Example(BaseModel):\n    name: str\n    age: int`;
    const fields = parsePydanticModel(model);
    expect(fields).toHaveLength(2);
    expect(fields[0].fieldName).toBe("name");
    expect(fields[0].fieldType).toBe("str");
    expect(fields[1].fieldName).toBe("age");
    expect(fields[1].fieldType).toBe("int");
    // id should be a string (Math.random-derived)
    expect(typeof fields[0].id).toBe("string");
  });

  it("ignores blank lines", () => {
    const fields = parsePydanticModel("\n\nname: str\n\n");
    expect(fields).toHaveLength(1);
    expect(fields[0].fieldName).toBe("name");
  });
});
