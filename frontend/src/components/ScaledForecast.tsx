import React, { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { format, parseISO } from "date-fns";

import { API_ENDPOINTS } from "@/lib/api";

interface ScaledForecastProps {
  plant_id: string;
  name: string;
  latitude: number;
  longitude: number;
  dc_capacity_mw: number;
  ac_capacity_mw: number;
}

export const ScaledForecast = ({ plant_id, name, latitude, longitude, dc_capacity_mw, ac_capacity_mw }: ScaledForecastProps) => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchForecast = async () => {
      setLoading(true);
      try {
        const response = await fetch(API_ENDPOINTS.LIVE_PREDICTION, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            latitude: latitude,
            longitude: longitude,
            dc_capacity_mw: dc_capacity_mw,
            ac_capacity_mw: ac_capacity_mw,
            tilt: 15.0,
            azimuth: 180.0
          })
        });
        const result = await response.json();
        const formatted = result.map((d: any) => ({
          ...d,
          displayTime: format(parseISO(d.timestamp), "HH:mm"),
          displayDate: format(parseISO(d.timestamp), "MMM dd")
        }));
        setData(formatted);
      } catch (error) {
        console.error("Failed to fetch forecast:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchForecast();
  }, [plant_id, latitude, longitude, dc_capacity_mw, ac_capacity_mw]);

  if (loading) return (
    <div className="w-full h-full min-h-[300px] flex items-center justify-center font-mono text-[10px] text-muted-foreground animate-pulse border border-dashed border-border bg-background/50">
      SYNCING PHYSICS-GUIDED AI DISPATCH...
    </div>
  );

  return (
    <div className="w-full h-full flex flex-col">
      <div className="flex items-center justify-between mb-4 pr-4">
        <div className="font-mono text-[10px] tracking-[0.1em] text-muted-foreground uppercase">
          Scaled LightGBM Forecast · Live
        </div>
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-solar">
          <div className="w-3 h-0.5 bg-solar" /> PREDICTION (MW)
        </div>
      </div>

      <div className="w-full flex-1 min-h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorPredScaled" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(var(--solar))" stopOpacity={0.3} />
                <stop offset="95%" stopColor="hsl(var(--solar))" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis
              dataKey="displayTime"
              stroke="hsl(var(--muted-foreground))"
              fontSize={10}
              fontFamily="JetBrains Mono"
              interval={4}
              tickMargin={10}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              fontSize={10}
              fontFamily="JetBrains Mono"
              tickFormatter={(val) => `${val}`}
              tickMargin={10}
            />
            <Tooltip
              contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '4px' }}
              itemStyle={{ fontFamily: 'JetBrains Mono', fontSize: '12px' }}
              labelStyle={{ color: 'hsl(var(--muted-foreground))', marginBottom: '4px', fontSize: '10px' }}
              formatter={(value: any) => [`${value} MW`, "Prediction"]}
            />
            <Area
              type="monotone"
              dataKey="pred_mw"
              name="Prediction"
              stroke="hsl(var(--solar))"
              fillOpacity={1}
              fill="url(#colorPredScaled)"
              strokeWidth={2}
              isAnimationActive={true}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
