import { Tag } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import * as LucideIcons from "lucide-react";

/**
 * Resolve a Lucide icon component from a kebab-case (or snake_case) icon name.
 *
 * Category icons are stored as lowercase kebab-case strings (e.g.
 * ``"file-text"``) matching the Lucide icon catalogue, but Lucide exports
 * its React components in PascalCase (``FileText``). This converts the stored
 * name to the export key and looks it up, falling back to the generic ``Tag``
 * icon for empty / unknown names.
 */
export function resolveLucideIcon(
  iconName: string | null | undefined
): LucideIcon {
  if (!iconName) return Tag;
  const pascal = iconName
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
  const icons = LucideIcons as unknown as Record<string, LucideIcon>;
  return icons[pascal] || Tag;
}
