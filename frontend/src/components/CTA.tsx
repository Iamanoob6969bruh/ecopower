import { Button } from "@/components/ui/button";
import { ArrowUpRight } from "lucide-react";

export const CTA = () => (
  <section className="bg-primary text-primary-foreground">
    <div className="container mx-auto px-6 lg:px-10 py-24 lg:py-32">
      <div className="grid lg:grid-cols-12 gap-10 items-end">
        <div className="lg:col-span-8">
          <div className="font-mono text-[10px] tracking-[0.3em] text-primary-foreground/60 uppercase mb-6">— Get Started</div>
          <h2 className="font-serif text-5xl lg:text-7xl leading-[0.98] text-balance">
            See your grid <em className="text-accent">twelve hours</em> ahead.
          </h2>
        </div>
        <div className="lg:col-span-4 space-y-6">
          <p className="text-primary-foreground/70 leading-relaxed">
            Plug in your assets, stream weather and SCADA data, and start forecasting in minutes. Onboarding in under a week.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button size="lg" variant="secondary" className="h-12 px-6 rounded-sm gap-2 group">
              Request a demo
              <ArrowUpRight className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </Button>
            <Button size="lg" variant="ghost" className="h-12 px-4 text-primary-foreground hover:bg-primary-foreground/10 underline underline-offset-4 decoration-1">
              Talk to engineering
            </Button>
          </div>
        </div>
      </div>
    </div>
  </section>
);
