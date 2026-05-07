import { LayoutDashboard, Factory, CloudSun, BarChart3 } from "lucide-react";

const modules = [
  { n: "01", icon: LayoutDashboard, title: "Dashboard", desc: "Unified command surface for every site, asset and feed." },
  { n: "02", icon: Factory, title: "Assets", desc: "Per-turbine and per-inverter health, capacity factor and SLA tracking." },
  { n: "03", icon: CloudSun, title: "Forecast", desc: "Probabilistic 48-hour generation outlook with P10/P50/P90 bands." },
  { n: "04", icon: BarChart3, title: "Analysis", desc: "Backtest, compare actual vs predicted, export regulator-ready reports." },
];

export const Modules = () => (
  <section className="border-t border-border">
    <div className="container mx-auto px-6 lg:px-10 py-20">
      <div className="grid lg:grid-cols-12 gap-10 mb-12">
        <div className="lg:col-span-5">
          <div className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground uppercase mb-4">— Platform</div>
          <h2 className="font-serif text-4xl lg:text-5xl leading-[1.05] text-balance">
            Four modules. <em className="text-accent">One</em> source of truth.
          </h2>
        </div>
        <p className="lg:col-span-6 lg:col-start-7 text-muted-foreground text-lg leading-relaxed">
          Engineered for the people who keep the lights on — grid controllers, asset owners, traders and regulators sharing the same numbers, the same minute.
        </p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-4 border-t border-border">
        {modules.map((m, i) => {
          const Icon = m.icon;
          return (
            <div
              key={m.n}
              className={`group p-8 border-b md:border-b-0 ${i < 3 ? "md:border-r" : ""} ${i % 2 === 0 ? "border-r md:border-r" : ""} border-border hover:bg-muted/40 transition-colors cursor-pointer`}
            >
              <div className="flex items-start justify-between mb-12">
                <span className="font-mono text-[11px] tracking-wider text-muted-foreground">{m.n}</span>
                <Icon className="w-5 h-5 text-muted-foreground group-hover:text-accent transition-colors" />
              </div>
              <h3 className="font-serif text-3xl mb-3">{m.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{m.desc}</p>
            </div>
          );
        })}
      </div>
    </div>
  </section>
);
