import { useEffect, useState } from "react";
import api from "../../api";
import { useLocalStorage } from "../../App";

export default function SettingsPreferences({ toast }: any) {
  const [raw, setRaw] = useLocalStorage<string>("pref.nl.raw", "");
  const [summary, setSummary] = useState<string>("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    api
      .getAutoStyle()
      .then(r => {
        setRaw(r.raw || "");
        setSummary(r.summary || "");
        setDirty(false);
      })
      .catch(() => {});
  }, []);

  async function save() {
    const r = await api.postAutoStyle(raw);
    setSummary(r.summary || "");
    setDirty(false);
    toast.show("Style saved.");
  }

  async function reset() {
    const r = await api.deleteAutoStyle();
    setRaw(r.raw || "");
    setSummary(r.summary || "");
    setDirty(false);
  }

  // Build bullet list from summary text
  const summaryLines = summary
    .split(/\n+/)
    .map(s => s.replace(/^[•*-]\s*/, "").trim())
    .filter(Boolean);

  return (
    <div className="pref-card">
      <div className="pref-grid">
        <textarea
          className="input pref-input"
          value={raw}
          onChange={e => {
            setRaw(e.target.value);
            setDirty(true);
          }}
          placeholder="Describe tone, formatting, constraints..."
        />
        <div className="pref-summary">
          <div className="subtitle">GPT will note:</div>
          {summaryLines.length ? (
            <ul>
              {summaryLines.map((line, idx) => (
                <li key={idx}>{line}</li>
              ))}
            </ul>
          ) : (
            <div className="help">No summary yet.</div>
          )}
        </div>
      </div>
      <div className="pref-actions">
        <span className="pref-count">{raw.length} chars</span>
        <button className="btn brand" onClick={save} disabled={!dirty}>
          Save
        </button>
        <button className="btn" onClick={reset}>Reset</button>
      </div>
    </div>
  );
}

