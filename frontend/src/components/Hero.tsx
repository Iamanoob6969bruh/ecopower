import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export const Hero = () => {
  return (
    <section className="relative overflow-hidden">
      <div className="container mx-auto px-6 lg:px-10 pt-16 lg:pt-24 pb-12">
        <div className="grid lg:grid-cols-12 gap-10 lg:gap-16 items-end">
          {/* Left — editorial text */}
          <div className="lg:col-span-7 animate-fade-up">
            <div className="flex items-center gap-3 mb-8 font-mono text-[11px] tracking-[0.25em] text-muted-foreground uppercase">
              <span className="w-8 h-px bg-accent" />
              Issue №.014 · Renewable Forecasting
            </div>

            <h1 className="font-serif text-[3.25rem] sm:text-7xl lg:text-[6rem] leading-[0.95] tracking-tight text-balance mb-8">
              The grid, <em className="text-accent">forecast</em>
              <br />
              twelve hours <br className="hidden sm:block" />
              <span className="italic text-muted-foreground/70">before sunrise.</span>
            </h1>

            <p className="text-lg text-muted-foreground max-w-xl leading-relaxed mb-10">
              EcoPower Intelligence reads satellites, weather models and SCADA telemetry to predict every megawatt of solar and wind generation — so operators trade, dispatch and balance with calm precision.
            </p>

            <div className="flex flex-wrap items-center gap-4">
              <Button size="lg" className="h-12 px-6 rounded-sm font-medium gap-2 group">
                Open Control Center
                <ArrowUpRight className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </Button>
              <Button size="lg" variant="ghost" className="h-12 px-4 font-medium underline underline-offset-4 decoration-1">
                Read the methodology →
              </Button>
            </div>
          </div>

          {/* Right — editorial meta block */}
          <aside className="lg:col-span-5 lg:pl-10 lg:border-l border-border space-y-8 animate-fade-up" style={{ animationDelay: "0.15s" }}>
            <Meta label="Coverage" value="320+ sites · 1.4 GW" detail="Solar parks, on-shore & off-shore wind across South Asia" />
            <Meta label="Horizon" value="48 hours · hourly" detail="Probabilistic outputs with P10/P50/P90 bands" />
            <Meta label="Model" value="EP-Forecast v4.2" detail="Trained on 11 years of generation & weather reanalysis" />
            <div className="pt-6 border-t border-border font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
              Updated 06 May 2026 · 14:32 IST
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
};

const Meta = ({ label, value, detail }: { label: string; value: string; detail: string }) => (
  <div>
    <div className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground uppercase mb-2">{label}</div>
    <div className="font-serif text-3xl mb-1.5">{value}</div>
    <div className="text-sm text-muted-foreground leading-relaxed">{detail}</div>
  </div>
);
