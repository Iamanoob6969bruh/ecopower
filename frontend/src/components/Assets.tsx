import React from "react";
import { Sun, Wind, MapPin, Activity, X, AlertTriangle, CheckCircle, Info } from "lucide-react";
import { LiveGraph } from "./LiveGraph";

interface Asset {
  plant_id: string;
  name: string;
  plant_type: "solar" | "wind";
  capacity_mw: number;
  dc_capacity_mw?: number;
  district: string;
  status: "green" | "yellow" | "red";
  operator: string;
  year?: number;
  description?: string;
  hardware?: string;
  coordinates?: [number, number];
}

const solarAssets: Asset[] = [
  {
    plant_id: "kpcl_shivanasamudra",
    name: "Shivanasamudra Solar Plant",
    plant_type: "solar",
    capacity_mw: 15,
    dc_capacity_mw: 18,
    district: "Mandya",
    status: "green",
    operator: "KPCL (State Govt)",
    description: "KPCL's flagship 15 MW solar plant located near the Shivanasamudra waterfalls. Generates power using fixed-tilt modules.",
    hardware: "Multi-Crystalline Panels",
    coordinates: [12.3000, 77.1700]
  },
  {
    plant_id: "kpcl_yalesandra",
    name: "Yalesandra Solar PV Plant",
    plant_type: "solar",
    capacity_mw: 3,
    dc_capacity_mw: 3.6,
    district: "Kolar",
    status: "green",
    operator: "KPCL (State Govt)",
    description: "India's first megawatt-scale, grid-connected solar power plant, commissioned in 2009 over 10.3 acres.",
    hardware: "Mono-Crystalline Panels (225Wp & 240Wp)",
    coordinates: [12.8931, 78.1655]
  },
  {
    plant_id: "kpcl_itnal",
    name: "Itnal Solar PV Plant",
    plant_type: "solar",
    capacity_mw: 3,
    dc_capacity_mw: 3.6,
    district: "Belagavi",
    status: "yellow",
    operator: "KPCL (State Govt)",
    description: "State-owned decentralized 3 MW generation facility feeding directly into the northern Karnataka local grid.",
    hardware: "Mono-Crystalline Panels",
    coordinates: [16.4348, 74.6740]
  },
  {
    plant_id: "kpcl_yapaldinni",
    name: "Yapaldinni Solar PV Plant",
    plant_type: "solar",
    capacity_mw: 3,
    dc_capacity_mw: 3.6,
    district: "Raichur",
    status: "green",
    operator: "KPCL (State Govt)",
    description: "3 MW grid-connected power plant located in the high-heat, high-irradiance district of Raichur.",
    hardware: "Mono-Crystalline Panels",
    coordinates: [16.2475, 77.4431]
  },
  {
    plant_id: "kspdcl_pavagada",
    name: "Pavagada Solar Park",
    plant_type: "solar",
    capacity_mw: 2050,
    dc_capacity_mw: 2460,
    district: "Tumkur",
    status: "green",
    operator: "KSPDCL (Joint Govt Venture)",
    description: "One of the world's largest solar parks spanning 13,000 acres. Grid infrastructure managed by KSPDCL.",
    hardware: "Mixed (Thin-film & Multi-Crystalline)",
    coordinates: [14.2500, 77.4500]
  }
];

const windAssets: Asset[] = [
  { plant_id: "wind_tuppadahalli", name: "Tuppadahalli Wind Farm", plant_type: "wind", capacity_mw: 56.1, district: "Chitradurga", status: "green", operator: "Acciona", hardware: "80m Hub Height", coordinates: [14.200, 76.433] },
  { plant_id: "wind_bannur", name: "Bannur Wind Farm", plant_type: "wind", capacity_mw: 78.0, district: "Vijayapura", status: "green", operator: "Suez", hardware: "120m Hub Height", coordinates: [16.830, 75.720] },
  { plant_id: "wind_jogmatti", name: "Jogmatti BSES Wind Farm", plant_type: "wind", capacity_mw: 14.0, district: "Chitradurga", status: "yellow", operator: "BSES", hardware: "65m Hub Height", coordinates: [14.108, 76.391] },
  { plant_id: "wind_bijapur", name: "Bijapur Wind Farm", plant_type: "wind", capacity_mw: 50.0, district: "Vijayapura", status: "green", operator: "Inox Wind", hardware: "106m Hub Height", coordinates: [16.750, 75.900] },
  { plant_id: "wind_gadag", name: "Gadag Wind Farm", plant_type: "wind", capacity_mw: 302.4, district: "Gadag", status: "green", operator: "ReNew Power", hardware: "135m Hub Height", coordinates: [15.420, 75.620] },
  { plant_id: "wind_mangoli", name: "Energon Mangoli Wind Farm", plant_type: "wind", capacity_mw: 46.0, district: "Vijayapura", status: "green", operator: "Energon", hardware: "100m Hub Height", coordinates: [16.550, 76.200] },
  { plant_id: "wind_tata_power", name: "Tata Power Wind Project", plant_type: "wind", capacity_mw: 50.4, district: "Gadag", status: "green", operator: "Tata Power", hardware: "65m Hub Height", coordinates: [15.350, 75.580] },
  { plant_id: "wind_clp", name: "CLP Wind Farm", plant_type: "wind", capacity_mw: 50.0, district: "Belagavi", status: "green", operator: "CLP India", hardware: "80m Hub Height", coordinates: [16.140, 74.830] },
];


