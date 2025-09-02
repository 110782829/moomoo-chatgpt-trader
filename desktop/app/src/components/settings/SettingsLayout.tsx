import { type ReactElement, type ReactNode, type CSSProperties } from "react";

export interface Section {
  id: string;
  title: string;
  element: ReactElement;
}

export function SectionCard({ id, title, children, style }: { id: string; title: string; children: ReactNode; style?: CSSProperties }) {
  return (
    <section id={id} style={{ scrollMarginTop: 20, display: "flex", ...style }}>
      {/* Panel fills height */}
      <div className="panel" style={{ flex: 1 }}>
        {/* parent gap controls spacing */}
        <h2 style={{ marginTop: 0 }}>{title}</h2>
        {children}
      </div>
    </section>
  );
}

export default function SettingsLayout({ sections }: { sections: Section[] }) {
  return (
    <div className="stack">
      {sections.map(s => (
        <SectionCard key={s.id} id={s.id} title={s.title}>
          {s.element}
        </SectionCard>
      ))}
    </div>
  );
}
