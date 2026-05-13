import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Allow only protocols that cannot execute script. react-markdown 10.x's
 * default `urlTransform` already strips `javascript:` and most `data:` URIs,
 * but we pin the contract here so the safety story doesn't quietly regress
 * if the upstream default ever changes. User-authored markdown (profile
 * fields, corpus descriptions, agent output) flows through this component,
 * so the allowlist is intentionally narrow.
 */
const SAFE_PROTOCOLS = /^(https?:|mailto:|tel:)/i;

function urlTransform(url: string): string {
  // Treat empty / fragment-only / relative URLs as safe.
  //
  // We intentionally pass through absolute in-app paths like ``/settings``
  // unchanged. There is no XSS vector (no protocol means no js: / data:
  // execution) and rewriting them would break legitimate cross-page links
  // inside the same SPA. The accepted trade-off: a profile author can craft
  // in-app phishing links (e.g. ``/admin``) just like they can in any free-
  // text field. This is *not* a license to broaden the allowlist later —
  // anything carrying a ``:`` must still match SAFE_PROTOCOLS.
  //
  // Protocol-relative URLs (``//example.com``) MUST be rejected here —
  // browsers resolve them to the page's protocol, so on an HTTPS page
  // ``[click](//phishing.example)`` would render as a live external link
  // disguised as a relative path. Strip the leading slash and hand off to
  // SAFE_PROTOCOLS, which requires an explicit ``http(s):`` / ``mailto:`` /
  // ``tel:`` to pass.
  if (!url || url.startsWith("#")) return url;
  if (url.startsWith("/") && !url.startsWith("//")) return url;
  return SAFE_PROTOCOLS.test(url) ? url : "";
}

export const SafeMarkdown: React.FC<{ children: string }> = ({ children }) => {
  try {
    return (
      <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={urlTransform}>
        {children}
      </ReactMarkdown>
    );
  } catch (error) {
    console.warn(
      "Failed to render with remarkGfm, falling back to basic markdown:",
      error
    );
    return (
      <ReactMarkdown urlTransform={urlTransform}>{children}</ReactMarkdown>
    );
  }
};