const StatusLight = ({ status }: { status: "green" | "yellow" | "red" }) => {
  const colors = {
    green: "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]",
    yellow: "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]",
    red: "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.4)]",
  };
  return <div className={`w-2 h-2 rounded-full ${colors[status]} animate-pulse`} />;
};

const AssetCard = ({ asset, onClick }: { asset: Asset; onClick: () => void }) => {
  const Icon = asset.plant_type === "solar" ? Sun : Wind;
  const accentColor = asset.plant_type === "solar" ? "hsl(var(--solar))" : "hsl(var(--wind))";

  return (
    <div
      className="p-6 border border-border bg-card flex flex-col justify-between transition-all hover:bg-accent/5 cursor-pointer group"
      style={{ boxShadow: "var(--shadow-soft)" }}
      onClick={onClick}
    >
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-sm bg-background border border-border group-hover:border-primary/50 transition-colors">
            <Icon className="w-4 h-4" style={{ color: accentColor }} />
          </div>
          <div>
            <h4 className="font-serif text-lg leading-tight">{asset.name}</h4>
            <p className="font-mono text-[9px] tracking-[0.2em] text-muted-foreground uppercase">{asset.district}</p>
          </div>
        </div>
        <StatusLight status={asset.status} />
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className="font-serif text-3xl">{asset.capacity_mw}</span>
        <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">MW Cap</span>
      </div>
    </div>
  );
};

const AssetModal = ({ asset, onClose }: { asset: Asset; onClose: () => void }) => {
  const [plantStats, setPlantStats] = React.useState({ peak: 0, avg: 0, totalEnergyMWh: 0 });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-background/95 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="bg-[#FAF8F6] border border-border/50 w-full max-w-5xl h-[90vh] flex flex-col shadow-2xl animate-in zoom-in-95 duration-300 overflow-hidden rounded-sm">
        {/* Header - Matches Image exactly */}
        <div className="p-10 pb-4 flex justify-between items-start">
          <div className="space-y-2 max-w-3xl">
            <h2 className="font-serif text-3xl text-foreground/90">Plant Overview</h2>
            <p className="text-muted-foreground text-[13px] leading-relaxed font-sans max-w-xl opacity-90">
              {asset.description || "Operational generation node providing grid stability and clean energy throughput to the regional load despatch center."}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-accent/10 rounded-full transition-colors group">
            <X className="w-6 h-6 text-muted-foreground group-hover:text-foreground" />
          </button>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Main Visualization Section */}
          <div className="flex-1 px-10 py-4 flex flex-col overflow-y-auto">
            <div className="flex-1 mb-10">
              <LiveGraph 
                plant_id={asset.plant_id} 
                capacity_mw={asset.capacity_mw} 
                plant_type={asset.plant_type}
                onDataUpdate={setPlantStats}
              />
            </div>

            {/* Metrics Grid - Matches Image Aesthetic */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
              <MetricBox 
                label="Peak Generation" 
                value={`${plantStats.peak.toFixed(2)} MW`} 
                sub="Today's Max"
              />
              <MetricBox 
                label="Avg Output" 
                value={`${plantStats.avg.toFixed(2)} MW`} 
                sub="Last 24h"
              />
              <MetricBox 
                label="Energy Generated Till Now" 
                value={`${plantStats.totalEnergyMWh.toFixed(2)} MWh`} 
                sub="Today's Total"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const MetaRow = ({ label, value }: { label: string; value: string }) => (
  <div className="space-y-1">
    <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">{label}</div>
    <div className="font-serif text-base">{value}</div>
  </div>
);

const MetricBox = ({ label, value, sub }: { label: string; value: string; sub: string }) => (
  <div className="p-8 border border-border/40 bg-white/50 flex flex-col justify-between">
    <div>
      <div className="font-mono text-[9px] tracking-[0.25em] text-muted-foreground uppercase mb-6">{label}</div>
      <div className="font-serif text-4xl text-foreground/90">{value}</div>
    </div>
    <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-[0.15em] mt-2">{sub}</div>
  </div>
);


export const Assets = () => {
  const [selectedAsset, setSelectedAsset] = React.useState<Asset | null>(null);


  return (
    <section className="container mx-auto px-6 lg:px-10 pt-12 pb-16 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-12">
        <div>
          <div className="font-mono text-[10px] tracking-[0.3em] text-muted-foreground uppercase mb-2">— Assets · Generation Nodes</div>
          <h2 className="font-serif text-4xl">Grid Infrastructure</h2>
        </div>

      </div>

      <div className="space-y-16">
        <div>
          <div className="flex items-center gap-3 mb-8">
            <Sun className="w-5 h-5 text-solar" />
            <h3 className="font-serif text-2xl uppercase tracking-tight">Solar Photovoltaic</h3>
            <div className="flex-grow h-px bg-border/50 ml-4" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {solarAssets.map((asset) => (
              <AssetCard key={asset.plant_id} asset={asset} onClick={() => setSelectedAsset(asset)} />
            ))}
          </div>
        </div>

        <div>
          <div className="flex items-center gap-3 mb-8">
            <Wind className="w-5 h-5 text-wind" />
            <h3 className="font-serif text-2xl uppercase tracking-tight">Wind Turbines</h3>
            <div className="flex-grow h-px bg-border/50 ml-4" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {windAssets.map((asset) => (
              <AssetCard key={asset.plant_id} asset={asset} onClick={() => setSelectedAsset(asset)} />
            ))}
          </div>
        </div>
      </div>

      {selectedAsset && <AssetModal asset={selectedAsset} onClose={() => setSelectedAsset(null)} />}
    </section>
  );
};
