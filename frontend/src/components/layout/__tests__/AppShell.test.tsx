import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "../AppShell";

describe("AppShell", () => {
  it("renders the four shell layers with the expected layout constraints", () => {
    const { container } = render(
      <AppShell
        navMenu={<nav data-testid="nav">nav</nav>}
        footer={<footer data-testid="footer">footer</footer>}
      >
        <main data-testid="content">content</main>
      </AppShell>
    );

    // Outer wrapper: floor at 100vh, no clip, no centering (issue #1558).
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.style.minHeight).toBe("100vh");
    expect(outer.style.height).toBe("");
    expect(outer.style.maxHeight).toBe("");
    expect(outer.style.overflow).toBe("");
    expect(outer.style.justifyContent).toBe("");
    expect(outer.style.display).toBe("flex");
    expect(outer.style.flexDirection).toBe("column");

    // Flex shell: grows inside outer, allows children to shrink.
    const appContainer = container.querySelector(
      "#AppContainer"
    ) as HTMLElement;
    const flexShell = appContainer.parentElement as HTMLElement;
    expect(flexShell.style.flexGrow).toBe("1");
    expect(flexShell.style.minHeight).toBe("0");
    expect(flexShell.style.height).toBe("");
    expect(flexShell.style.maxHeight).toBe("");
    expect(flexShell.style.overflow).toBe("");
    expect(flexShell.style.position).toBe("relative");

    // App container: pushes footer down, no overflow clip.
    expect(appContainer.style.flexGrow).toBe("1");
    expect(appContainer.style.overflow).toBe("");
    expect(appContainer.style.justifyContent).toBe("flex-start");
    expect(appContainer.style.margin).toBe("0px");
    expect(appContainer.style.padding).toBe("0px");
    expect(appContainer.style.minHeight).toBe("0");

    // Footer wrapper: never shrinks, no negative-margin hack.
    const footerWrapper = screen.getByTestId("footer")
      .parentElement as HTMLElement;
    expect(footerWrapper.style.flexShrink).toBe("0");
    expect(footerWrapper.style.position).toBe("relative");
    expect(footerWrapper.style.marginTop).toBe("");

    // Children round-trip
    expect(screen.getByTestId("content")).toHaveTextContent("content");
    expect(screen.getByTestId("nav")).toHaveTextContent("nav");
    expect(screen.getByTestId("footer")).toHaveTextContent("footer");
  });

  it("renders overlays as direct children of the outer wrapper", () => {
    const { container } = render(
      <AppShell
        navMenu={<div data-testid="nav" />}
        overlays={<div data-testid="overlay">overlay</div>}
      >
        <div data-testid="content" />
      </AppShell>
    );

    const outer = container.firstElementChild as HTMLElement;
    const overlay = screen.getByTestId("overlay");
    expect(overlay.parentElement).toBe(outer);
  });

  it("hides the footer when showFooter is false", () => {
    render(
      <AppShell
        navMenu={<div data-testid="nav" />}
        footer={<footer data-testid="footer" />}
        showFooter={false}
      >
        <div data-testid="content" />
      </AppShell>
    );

    expect(screen.queryByTestId("footer")).not.toBeInTheDocument();
  });

  it("does not render a footer wrapper when no footer node is supplied", () => {
    const { container } = render(
      <AppShell navMenu={<div data-testid="nav" />}>
        <div data-testid="content" />
      </AppShell>
    );

    // Only the navMenu and #AppContainer should live inside the flex shell.
    const flexShell = (container.querySelector("#AppContainer") as HTMLElement)
      .parentElement as HTMLElement;
    expect(flexShell.children).toHaveLength(2);
  });

  it("wraps the inner tree in the supplied themeProvider", () => {
    const ThemeMarker: React.FC<{ children: React.ReactNode }> = ({
      children,
    }) => <div data-testid="theme-wrapper">{children}</div>;

    render(
      <AppShell navMenu={<div data-testid="nav" />} themeProvider={ThemeMarker}>
        <div data-testid="content" />
      </AppShell>
    );

    const themeWrapper = screen.getByTestId("theme-wrapper");
    expect(themeWrapper.querySelector("#AppContainer")).not.toBeNull();
  });
});
