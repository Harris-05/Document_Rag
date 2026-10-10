import Link from "next/link";
import { Suspense } from "react";
import { ActiveNav } from "./ActiveNav";
import { NavLinks } from "./NavLinks";

/** The bar across the top of every page inside the app. */
export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur-xl">
      <div className="mx-auto flex h-16 w-full max-w-[1600px] items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link
          href="/app"
          className="-ml-2 inline-flex min-h-11 items-center rounded-ctl px-2 text-[13px] font-medium uppercase tracking-[0.4em] text-ink"
          aria-label="Marginalia library"
        >
          Marginalia
        </Link>
        {/* The current page is only known in the browser, so the links first render without it, then mark it. */}
        <Suspense fallback={<NavLinks inLibrary={false} />}>
          <ActiveNav />
        </Suspense>
      </div>
    </header>
  );
}
