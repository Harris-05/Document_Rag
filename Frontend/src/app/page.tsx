import type { Metadata } from "next";
import { FinalCta } from "@/components/landing/FinalCta";
import { Footer } from "@/components/landing/Footer";
import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { LandingNav } from "@/components/landing/LandingNav";
import { LandingMotion } from "@/components/landing/LandingMotion";
import { WhoItsFor } from "@/components/landing/WhoItsFor";
import "./landing.css";

export const metadata: Metadata = {
  title: "Marginalia: contract answers you can check",
  description:
    "Upload a PDF or Word contract, ask in plain language, and get an answer with the exact clause quoted beside it.",
};

export default function Landing() {
  return (
    <LandingMotion>
      <div className="landing min-h-dvh">
        <LandingNav />
        <main>
          <Hero />
          <HowItWorks />
          <WhoItsFor />
          <FinalCta />
        </main>
        <Footer />
      </div>
    </LandingMotion>
  );
}
