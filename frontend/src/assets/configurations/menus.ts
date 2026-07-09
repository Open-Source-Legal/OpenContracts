export interface HeaderMenuItem {
  title: string;
  route: string;
  protected: boolean;
  id: string;
  activeRoutes?: string[];
}

export const header_menu_items: HeaderMenuItem[] = [
  {
    title: "Start",
    route: "/",
    protected: false,
    id: "discover_menu_button",
  },
  {
    title: "Akten",
    route: "/akten",
    protected: false,
    id: "corpus_menu_button",
    activeRoutes: ["/corpuses"],
  },
  {
    title: "Dokumente",
    route: "/documents",
    protected: false,
    id: "document_menu_button",
  },
  {
    title: "Vertragsprüfung",
    route: "/vertragspruefung",
    protected: false,
    id: "extract_menu_button",
    activeRoutes: ["/extracts"],
  },
  {
    title: "Playbooks",
    route: "/playbooks",
    protected: false,
    id: "label_set_menu_button",
    activeRoutes: ["/label_sets"],
  },
];
