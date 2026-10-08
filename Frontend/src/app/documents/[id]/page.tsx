import { Suspense } from "react";
import { Header } from "@/components/layout/Header";
import { DocumentReader, ReaderSkeleton } from "@/components/reader/DocumentReader";

async function Reader({ params }: { params: PageProps<"/documents/[id]">["params"] }) {
  const { id } = await params;
  return <DocumentReader id={id} />;
}

export default function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-4xl px-4 pb-20 pt-8 sm:px-6 lg:px-10">
        {/* Route params are resolved inside Suspense so the rest of the page can prerender. */}
        <Suspense fallback={<ReaderSkeleton />}>
          <Reader params={params} />
        </Suspense>
      </main>
    </>
  );
}
