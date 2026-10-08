import { Quotes } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";

export function Header() {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center px-4 sm:px-6 lg:px-10">
        <Link
          href="/"
          className="-ml-2 flex min-h-11 items-center gap-2.5 rounded-ctl px-2 text-ink"
          aria-label="Marginalia home"
        >
          <span className="grid size-8 place-items-center rounded-ctl bg-accent text-accent-ink">
            <Quotes size={18} weight="fill" aria-hidden />
          </span>
          <span className="text-[17px] font-semibold tracking-tight">Marginalia</span>
        </Link>
      </div>
    </header>
  );
}
