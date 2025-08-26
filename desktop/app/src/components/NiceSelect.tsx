import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";

type Opt = { value: string; label: string };

function useOutsideClose<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); };
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", h, true);
    document.addEventListener("keydown", k, true);
    return () => { document.removeEventListener("mousedown", h, true); document.removeEventListener("keydown", k, true); };
  }, [open, onClose]);
  return ref;
}

function useAnchorPosition(trigger: HTMLElement | null, open: boolean, menuMaxH = 260) {
  const [pos, setPos] = useState<{ left: number; top: number; width: number; openUp: boolean }>({ left: 0, top: 0, width: 0, openUp: false });
  useEffect(() => {
    if (!open || !trigger) return;
    const el: HTMLElement = trigger;
    function place() {
      const r = el.getBoundingClientRect();
      const width = Math.max(r.width, 160);
      let left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
      let top = r.bottom + 6;
      let openUp = false;
      if (top + menuMaxH > window.innerHeight - 8) {
        openUp = true;
        top = Math.max(8, r.top - 6 - menuMaxH);
      }
      setPos({ left, top, width, openUp });
    }
    place();
    const opts: AddEventListenerOptions = { passive: true };
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place, opts);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, trigger, menuMaxH]);
  return pos;
}

export function NiceSelect({
  value, onChange, options, width = 160, placeholder = "Select…",
}: { value: string; onChange: (v: string) => void; options: Opt[]; width?: number; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const outsideRef = useOutsideClose<HTMLDivElement>(open, () => setOpen(false));
  const pos = useAnchorPosition(btnRef.current ?? null, open);
  const current = options.find(o => o.value === value);
  return (
    <div className="custom-select" ref={wrapRef} style={{ width }}>
      <button className="custom-trigger" ref={btnRef} type="button" onClick={() => setOpen(o => !o)}>
        {current?.label ?? <span style={{ color: "var(--muted)" }}>{placeholder}</span>}
      </button>
      {open && createPortal(
        <div
          ref={outsideRef}
          className="menu"
          style={{ position: "fixed", left: pos.left, top: pos.top, width: pos.width, maxHeight: 260, zIndex: 10000 }}
        >
          {options.map(o => (
            <div
              key={o.value}
              className={`item ${o.value === value ? "active" : ""}`}
              onClick={() => { onChange(o.value); setOpen(false); }}
            >
              {o.label}
            </div>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}

export function NiceCombobox({
  value, onChange, options, width = 200, placeholder = "Search…",
}: { value: string; onChange: (v: string) => void; options: Opt[]; width?: number; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const outsideRef = useOutsideClose<HTMLDivElement>(open, () => setOpen(false));
  const pos = useAnchorPosition(btnRef.current, open);
  const current = options.find(o => o.value === value);
  const filtered = q ? options.filter(o => o.label.toLowerCase().includes(q.toLowerCase()) || o.value.toLowerCase().includes(q.toLowerCase())) : options;
  return (
    <div className="custom-select" style={{ width }}>
      <button className="custom-trigger" ref={btnRef} type="button" onClick={() => setOpen(o => !o)}>
        {current?.label ?? <span style={{ color: "var(--muted)" }}>Select…</span>}
      </button>
      {open && createPortal(
        <div
          ref={outsideRef}
          className="menu"
          style={{ position: "fixed", left: pos.left, top: pos.top, width: pos.width, maxHeight: 260, zIndex: 10000 }}
        >
          <input className="search" autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder={placeholder} />
          {filtered.length ? filtered.map(o => (
            <div
              key={o.value}
              className={`item ${o.value === value ? "active" : ""}`}
              onClick={() => { onChange(o.value); setOpen(false); setQ(""); }}
            >
              {o.label}
            </div>
          )) : <div className="item" style={{ color: "var(--muted)" }}>No matches</div>}
        </div>,
        document.body
      )}
    </div>
  );
}
