import { Buildings, Gavel, Handshake, ShieldCheck } from "@phosphor-icons/react/dist/ssr";
import { Reveal } from "./Reveal";

const AUDIENCES = [
  {
    icon: Gavel,
    title: "Lawyers and legal teams",
    body: "Find the clause you need without rereading the whole agreement, and compare two versions to see what changed and why it matters.",
  },
  {
    icon: Handshake,
    title: "Procurement and vendor managers",
    body: "Ask the same question across several supplier contracts at once: notice periods, renewals, liability limits.",
  },
  {
    icon: Buildings,
    title: "Founders and operators",
    body: "Understand the agreement before you sign it. Get a plain answer and the exact wording behind it, ready to share as PDF or Word.",
  },
  {
    icon: ShieldCheck,
    title: "Compliance and risk",
    body: "Trace every answer to its source text. When the evidence is thin, Marginalia says so instead of guessing.",
  },
] as const;

export function WhoItsFor() {
  return (
    <section id="who-its-for" aria-labelledby="who-title" className="border-b border-line bg-surface">
      <div className="mx-auto w-full max-w-7xl px-4 py-24 sm:px-6 lg:px-10">
        <Reveal className="max-w-2xl">
          <p className="text-[11px] uppercase tracking-[0.22em] text-ink-subtle">Who it&apos;s for</p>
          <h2 id="who-title" className="mt-3 text-3xl font-light uppercase leading-tight tracking-tight sm:text-4xl">
            For anyone who has to read contracts closely
          </h2>
        </Reveal>
        <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {AUDIENCES.map(({ icon: Icon, title, body }, index) => (
            <li key={title}>
              <Reveal delay={index * 0.08} className="h-full">
                <div className="h-full rounded-md border border-line bg-surface p-6 shadow-card transition-transform duration-300 hover:-translate-y-1">
                  <span className="mb-5 grid size-10 place-items-center rounded-full bg-accent text-accent-ink">
                    <Icon size={20} aria-hidden />
                  </span>
                  <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">{body}</p>
                </div>
              </Reveal>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
