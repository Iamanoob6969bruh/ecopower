export const Footer = () => (
  <footer className="border-t border-border">
    <div className="container mx-auto px-6 lg:px-10 py-10 grid md:grid-cols-4 gap-8 text-sm">
      <div>
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-7 h-7 rounded-sm bg-primary flex items-center justify-center font-mono text-[10px] font-bold text-primary-foreground">EP</div>
          <span className="font-semibold">EcoPower Intelligence</span>
        </div>
        <p className="text-muted-foreground text-xs leading-relaxed">Forecasting the future of renewable energy, one watt at a time.</p>
      </div>
      <FooterCol title="Product" items={["Dashboard", "Assets", "Forecast", "Analysis"]} />
      <FooterCol title="Company" items={["About", "Methodology", "Careers", "Press"]} />
      <FooterCol title="Resources" items={["Documentation", "API", "Status", "Contact"]} />
    </div>
    <div className="border-t border-border">
      <div className="container mx-auto px-6 lg:px-10 py-5 flex flex-col md:flex-row justify-between gap-2 font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
        <span>© 2026 EcoPower Intelligence</span>
        <span>Made with care · Stockholm · Nagpur</span>
      </div>
    </div>
  </footer>
);

const FooterCol = ({ title, items }: { title: string; items: string[] }) => (
  <div>
    <div className="font-mono text-[10px] tracking-[0.25em] text-muted-foreground uppercase mb-4">{title}</div>
    <ul className="space-y-2">
      {items.map((i) => (
        <li key={i}><a href="#" className="hover:text-accent transition-colors">{i}</a></li>
      ))}
    </ul>
  </div>
);
