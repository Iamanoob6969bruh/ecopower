import { LayoutDashboard, Factory, CloudSun, BarChart3 } from "lucide-react";

const features = [
  {
    icon: LayoutDashboard,
    tab: "01 · Dashboard",
    title: "Unified Control Center",
    desc: "Monitor every solar farm and wind site from a single command surface — live KPIs, anomaly alerts and grid status at a glance.",
    color: "primary",
  },
  {
    icon: Factory,
    tab: "02 · Assets",
    title: "Asset Intelligence",
    desc: "Drill into individual turbines and inverters. Track health, capacity factor and maintenance windows across your fleet.",
    color: "accent",
  },
  {
    icon: CloudSun,
    tab: "03 · Forecast",
    title: "48-Hour AI Forecasts",
    desc: "Satellite-driven, weather-aware predictions powered by machine learning models trained on years of generation data.",
    color: "solar",
  },
  {
    icon: BarChart3,
    tab: "04 · Analysis",
    title: "Deep Analytics",
    desc: "Backtest scenarios, compare actual vs predicted output and export reports for traders, operators and regulators.",
    color: "wind",
  },
];

export const Features = () => {
  return (
    <section className="py-28 relative">
      <div className="container mx-auto px-6">
        <div className="max-w-2xl mb-20">
          <div className="text-[11px] tracking-[0.3em] text-accent font-semibold uppercase mb-5">— Platform Modules</div>
          <h2 className="font-display text-4xl md:text-6xl font-medium leading-[1.05] mb-6">
            Four modules. <span className="gradient-text-gold italic">One source of truth.</span>
          </h2>
          <p className="text-muted-foreground text-lg font-light leading-relaxed">
            Every tab is engineered for the people who keep the lights on — from grid controllers to renewable asset owners.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-5">
          {features.map((f) => (
            <div
              key={f.tab}
              className="group relative rounded-2xl p-8 transition-smooth hover:-translate-y-1 overflow-hidden"
              style={{ background: "var(--gradient-card)", boxShadow: "var(--shadow-card)" }}
            >
              <div
                className="absolute top-0 left-0 w-full h-px opacity-60"
                style={{ background: `linear-gradient(90deg, transparent, hsl(var(--${f.color})), transparent)` }}
              />
              <div className="flex items-start gap-5">
                <div
                  className="w-14 h-14 rounded-xl flex items-center justify-center shrink-0 transition-smooth group-hover:scale-110"
                  style={{
                    background: `hsl(var(--${f.color}) / 0.12)`,
                    color: `hsl(var(--${f.color}))`,
                    border: `1px solid hsl(var(--${f.color}) / 0.35)`,
                  }}
                >
                  <f.icon className="w-6 h-6" />
                </div>
                <div className="flex-1">
                  <div className="text-[10px] tracking-[0.3em] text-muted-foreground mb-2 font-semibold">{f.tab.toUpperCase()}</div>
                  <h3 className="font-display text-2xl font-medium mb-3">{f.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
