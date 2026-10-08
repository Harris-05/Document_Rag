import { FileDoc, FilePdf } from "@phosphor-icons/react/dist/ssr";
import type { FileKind } from "@/lib/types";

/** Resolves the kind from a filename when the server has not told us yet. */
export function kindFromName(name: string): FileKind {
  return name.toLowerCase().endsWith(".docx") ? "docx" : "pdf";
}

export function FileBadge({ kind, size = 40 }: { kind: FileKind; size?: number }) {
  const Icon = kind === "pdf" ? FilePdf : FileDoc;
  return (
    <span
      className="grid shrink-0 place-items-center rounded-ctl bg-surface-2 text-ink-muted"
      style={{ width: size, height: size }}
    >
      <Icon size={Math.round(size * 0.55)} weight="duotone" aria-hidden />
    </span>
  );
}
