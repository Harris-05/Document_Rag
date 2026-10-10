import Link from "next/link";

const NAV_LINK =
  "inline-flex min-h-11 items-center border-b border-transparent text-[11px] uppercase tracking-[0.22em] text-ink-muted transition-colors hover:text-ink";

/** The links on the right of the app's top bar. Which page is current is passed in, so this needs no browser APIs. */
export function NavLinks({ inLibrary }: { inLibrary: boolean }) {
  return (
    <nav aria-label="Main" className="flex items-center gap-7">
      <Link
        href="/app"
        aria-current={inLibrary ? "page" : undefined}
        className={`${NAV_LINK} ${inLibrary ? "!border-ink !text-ink" : ""}`}
      >
        Library
      </Link>
      <Link href="/" className={NAV_LINK}>
        Overview
      </Link>
    </nav>
  );
}
