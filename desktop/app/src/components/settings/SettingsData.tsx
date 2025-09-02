import { useEffect, useState } from "react";
import { NiceSelect } from "../../App";
import api from "../../api";

export default function SettingsData({ toast }: any) {
  const [ktype, setKtype] = useState("K_DAY");
  const [barsTtl, setBarsTtl] = useState(60);
  const [dealsSync, setDealsSync] = useState(180);
  const [dataSource, setDataSource] = useState("futu");
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => {
    try {
      const d = await api.getDataSettings();
      setKtype(String(d.ktype||"K_DAY"));
      setBarsTtl(Number(d.bars_ttl_sec||60));
      setDealsSync(Number(d.deals_sync_sec||180));
      setDataSource(String(d.data_source||"futu"));
    } catch {}
  })(); }, []);

  async function save() {
    setSaving(true);
    try { await api.putDataSettings({ ktype, bars_ttl_sec: Number(barsTtl)||60, deals_sync_sec: Number(dealsSync)||180, data_source: dataSource }); toast.show("Data settings saved."); }
    catch(e:any){ toast.show(String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="form-row data-grid">{/* 3 rows x 2 columns */}
      <div>
        <div className="label">K-Type</div>
        <NiceSelect value={ktype} onChange={setKtype} options={[{value:"K_DAY",label:"K_DAY"},{value:"K_1M",label:"K_1M"},{value:"K_5M",label:"K_5M"}]} width="100%" />
      </div>
      <div>
        <div className="label">Bars TTL (sec)</div>
        <input className="input" type="number" value={barsTtl} onChange={e=>setBarsTtl(parseInt(e.target.value)||0)} />
      </div>
      <div>
        <div className="label">Deals sync (sec)</div>
        <input className="input" type="number" value={dealsSync} onChange={e=>setDealsSync(parseInt(e.target.value)||0)} />
      </div>
      <div>
        <div className="label">Data Source</div>
        <NiceSelect
          value={dataSource}
          onChange={setDataSource}
          options={[{value:"futu",label:"Moomoo"},{value:"yfinance",label:"Yahoo Finance"}]}
          width="100%"
        />
      </div>
      {/* action buttons */}
      <div style={{ display:"flex", alignItems:"flex-start", marginTop:10 }}>
        <button
          className="btn"
          style={{ width:"100%" }}
          onClick={() =>
            api
              .syncDealsNow()
              .then(() => toast.show("Sync triggered"))
              .catch((e: any) => toast.show(String(e)))
          }
        >
          Sync Deals Now
        </button>
      </div>
      <div style={{ display:"flex", alignItems:"flex-start", marginTop:10 }}>
        <button
          className="btn brand"
          style={{ width:"100%" }}
          onClick={save}
          disabled={saving}
        >
          {saving ? "Saving…" : "Save Data Settings"}
        </button>
      </div>
    </div>
  );
}
