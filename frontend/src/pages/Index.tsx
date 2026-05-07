import { useState } from "react";
import { Navbar } from "@/components/Navbar";
import { Dashboard } from "@/components/Dashboard";
import { ForecastPanel } from "@/components/ForecastPanel";
import { Assets } from "@/components/Assets";
import { Forecast } from "@/components/Forecast";
import { Analysis } from "@/components/Analysis";


const Index = () => {
  const [activeTab, setActiveTab] = useState("Dashboard");

  return (
    <main className="min-h-screen bg-background">
      <Navbar active={activeTab} setActive={setActiveTab} />
      {activeTab === "Dashboard" && (
        <>
          <Dashboard />
          <ForecastPanel />
        </>
      )}
      {activeTab === "Assets" && <Assets />}
      {activeTab === "Forecast" && <Forecast />}
      {activeTab === "Analysis" && <Analysis />}
    </main>
  );
};



export default Index;

