import { Header } from "@/components/layout/Header";
import { Workspace } from "@/components/Workspace";

export default function Home() {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-7xl px-4 pb-20 pt-10 sm:px-6 lg:px-10 lg:pt-14">
        <Workspace />
      </main>
    </>
  );
}
