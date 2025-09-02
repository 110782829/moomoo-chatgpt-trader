import { useEffect, useState } from "react";
import api from "../../api";

export default function SettingsAdvanced({ toast }: any) {
  const [status, setStatus] = useState<any>(null);
  useEffect(() => { api.sessionStatus().then(setStatus).catch(()=>{}); }, []);
  return (
    <div className="stack">
      <div className="row" style={{gap:8}}>
        <button className="btn" onClick={()=>api.sessionClear().then(()=>toast.show("Session cleared.")).catch((e:any)=>toast.show(String(e)))}>Clear Session</button>
      </div>
      <details style={{marginTop:8}}>
        <summary>Session Status JSON</summary>
        <pre style={{whiteSpace:"pre-wrap", fontSize:12}}>{JSON.stringify(status,null,2)}</pre>
      </details>
    </div>
  );
}
