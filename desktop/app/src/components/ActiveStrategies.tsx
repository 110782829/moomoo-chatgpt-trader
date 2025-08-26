import { useEffect, useState } from "react";
import { GET, SEND } from "../lib/api";

/** List of running strategies */
export function ActiveStrategies({ onStopped, refreshKey }: { onStopped?: () => void; refreshKey?: number }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { refresh(); }, []);
  useEffect(() => { refresh(); }, [refreshKey]);

  async function refresh() {
    try {
      setLoading(true);
      const ls = await GET<any[]>("/automation/strategies");
      setItems(ls || []);
    } finally {
      setLoading(false);
    }
  }

  async function stop(id: number) {
    try {
      await SEND(`/automation/stop/${id}`, {}, "POST");
      onStopped?.();
      refresh();
    } catch {}
  }

  return (
    <div className="stack">
      <div className="row">
        <button className="btn" onClick={refresh}>{loading ? "Refreshing…" : "Refresh"}</button>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr>{["id","name","symbol","active","actions"].map(h => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>
            {(items?.length ? items : []).map((s: any) => (
              <tr key={s.id}>
                <td>{s.id}</td><td>{s.name}</td><td>{s.symbol}</td>
                <td>{String(s.active)}</td>
                <td>{s.active && <button className="btn red" onClick={() => stop(Number(s.id))}>Stop</button>}</td>
              </tr>
            ))}
            {!items?.length && <tr><td>No strategies</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

