import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";

/** The way back to the library, shown at the start of every workspace page's title bar. */
export function Crumb() {
  return (
    <nav aria-label="Breadcrumb" className="-ml-2 flex items-center gap-3">
      <Link
        href="/app"
        className="inline-flex min-h-11 items-center gap-2 rounded-ctl px-2 text-[11px] uppercase tracking-[0.22em] text-ink-muted transition-colors hover:text-ink"
      >
        <ArrowLeft size={14} aria-hidden />
        Library
      </Link>
      <span aria-hidden className="h-5 w-px bg-line-strong" />
    </nav>
  );
}
