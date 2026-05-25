import React from "react";
import { MemoryRouter } from "react-router-dom";

import { Footer } from "../src/components/layout/Footer";

/**
 * Minimal harness for the cite Footer CT tests. Wraps the Footer in a
 * MemoryRouter so the internal `<Link to="…">` nodes can render — the
 * Playwright CT root (`playwright/index.tsx`) already provides Jotai,
 * Apollo, and theme, but it deliberately does not mount a router so
 * each test can choose its own routing context.
 */
export const FooterHarness: React.FC = () => (
  <MemoryRouter>
    <Footer />
  </MemoryRouter>
);
