import { FaqSection } from "@/components/marketing/FaqSection";
import { FeaturesSection } from "@/components/marketing/FeatureSection";
import { FinalCta } from "@/components/marketing/FinalCta";
import { Footer } from "@/components/marketing/Footer";
import Hero from "@/components/marketing/Hero";
import { Integrations } from "@/components/marketing/Integrations";
import { LogoCarousel } from "@/components/marketing/LogoCarousel";
import { Navbar } from "@/components/marketing/Navbar";
import { PricingSection } from "@/components/marketing/PricingSection";
import { TestimonialSection } from "@/components/marketing/TestimonialSection";
import { UseCases } from "@/components/marketing/UseCases";

export default function Home() {
  return (
    <div className="landing min-h-screen">
      <Navbar />
      <main>
        <Hero />
        <LogoCarousel />
        <FeaturesSection />
        <UseCases />
        <Integrations />
        <TestimonialSection />
        <PricingSection />
        <FaqSection />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
