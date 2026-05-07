const items = [
  { label: "SOLAR", value: "94.3 MWh", delta: "+2.4%", up: true },
  { label: "WIND", value: "62.1 MWh", delta: "+1.2%", up: true },
  { label: "GRID FREQ", value: "50.00 Hz", delta: "STABLE", up: true },
  { label: "FORECAST ACC.", value: "98.2%", delta: "MAPE", up: true },
  { label: "CARBON OFFSET", value: "412 t CO₂", delta: "+18 t", up: true },
  { label: "DISPATCH PRICE", value: "₹3.42 /kWh", delta: "-0.8%", up: false },
  { label: "CAPACITY USE", value: "76.4%", delta: "+1.1%", up: true },
  { label: "ANOMALIES", value: "0", delta: "OK", up: true },
];

export const Ticker = () => {
  const row = [...items, ...items];
  return (
    <div className="border-y border-border bg-primary text-primary-foreground overflow-hidden">
      <div className="flex animate-ticker py-2.5 whitespace-nowrap">
        {row.map((it, i) => (
          <div key={i} className="flex items-center gap-3 px-8 font-mono text-[11px] tracking-wider">
            <span className="text-primary-foreground/60">{it.label}</span>
            <span className="font-semibold">{it.value}</span>
            <span style={{ color: it.up ? "hsl(var(--emerald))" : "hsl(var(--signal))" }}>
              {it.up ? "▲" : "▼"} {it.delta}
            </span>
            <span className="text-primary-foreground/30">·</span>
          </div>
        ))}
      </div>
    </div>
  );
};
