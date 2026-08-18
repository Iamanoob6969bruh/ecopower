import React, { useEffect, useState } from "react";
import { Sun, Wind, Activity, TrendingUp } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/api";
import { istWindow } from "@/lib/time";

interface GridStatus {
  solar_mw: number;
  wind_mw: number;
  frequency: number;
  timestamp: string;
  is_stale: boolean;
}

export const Dashboard = () => {
  const [status, setStatus] = useState<GridStatus | null>(null);
  const [solarTotal, setSolarTotal] = useState<number | null>(null);
  const [windTotal, setWindTotal] = useState<number | null>(null);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const getJson = async (url: string) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${url} -> ${res.status}`);
      return res.json();
    };

    const fetchData = async () => {
      getJson(API_ENDPOINTS.SLDC_STATUS).then(setStatus).catch(() => console.warn("SLDC status unavailable"));
      getJson(API_ENDPOINTS.SOLAR_TOTAL).then(d => setSolarTotal(d.total_mwh)).catch(() => console.warn("Solar summary unavailable"));
      getJson(API_ENDPOINTS.WIND_TOTAL).then(d => setWindTotal(d.total_mwh)).catch(() => console.warn("Wind summary unavailable"));

      // Live forecast accuracy: compare predicted vs actual across today's blocks.
      const { start } = istWindow(24, 0);
      getJson(`${API_ENDPOINTS.GENERATION_AGGREGATE}?start=${start}`)
        .then((rows: any[]) => {
          const errs: number[] = [];
          for (const r of rows || []) {
            const act = (r.solar_actual_kw || 0) + (r.wind_actual_kw || 0);
            const pred = (r.solar_predicted_kw || 0) + (r.wind_predicted_kw || 0);
            const denom = Math.max(act, pred);
            if (denom > 100) errs.push(Math.abs(act - pred) / denom); // ignore near-zero night blocks
          }
          if (errs.length) {
            const mape = errs.reduce((a, b) => a + b, 0) / errs.length;
            setAccuracy(Math.max(0, Math.min(100, (1 - mape) * 100)));
          } else {
            setAccuracy(null);
          }
        })
        .catch(() => console.warn("Aggregate unavailable"));

      setLoading(false);
    };

    fetchData();
    const interval = setInterval(fetchData, 30000); // Poll every 30s for better responsiveness
    return () => clearInterval(interval);
  }, []);


  const stats = [
    {
      icon: Sun,
      label: "Solar Output",
      value: (solarTotal !== null && solarTotal !== undefined) ? solarTotal.toLocaleString() : (status && status.solar_mw !== undefined && status.solar_mw !== null ? status.solar_mw.toFixed(1) : "—"),
      unit: "MWh",
      delta: "Cumulative Today",
      color: "solar"
    },
    {
      icon: Wind,
      label: "Wind Output",
      value: (windTotal !== null && windTotal !== undefined) ? windTotal.toLocaleString() : (status && status.wind_mw !== undefined && status.wind_mw !== null ? status.wind_mw.toFixed(1) : "—"),
      unit: "MWh",
      delta: "Cumulative Today",
      color: "wind"
    },
    {
      icon: TrendingUp,
      label: "Accuracy",
      value: accuracy !== null ? accuracy.toFixed(1) : "—",
      unit: "%",
      delta: "Predicted vs actual · today",
      color: "emerald"
    },
    {
      icon: Activity,
      label: "Frequency",
      value: (status && status.frequency !== undefined && status.frequency !== null) ? status.frequency.toFixed(2) : "—",
      unit: "Hz",
      delta: status?.is_stale ? "Stale feed" : "Live",
      color: "primary"
    },
  ];

  return (
    <section className="container mx-auto px-6 lg:px-10 pt-12 pb-16">
      <div className="flex items-end justify-between mb-6">
        <div>
          <h2 className="font-serif text-3xl lg:text-4xl">Today's grid at a glance</h2>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 border border-border bg-card" style={{ boxShadow: "var(--shadow-soft)" }}>
        {stats.map((s, i) => {
          const Icon = s.icon;
          return (
            <div
              key={s.label}
              className={`p-6 lg:p-7 ${i < 3 ? "lg:border-r" : ""} ${i < 2 ? "border-r border-b lg:border-b-0" : i === 2 ? "border-b lg:border-b-0" : ""} border-border`}
            >
              <div className="flex items-center justify-between mb-5">
                <span className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground uppercase">{s.label}</span>
                <Icon className="w-4 h-4" style={{ color: `hsl(var(--${s.color}))` }} />
              </div>
              <div className="flex items-baseline gap-1.5 mb-1">
                <span className="font-serif text-5xl">{s.value}</span>
                <span className="text-sm text-muted-foreground">{s.unit}</span>
              </div>
              <div className="font-mono text-[11px]" style={{ color: `hsl(var(--${s.color}))` }}>{s.delta}</div>
            </div>
          );
        })}
      </div>
    </section>
  );
};

