import { EnvelopeSimple, LinkedinLogo } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";

const LINKEDIN_URL = "https://www.linkedin.com/in/harris-azhar";
const EMAIL = "harrisazhar2005@gmail.com";

const HEADING = "text-[11px] uppercase tracking-[0.22em] text-ink-subtle";
const LINK =
  "inline-flex min-h-11 items-center gap-2.5 text-sm text-ink-muted transition-colors hover:text-ink focus-visible:text-ink";

export function Footer() {
  return (
    <footer className="bg-surface">
      <div className="mx-auto w-full max-w-7xl px-4 pb-8 pt-16 sm:px-6 lg:px-10">
        <div className="grid gap-12 md:grid-cols-[1.4fr_1fr_1fr]">
          <div className="flex max-w-sm flex-col gap-4">
            <span className="text-[13px] font-medium uppercase tracking-[0.4em]">Marginalia</span>
            <p className="text-sm leading-relaxed text-ink-muted">
              Ask questions of your contracts and see exactly which clause each answer comes from.
            </p>
          </div>

          <nav aria-label="Footer" className="flex flex-col gap-1">
            <h2 className={`${HEADING} mb-2`}>Explore</h2>
            <a href="#how-it-works" className={LINK}>
              How it works
            </a>
            <a href="#who-its-for" className={LINK}>
              Who it&apos;s for
            </a>
            <Link href="/app" className={LINK}>
              Open the app
            </Link>
          </nav>

          <div className="flex flex-col gap-1">
            <h2 className={`${HEADING} mb-2`}>Contact</h2>
            <a href={LINKEDIN_URL} target="_blank" rel="noopener noreferrer" className={LINK}>
              <LinkedinLogo size={18} weight="fill" aria-hidden />
              LinkedIn
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
            <a href={`mailto:${EMAIL}`} className={LINK}>
              <EnvelopeSimple size={18} aria-hidden />
              {EMAIL}
            </a>
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-2 border-t border-line pt-6 text-xs text-ink-subtle sm:flex-row sm:items-center sm:justify-between">
          <p>Built by Muhammad Harris Azhar.</p>
          <p>Marginalia helps you read and search contracts. It is not a law firm and does not give legal advice.</p>
        </div>
      </div>
    </footer>
  );
}
