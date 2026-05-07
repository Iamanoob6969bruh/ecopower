import React, { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine
} from "recharts";
import { format, parseISO, subHours, addHours, startOfDay, addDays } from "date-fns";
import { Activity } from "lucide-react";

import { API_ENDPOINTS } from "../lib/api";

export const LiveGraph = ({
  plant_id,
  capacity_mw,
  plant_type,
  onDataUpdate
}: {
  plant_id: string,
  capacity_mw: number,
  plant_type: "solar" | "wind",
  onDataUpdate?: (stats: { peak: number, avg: number, totalEnergyMWh: number }) => void
}) => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const now = new Date();
        // Rolling Window: 12 hours past to 12 hours future
        const start = subHours(now, 12).toISOString();
        const end = addHours(now, 12).toISOString();

        const response = await fetch(`${API_ENDPOINTS.PLANT_GENERATION(plant_id)}?start=${start}&end=${end}`);
        if (!response.ok) throw new Error("Failed to fetch");
        const raw = await response.json();
        
        if (raw && Array.isArray(raw)) {
          const formatted = raw.map((d: any) => {
            const ts = parseISO(d.timestamp);
            return {
              ...d,
              timestampMs: ts.getTime(),
              // Show actual if it exists in the database
              actual_kw: d.actual_kw !== null ? d.actual_kw : null,
              predicted_kw: d.predicted_kw !== null ? d.predicted_kw : null,
            };
          });

          setData(formatted);

          if (onDataUpdate) {
            const todayStart = startOfDay(now).getTime();
            const todayEnd = addDays(startOfDay(now), 1).getTime();
            const todayActuals = formatted.filter((d: any) => d.timestampMs >= todayStart && d.timestampMs < todayEnd && d.actual_kw !== null);

            const peak = Math.max(...todayActuals.map((d: any) => d.actual_kw || 0), 0) / 1000;
            const avg = todayActuals.length > 0
              ? todayActuals.reduce((acc: number, d: any) => acc + (d.actual_kw || 0), 0) / todayActuals.length / 1000
              : 0;

            const totalEnergyMWh = todayActuals.reduce((acc: number, d: any) => acc + (d.actual_kw || 0) * 0.25, 0) / 1000;

            onDataUpdate({ peak, avg, totalEnergyMWh });
          }

        }
      } catch (e) {
        console.error(e);
        setError(true);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [plant_id]);

  const nowMs = new Date().getTime();

  if (loading) {
    return (
      <div className="w-full h-[350px] flex items-center justify-center font-mono text-xs text-muted-foreground animate-pulse">
        SYNCING TELEMETRY...
      </div>
    );
  }

  if (error || data.length === 0) {
    return (
      <div className="w-full h-[350px] flex flex-col items-center justify-center text-center p-8">
        <Activity className="w-12 h-12 text-muted-foreground/20 mx-auto mb-6" />
        <h3 className="font-serif text-lg mb-3 text-muted-foreground">Generation Telemetry Unavailable</h3>
        <p className="text-sm text-muted-foreground/70 leading-relaxed italic max-w-sm">
          "Waiting for plant handshake..."
        </p>
      </div>
    );
  }

  const primaryColor = plant_type === "solar" ? "hsl(var(--solar))" : "hsl(var(--wind))";
  const predColor = "hsl(var(--emerald))";

  return (
    <div className="w-full h-full flex flex-col relative group">
      {/* Internal Legend - Matches Image Precisely */}
      <div className="absolute top-6 right-10 z-10 flex items-center gap-6 text-[9px] font-mono pointer-events-none">
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5" style={{ backgroundColor: primaryColor }} />
          <span className="text-muted-foreground tracking-widest uppercase">Actual</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5 border-t border-dashed" style={{ borderColor: predColor }} />
          <span className="text-muted-foreground tracking-widest uppercase">Predicted</span>
        </div>
      </div>

      <div className="w-full flex-1 p-6 border border-dashed border-muted-foreground/30 bg-background/20 rounded-sm">
        <ResponsiveContainer width="100%" height={380}>
          <AreaChart data={data} margin={{ top: 40, right: 20, left: 0, bottom: 40 }}>
            <defs>
              <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={primaryColor} stopOpacity={0.4} />
                <stop offset="95%" stopColor={primaryColor} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorPred" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={predColor} stopOpacity={0.15} />
                <stop offset="95%" stopColor={predColor} stopOpacity={0} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} opacity={0.6} />

            <XAxis
              dataKey="timestampMs"
              type="number"
              domain={['dataMin', 'dataMax']}
              stroke="hsl(var(--muted-foreground))"
              fontSize={9}
              fontFamily="JetBrains Mono"
              tickFormatter={(val) => {
                const d = new Date(val);
                return format(d, "HH:mm");
              }}
              tick={{ dy: 10 }}
              interval="preserveStartEnd"
              minTickGap={60}
              axisLine={{ stroke: 'hsl(var(--border))', strokeWidth: 1 }}
            />

            <YAxis
              stroke="hsl(var(--muted-foreground))"
              fontSize={9}
              fontFamily="JetBrains Mono"
              tickFormatter={(val) => `${val}\nkW`}
              tick={{ dx: -10 }}
              axisLine={false}
              tickLine={false}
              domain={[0, capacity_mw * 1000]}
              ticks={[0, capacity_mw * 1000 * 0.33, capacity_mw * 1000 * 0.66, capacity_mw * 1000]}
            />

            <Tooltip
              labelFormatter={(label) => format(new Date(label), "MMM dd, HH:mm")}
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                borderColor: 'hsl(var(--border))',
                borderRadius: '0px',
                boxShadow: 'var(--shadow-soft)',
                fontFamily: 'JetBrains Mono',
                fontSize: '11px'
              }}
            />

            <Area
              type="monotone"
              dataKey="predicted_kw"
              stroke={predColor}
              strokeWidth={1.5}
              strokeDasharray="4 4"
              fillOpacity={1}
              fill="url(#colorPred)"
              isAnimationActive={false}
              connectNulls={true}
            />

            <Area
              type="monotone"
              dataKey="actual_kw"
              stroke={primaryColor}
              strokeWidth={2.5}
              fillOpacity={1}
              fill="url(#colorActual)"
              isAnimationActive={false}
              connectNulls={false}
            />

            <ReferenceLine x={nowMs} stroke="hsl(var(--destructive))" strokeDasharray="2 2" opacity={0.5} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
