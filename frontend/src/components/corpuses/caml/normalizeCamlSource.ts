/**
 * CAML source normalization — repair stray top-level block fences before parsing.
 *
 * WHY THIS EXISTS
 * ---------------
 * `@os-legal/caml`'s tokenizer is depth-specific: the document body is scanned
 * for depth-3 (`:::`) fences, and only a chapter's *interior* is scanned for
 * depth-4 (`::::`) block fences. A `:::: <block>` fence written at the top level
 * (with no enclosing `::: chapter`) can never be closed by the depth-3
 * tokenizer — the `::::` close line fails its `^:{3}\s*$` close pattern — so the
 * parser's unclosed-fence recovery re-emits the block body *and the literal
 * `::::`* as a prose token. The result renders as a stray markdown bullet list
 * with a dangling `::::`. The canonical symptom is the `corpus-stats` block:
 *
 *     :::: corpus-stats
 *     - documents | Documents
 *     - annotations | Annotations
 *     ::::
 *
 * leaking to screen as "• documents | Documents" / "• annotations | Annotations
 * ::::".
 *
 * The backend CAML authoring guide presents every block example as a bare
 * `::::` fence, so LLM-authored `Readme.CAML` articles frequently emit blocks at
 * the top level. Rather than fork the pinned parser, we wrap any run of stray
 * top-level `::::`+ fences (plus the prose between them) in a synthetic
 * `::: chapter`, which the parser then tokenizes correctly. The transform is a
 * no-op on correctly-nested input and is idempotent (re-running on its own
 * output changes nothing). Top-level *depth-3* blocks (`::: cards`) are already
 * handled by the parser — it wraps them in an implicit chapter — and are left
 * untouched.
 *
 * This runs at render time (the only place CAML is parsed) so it repairs
 * already-stored articles as well as new ones; it pairs with the backend
 * prompt hardening that reduces the rate of mis-nested output at the source.
 */
import { parseCaml } from "@os-legal/caml";
import type { CamlDocument } from "@os-legal/caml";

/** Header of a fence line: 3+ leading colons, then the (possibly empty) rest. */
const FENCE_RE = /^(:{3,})(.*)$/;

/** Splits YAML frontmatter from the body exactly as the parser does, so the
 *  normalizer never touches frontmatter content. */
const FRONTMATTER_RE = /^(---[ \t]*\n[\s\S]*?\n---[ \t]*\n)([\s\S]*)$/;

const SYNTHETIC_CHAPTER_OPEN = "::: chapter";
const SYNTHETIC_CHAPTER_CLOSE = ":::";

/**
 * Wrap stray top-level `::::`+ block fences in a synthetic `::: chapter` so the
 * upstream parser recognises them as blocks instead of leaking them as prose.
 *
 * Pure function, no side effects. Returns `source` unchanged when there is no
 * depth-4 fence to rescue or when the input is already well nested.
 */
export function normalizeCamlSource(source: string): string {
  // Fast path: a depth-4 fence is a prerequisite for the bug, so if the source
  // contains no `::::` anywhere there is nothing to wrap.
  if (!source || !source.includes("::::")) return source;

  const fmMatch = source.match(FRONTMATTER_RE);
  const head = fmMatch ? fmMatch[1] : "";
  const body = fmMatch ? fmMatch[2] : source;

  const lines = body.split("\n");
  const out: string[] = [];

  // True while inside a real depth-3 region — a `::: chapter` or a top-level
  // `::: <block>`. Depth-4 fences nested inside such a region are valid and
  // pass through untouched.
  let inDepth3 = false;
  // True while we are adopting a run of stray top-level `::::`+ fences into a
  // synthetic chapter we opened.
  let wrapping = false;

  const closeWrap = () => {
    if (wrapping) {
      out.push(SYNTHETIC_CHAPTER_CLOSE);
      wrapping = false;
    }
  };

  for (const line of lines) {
    const fence = line.trim().match(FENCE_RE);

    if (!fence) {
      // Non-fence line: prose either passes through or is carried inside the
      // synthetic wrapper we are currently building.
      out.push(line);
      continue;
    }

    const colons = fence[1].length;
    const rest = fence[2].trim();

    if (colons === 3) {
      if (rest === "") {
        // A bare `:::` closes an open depth-3 region; at the top level the
        // parser ignores it, so we only flip state when one is open.
        if (inDepth3) inDepth3 = false;
        out.push(line);
        continue;
      }
      // `::: <type>` opens a real depth-3 region (chapter or top-level block).
      // A real region supersedes any synthetic wrapper in progress.
      closeWrap();
      inDepth3 = true;
      out.push(line);
      continue;
    }

    // colons >= 4: a block fence (open or close line).
    if (inDepth3) {
      // Correctly nested inside a depth-3 region — leave as-is.
      out.push(line);
      continue;
    }

    // Stray top-level block fence: open a synthetic chapter to adopt it.
    if (!wrapping) {
      out.push(SYNTHETIC_CHAPTER_OPEN);
      wrapping = true;
    }
    out.push(line);
  }

  closeWrap();

  return head + out.join("\n");
}

/**
 * Parse a CAML article, repairing stray top-level block fences first.
 *
 * Drop-in replacement for `parseCaml()` for article sources (corpus
 * `Readme.CAML`). Use this instead of the raw parser anywhere an article body
 * authored by a user or an LLM is rendered.
 */
export function parseCamlArticle(source: string): CamlDocument {
  return parseCaml(normalizeCamlSource(source));
}
