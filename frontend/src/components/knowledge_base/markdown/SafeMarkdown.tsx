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
const SAFE_PROTOCOLS = /^(https?:|mailto:|tel:|#|\/)/i;

function urlTransform(url: string): string {
  // Treat empty / fragment-only / relative URLs as safe.
  if (!url || url.startsWith("#") || url.startsWith("/")) return url;
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
