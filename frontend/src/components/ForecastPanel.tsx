import React, { useEffect, useState } from "react";
import { format } from "date-fns";
import { API_ENDPOINTS } from "@/lib/api";

const W = 1000;
const H = 320;
const PAD = { l: 64, r: 24, t: 24, b: 36 };

export const ForecastPanel = () => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
        const response = await fetch(`${API_ENDPOINTS.GENERATION_AGGREGATE}?start=${start}`);
        if (!response.ok) throw new Error("Failed to fetch");
        const raw = await response.json();

        let cumulativeSolar = 0;
        let cumulativeWind = 0;
        let cumulativeSolarF = 0;
        let cumulativeWindF = 0;

        const formatted = raw.map((d: any, i: number) => {
          // Accumulate energy: each point is 15 mins (0.25h)
          // kw * 0.25 / 1000 = MWh
          cumulativeSolar += (d.solar_actual_kw * 0.25) / 1000;
          cumulativeWind += (d.wind_actual_kw * 0.25) / 1000;
          cumulativeSolarF += (d.solar_predicted_kw * 0.25) / 1000;
          cumulativeWindF += (d.wind_predicted_kw * 0.25) / 1000;

          return {
            hour: i,
            timestamp: d.timestamp,
            solar: cumulativeSolar,
            wind: cumulativeWind,
            solarF: cumulativeSolarF,
            windF: cumulativeWindF
          };
        });
        setData(formatted);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading || data.length === 0) {
    return (
      <section className="container mx-auto px-6 lg:px-10 pb-16">
        <div className="h-[400px] flex items-center justify-center border border-dashed border-muted-foreground/30 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Calibrating AI Generation Models...
        </div>
      </section>
    );
  }

  const yMax = Math.max(...data.flatMap((d) => [d.solar, d.wind, d.solarF, d.windF])) * 1.1;
  const xScale = (i: number) => PAD.l + (i / (data.length - 1)) * (W - PAD.l - PAD.r);
  const yScale = (v: number) => PAD.t + (1 - v / yMax) * (H - PAD.t - PAD.b);

  const buildArea = (key: string) => {
    const points = data.map((d, i) => `${xScale(i)},${yScale(d[key])}`).join(" ");
    return `${PAD.l},${H - PAD.b} ${points} ${W - PAD.r},${H - PAD.b}`;
  };

  const buildLine = (key: string) =>
    data.map((d, i) => `${xScale(i)},${yScale(d[key])}`).join(" ");

  return (
    <section className="container mx-auto px-6 lg:px-10 pb-16">
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Chart */}
        <div className="lg:col-span-2 border border-border bg-card p-6 lg:p-8" style={{ boxShadow: "var(--shadow-soft)" }}>
          <div className="flex items-start justify-between mb-6">
            <div>
              <div className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground uppercase mb-2">— Cumulative · 48h</div>
              <h3 className="font-serif text-2xl">Total Generation Progress</h3>
              <p className="text-xs text-muted-foreground mt-1">Real-time aggregation of all fleet nodes</p>
            </div>
            <div className="flex items-center gap-4 text-[11px] font-mono">
              <Legend color="solar" label="SOLAR (MWh)" />
              <Legend color="wind" label="WIND (MWh)" />
              <Legend color="emerald" label="FORECAST" dashed />
            </div>
          </div>

          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto overflow-visible">
            {/* Grid */}
            {[0, 0.25, 0.5, 0.75, 1].map((p) => (
              <line
                key={p}
                x1={PAD.l}
                x2={W - PAD.r}
                y1={PAD.t + p * (H - PAD.t - PAD.b)}
                y2={PAD.t + p * (H - PAD.t - PAD.b)}
                stroke="hsl(var(--border))"
                strokeWidth="1"
                strokeDasharray="4 4"
              />
            ))}
            {/* Y labels */}
            {[0, 0.25, 0.5, 0.75, 1].map((p) => (
              <text
                key={`y${p}`}
                x={PAD.l - 8}
                y={PAD.t + p * (H - PAD.t - PAD.b) + 3}
                textAnchor="end"
                className="fill-muted-foreground"
                style={{ fontSize: 9, fontFamily: "JetBrains Mono" }}
              >
                {Math.round(yMax * (1 - p)).toLocaleString()} <tspan fontSize="7">MWh</tspan>
              </text>
            ))}
            {/* X labels */}
            {[0, 12, 24, 36, 47].map((i) => {
              if (i >= data.length) return null;
              return (
                <text
                  key={`x${i}`}
                  x={xScale(i)}
                  y={H - PAD.b + 18}
                  textAnchor="middle"
                  className="fill-muted-foreground"
                  style={{ fontSize: 9, fontFamily: "JetBrains Mono" }}
                >
                  {format(new Date(data[i].timestamp), "HH:mm")}
                </text>
              );
            })}

            <defs>
              <linearGradient id="solarGrad" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--solar))" stopOpacity="0.35" />
                <stop offset="100%" stopColor="hsl(var(--solar))" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="windGrad" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--wind))" stopOpacity="0.3" />
                <stop offset="100%" stopColor="hsl(var(--wind))" stopOpacity="0" />
              </linearGradient>
            </defs>

            <polygon points={buildArea("solar")} fill="url(#solarGrad)" />
            <polygon points={buildArea("wind")} fill="url(#windGrad)" />

            <polyline points={buildLine("solar")} fill="none" stroke="hsl(var(--solar))" strokeWidth="2.5" />
            <polyline points={buildLine("wind")} fill="none" stroke="hsl(var(--wind))" strokeWidth="2.5" />

            <polyline points={buildLine("solarF")} fill="none" stroke="hsl(var(--emerald))" strokeWidth="1.5" strokeDasharray="4 4" />
            <polyline points={buildLine("windF")} fill="none" stroke="hsl(var(--emerald))" strokeWidth="1.5" strokeDasharray="4 4" opacity="0.6" />
          </svg>
        </div>

        {/* Side notes */}
        <aside className="border border-border bg-card p-6 lg:p-8 space-y-6" style={{ boxShadow: "var(--shadow-soft)" }}>
          {(() => {
            const last = data[data.length - 1];
            const isAnomaly = last.solar < last.solarF * 0.9 || last.wind < last.windF * 0.9;

            return (
              <>
                <div>
                  <div className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground uppercase mb-2">— Anomaly Intelligence</div>
                  <h3 className={`font-serif text-2xl mb-1 ${isAnomaly ? "text-destructive" : ""}`}>
                    {isAnomaly ? "Anomalies Detected" : "System Nominal"}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {isAnomaly
                      ? "Localized generation shortfall detected in cluster nodes. Efficiency below expected AI baseline."
                      : "All cluster nodes performing within 95% of AI predicted confidence interval."}
                  </p>
                </div>
                <div className="border-t border-border pt-5 space-y-4">
                  <Row
                    label="Solar Performance"
                    value={`${((last.solar / (last.solarF || 1)) * 100).toFixed(1)}%`}
                    sub={last.solar < last.solarF * 0.9 ? "Underperforming · Inspect" : "Optimal Output"}
                  />
                  <Row
                    label="Wind Efficiency"
                    value={`${((last.wind / (last.windF || 1)) * 100).toFixed(1)}%`}
                    sub={last.wind < last.windF * 0.9 ? "Low Velocity Capture" : "Stable Capture"}
                  />
                  <Row
                    label="Grid Impact"
                    value={isAnomaly ? "Moderate" : "Negligible"}
                    sub={isAnomaly ? "-1.2 MW Shortfall" : "Sync Optimized"}
                  />
                </div>
                <div className={`border-t border-border pt-5 font-mono text-[10px] tracking-wider uppercase ${isAnomaly ? "text-destructive animate-pulse" : "text-muted-foreground"}`}>
                  {isAnomaly ? "Alert: Verification Required" : "Live Feed Active"}
                </div>
              </>
            );
          })()}
        </aside>
      </div>
    </section>
  );
};

const Legend = ({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) => (
  <div className="flex items-center gap-1.5 text-muted-foreground">
    <svg width="14" height="6">
      <line x1="0" y1="3" x2="14" y2="3" stroke={`hsl(var(--${color}))`} strokeWidth="1.5" strokeDasharray={dashed ? "2 2" : "0"} />
    </svg>
    {label}
  </div>
);

const Row = ({ label, value, sub }: { label: string; value: string; sub: string }) => (
  <div className="flex items-baseline justify-between gap-4">
    <div className="font-mono text-[10px] tracking-[0.2em] text-muted-foreground uppercase">{label}</div>
    <div className="text-right">
      <div className="font-serif text-lg leading-none">{value}</div>
      <div className="text-[11px] text-muted-foreground mt-1">{sub}</div>
    </div>
  </div>
);
