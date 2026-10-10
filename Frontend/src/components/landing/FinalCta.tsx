import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { Reveal } from "./Reveal";

export function FinalCta() {
  return (
    <section aria-labelledby="cta-title" className="border-b border-line">
      <div className="mx-auto w-full max-w-4xl px-4 py-28 text-center sm:px-6">
        <Reveal>
          <h2
            id="cta-title"
            className="text-balance text-3xl font-light uppercase leading-tight tracking-tight sm:text-5xl"
          >
            Stop searching. Start asking.
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-ink-muted">
            Upload your first contract and ask your first question.
          </p>
          <Link
            href="/app"
            className="group mt-9 inline-flex min-h-12 items-center gap-2 rounded-full bg-accent px-8 text-[12px] font-medium uppercase tracking-[0.2em] text-accent-ink transition-transform hover:scale-[1.02] active:scale-[0.98]"
          >
            Get started
            <ArrowRight
              size={16}
              weight="bold"
              className="transition-transform group-hover:translate-x-0.5"
              aria-hidden
            />
          </Link>
        </Reveal>
      </div>
    </section>
  );
}
