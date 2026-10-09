import { Suspense } from "react";
import { ConversationWorkspace } from "@/components/document/ConversationWorkspace";
import { WorkspaceSkeleton } from "@/components/document/DocumentWorkspace";
import { Header } from "@/components/layout/Header";

async function Workspace({ params }: { params: PageProps<"/conversations/[id]">["params"] }) {
  const { id } = await params;
  return <ConversationWorkspace id={id} />;
}

export default function ConversationPage({ params }: PageProps<"/conversations/[id]">) {
  return (
    <div className="flex h-dvh flex-col">
      <Header />
      <main className="mx-auto min-h-0 w-full max-w-[1600px] flex-1 px-4 pb-4 pt-4 sm:px-6 lg:px-8">
        {/* Route params are resolved inside Suspense so the rest of the page can prerender. */}
        <Suspense fallback={<WorkspaceSkeleton />}>
          <Workspace params={params} />
        </Suspense>
      </main>
    </div>
  );
}
