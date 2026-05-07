import { useState } from "react";
import { Menu, X } from "lucide-react";

const tabs = ["Dashboard", "Assets", "Forecast", "Analysis"];

export const Navbar = ({ active, setActive }: { active: string; setActive: (t: string) => void }) => {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 bg-background/85 backdrop-blur-md border-b border-border">
      <div className="container mx-auto px-6 lg:px-10">
        <nav className="flex items-center justify-between h-16">
          <a href="#" className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-sm bg-primary flex items-center justify-center font-mono text-xs font-bold text-primary-foreground">EP</div>
            <div className="leading-none">
              <div className="text-[15px] font-semibold tracking-tight">EcoPower</div>
              <div className="text-[10px] text-muted-foreground tracking-[0.2em] uppercase mt-0.5">Intelligence</div>
            </div>
          </a>

          <ul className="hidden md:flex items-center gap-8">
            {tabs.map((t) => (
              <li key={t}>
                <button
                  onClick={() => setActive(t)}
                  className={`relative text-sm font-medium transition-colors py-2 ${
                    active === t ? "text-primary" : "text-muted-foreground hover:text-primary"
                  }`}
                >
                  {t}
                  {active === t && <span className="absolute -bottom-[1px] left-0 right-0 h-px bg-accent" />}
                </button>
              </li>
            ))}
          </ul>


          <button className="md:hidden" onClick={() => setOpen(!open)} aria-label="Menu">
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </nav>

        {open && (
          <div className="md:hidden border-t border-border py-4 space-y-1">
            {tabs.map((t) => (
              <button
                key={t}
                onClick={() => { setActive(t); setOpen(false); }}
                className={`block w-full text-left px-3 py-2 text-sm ${
                  active === t ? "text-primary font-medium" : "text-muted-foreground"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  );
};

