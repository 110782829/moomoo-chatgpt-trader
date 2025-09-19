import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, GET, SEND } from "../api";
import api from "../api";

export default function AssistantMemory() {
  const [memory, setMemory] = useState("");
  const [style, setStyle] = useState("");
  const [chatLen, setChatLen] = useState(0);
  const [preset, setPreset] = useState("al_brooks");
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState(false);
  const editRef = useRef<HTMLDivElement|null>(null);
  const draftRef = useRef<string>("");

  const load = useCallback(async () => {
    try {
      const r = await GET<{ memory: string; style_summary: string; chat_len: number }>("/assistant/memory");
      setMemory(r.memory||""); setStyle(r.style_summary||""); setChatLen(r.chat_len||0);
    } catch {}
    draftRef.current = ""; setEdit(false);
  }, []);
  useEffect(()=>{ load(); }, [load]);

  useEffect(() => {
    const handler = () => { load(); };
    window.addEventListener("assistant-memory-updated", handler);
    return () => window.removeEventListener("assistant-memory-updated", handler);
  }, [load]);

  // When entering edit mode, focus and place caret at end on first click
  useEffect(() => {
    if (edit && editRef.current) {
      const el = editRef.current;
      // Focus and set caret to end
      requestAnimationFrame(() => {
        try {
          el.focus();
          const range = document.createRange();
          range.selectNodeContents(el);
          range.collapse(false);
          const sel = window.getSelection();
          sel?.removeAllRanges();
          sel?.addRange(range);
        } catch {}
      });
    }
  }, [edit]);

  async function clearAll() {
    setBusy(true);
    try { await SEND("/assistant/memory", {}, "DELETE"); await load(); } finally { setBusy(false); }
  }

  async function applyPreset() {
    setBusy(true);
    try { await SEND("/assistant/preset", { preset }); await load(); } finally { setBusy(false); }
  }

  async function saveEdit() {
    // read innerText from ref (avoid cursor jump by avoiding state during typing)
    const text = (editRef.current?.innerText || draftRef.current || "").trim();
    setBusy(true);
    try { await api.setStyleSummary(text); } finally { setBusy(false); }
    setEdit(false);
    await load();
  }

  function onEditableInput(e: React.FormEvent<HTMLDivElement>) {
    draftRef.current = (e.currentTarget as HTMLDivElement).innerText;
  }

  function onEditableKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      saveEdit();
    }
  }

  return (
    <div className="stack" style={{display:"grid", gap:8}}>
      <div style={{display:"flex",justifyContent:"flex-end",alignItems:"center"}}>
        <div className="help">chat history: {chatLen}</div>
      </div>
      <div className="row" style={{gap:8}}>
        <div style={{flex:1}}>
          <div className="label">Persistent memory</div>
          <div className="inner-card">
            <pre className="style-block">{memory||"(empty)"}</pre>
          </div>
        </div>
        <div style={{flex:1}}>
          <div className="label">Style summary (used by bot)</div>
          <div className={`inner-card ${edit? 'editing':''}`}>
            {!edit ? (
              <pre className="style-block" onClick={()=>{ draftRef.current = style; setEdit(true); }} title="Click to edit" style={{cursor:'text'}}>{style||"(empty)"}</pre>
            ) : (
              <div ref={editRef} contentEditable className="editable-content" suppressContentEditableWarning={true}
                   onInput={onEditableInput} onBlur={saveEdit} onKeyDown={onEditableKeyDown}>
                {draftRef.current || style}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="row" style={{gap:8,alignItems:"end"}}>
        <div>
          <div className="label">Preset</div>
          <select className="select" value={preset} onChange={e=>setPreset(e.target.value)}>
            <option value="al_brooks">Al Brooks (price action)</option>
            <option value="trend_follow">Trend Follow</option>
            <option value="mean_revert">Mean Reversion</option>
            <option value="long_bias">Long Bias</option>
            <option value="short_bias">Short Bias</option>
          </select>
        </div>
        <button className="btn brand" onClick={applyPreset} disabled={busy}>Apply Preset</button>
        <button className="btn red" onClick={clearAll} disabled={busy}>Clear Memory</button>
        {/* Auto‑save on Enter/blur; no explicit buttons */}
      </div>
    </div>
  );
}
