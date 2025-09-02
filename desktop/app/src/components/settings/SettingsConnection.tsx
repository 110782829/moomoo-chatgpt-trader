import { useEffect, useState } from "react";
import { NiceSelect } from "../../App";
import api from "../../api";

export default function SettingsConnection({
  host, setHost,
  port, setPort,
  clientId, setClientId,
  accountId, setAccountId,
  trdEnv, setTrdEnv,
  doConnect,
  doSelect,
  connected,
  activeAccount,
  toast,
}: any) {
  const [execMode, setExecMode] = useState<"sim"|"moomoo">("sim");

  useEffect(() => {
    api.getExecMode().then(r => setExecMode((r as any)?.mode || "sim")).catch(() => {});
  }, []);

  function changeExec(m: "sim"|"moomoo") {
    api.putExecMode(m)
      .then(() => { setExecMode(m); toast.show("Exec mode saved."); })
      .catch((e: any) => toast.show(String(e)));
  }

  async function connectAccount() {
    await doConnect();
    await doSelect();
  }
  return (
    <>
      <div className="help" style={{marginBottom:8}}>
        {connected ? "Connected" : "Not connected"} • {activeAccount?.account_id || "—"} {activeAccount?.trd_env ? `• ${activeAccount.trd_env}` : ""}
      </div>
      <div className="form-row">
        <div><div className="label">Host</div><input className="input" value={host} onChange={e=>setHost(e.target.value)} /></div>
        <div><div className="label">Port</div><input className="input" type="number" value={port} onChange={e=>setPort(parseInt(e.target.value)||0)} /></div>
        <div><div className="label">Client ID</div><input className="input" type="number" value={clientId} onChange={e=>setClientId(parseInt(e.target.value)||1)} /></div>
      </div>
      <div className="form-row" style={{marginTop:12}}>
        <div>
          <div className="label">Account ID</div>
          <input className="input" value={accountId} onChange={e=>setAccountId(e.target.value)} placeholder="e.g., 54871" />
        </div>
        <div>
          <div className="label">Trading Env</div>
          <NiceSelect
            value={trdEnv}
            onChange={(v)=>setTrdEnv((v === "REAL" ? "REAL" : "SIMULATE") as any)}
            options={[
              { value: "SIMULATE", label: "SIMULATE" },
              { value: "REAL", label: "REAL" },
            ]}
            width="100%"
          />
        </div>
        <div>
          <div className="label">Execution</div>
          <NiceSelect
            value={execMode}
            onChange={(v)=>changeExec(v as "sim"|"moomoo")}
            options={[
              { value: "sim", label: "Sim" },
              { value: "moomoo", label: "Moomoo" },
            ]}
            width="100%"
          />
        </div>
      </div>
      <div className="row" style={{marginTop:8}}>
        <button className="btn brand" onClick={connectAccount}>Connect Account</button>
      </div>
    </>
  );
}
