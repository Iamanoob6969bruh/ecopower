const metrics = [
  { value: "98.2%", label: "Forecast Accuracy", sub: "MAPE · 12-month sample" },
  { value: "1.4 GW", label: "Capacity Monitored", sub: "Across 320+ sites" },
  { value: "48 h", label: "Forecast Horizon", sub: "Hourly resolution" },
  { value: "<2 s", label: "Data Latency", sub: "Sensor to dashboard" },
];

export const Metrics = () => (
  <section className="py-24 border-y border-border relative overflow-hidden" style={{ background: "var(--gradient-emerald-deep)" }}>
    <div className="absolute inset-0 grid-pattern opacity-30" />
    <div className="container mx-auto px-6 relative">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-10">
        {metrics.map((m, i) => (
          <div key={m.label} className="text-center md:text-left relative">
            {i > 0 && <div className="hidden md:block absolute -left-5 top-2 bottom-2 w-px bg-border/60" />}
            <div className="font-display text-5xl md:text-6xl font-medium gradient-text-gold mb-3">{m.value}</div>
            <div className="text-sm font-semibold tracking-wide">{m.label}</div>
            <div className="text-xs text-muted-foreground mt-1.5 tracking-wider">{m.sub}</div>
          </div>
        ))}
      </div>
    </div>
  </section>
);
