// Desktop UI with connection panel, strategy catalog, status, logs, settings, and activity log.
// API base comes from VITE_API_BASE (defaults to http://127.0.0.1:8000)

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from "react-dom";
import api, { API_BASE, SEND, GET } from "./api";
import { SectionCard } from "./components/settings/SettingsLayout";
import SettingsConnection from "./components/settings/SettingsConnection";
import SettingsRisk from "./components/settings/SettingsRisk";
import SettingsData from "./components/settings/SettingsData";
import SettingsSignals from "./components/settings/SettingsSignals";
import SettingsPlanner from "./components/settings/SettingsPlanner";
import SettingsTrading from "./components/settings/SettingsTrading";
import SettingsWatchlist from "./components/settings/SettingsWatchlist";
import SettingsNews from "./components/settings/SettingsNews";
import AssistantChat from "./components/AssistantChat";
import AssistantMemory from "./components/AssistantMemory";
import WatchlistTrends from "./components/status/WatchlistTrends";

// ---------- Styles ----------
const css = `
:root {
  --bg:#0b0d11; --panel:#12161c; --card:#161b22; --muted:#94a3b8; --text:#e5e7eb; --text-dim:#cbd5e1;
  --brand:#7c3aed; --brand2:#06b6d4; --red:#ef4444; --amber:#f59e0b; --green:#22c55e; --border:#1f2937; --hover:#0f172a;
}
*{box-sizing:border-box} html,body,#root{height:100%}
body{margin:0;background:var(--bg);
 color:var(--text); font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}
.app{max-width:1180px;margin:0 auto;padding:28px 20px 28px}
.header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
.title{display:flex;align-items:center;gap:12px}
.badge{font-size:12px;color:var(--text-dim);background:linear-gradient(135deg, rgba(124,58,237,.25), rgba(6,182,212,.25));
  border:1px solid rgba(124,58,237,.35);padding:4px 8px;border-radius:8px}
.badge.good{color:var(--green);border-color:rgba(16,185,129,.45);background:linear-gradient(135deg, rgba(16,185,129,.18), rgba(16,185,129,.06))}
.badge.bad{color:var(--red);border-color:rgba(239,68,68,.45);background:linear-gradient(135deg, rgba(239,68,68,.18), rgba(239,68,68,.06))}
.tabs{display:flex;gap:8px;margin:8px 0 18px}
.tab{padding:8px 12px;border-radius:8px;background:var(--panel);color:var(--text-dim);
  border:1px solid var(--border);cursor:pointer;transition:.18s ease}
.tab:hover{background:var(--hover)}
.tab.active{color:var(--text);background:linear-gradient(180deg, rgba(124,58,237,.25), rgba(6,182,212,.25));border-color:rgba(124,58,237,.45)}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap: 8px}
@media (max-width:900px){.grid-3{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px}
.card-lg{padding:18px}
.card h3{margin:0 0 6px;font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.card .value{font-size:20px;font-weight:600}
.row{display:flex;gap:12px;flex-wrap:wrap}
.stack{display:grid;gap: 8px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:8px 12px;border-radius:10px;border:1px solid var(--border);
  background:#0e1320;color:var(--text);cursor:pointer;transition:transform .04s ease, background .18s ease;user-select:none}
.btn[disabled]{opacity:.55;cursor:not-allowed}
.btn:hover{background:var(--hover)} .btn:active{transform:translateY(1px)}
.btn.brand{background:linear-gradient(180deg, rgba(124,58,237,.5), rgba(6,182,212,.4));border-color:rgba(124,58,237,.5)}
.btn.red{background:linear-gradient(180deg, rgba(239,68,68,.25), rgba(239,68,68,.15));border-color:rgba(239,68,68,.4);color:var(--red)}
/* solid red button */
.btn.red-solid{background:linear-gradient(180deg,#7f1d1d,#651616);border-color:#8b2020;color:#fff;border-radius:12px}
.btn.red-solid:hover{background:#8b2020}
.btn.amber{background:linear-gradient(180deg, rgba(245,158,11,.25), rgba(245,158,11,.15));border-color:rgba(245,158,11,.4)}
.input,.select{width:100%;padding:8px 10px;border-radius:8px;background:#0c111b;color:var(--text);border:1px solid var(--border);outline:none;transition:border-color .18s}
.input:focus,.select:focus{border-color:rgba(124,58,237,.6)}
/* Symbol search: consistent across tables/logs */
.input.search{
  padding-left: 28px;                   /* room for icon */
  background-image: url('data:image/svg+xml;utf8,<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="11" cy="11" r="7" stroke="%23cbd5e1" stroke-width="2"/><path d="M20 20l-3.5-3.5" stroke="%23cbd5e1" stroke-width="2" stroke-linecap="round"/></svg>');
  background-repeat:no-repeat;
  background-position: 8px 50%;
  background-size: 16px 16px;
}
.input.search:focus{ border-color: var(--border); box-shadow:none; }

.select {
  -webkit-appearance: none;
  appearance: none;
  background-image: url('data:image/svg+xml;utf8,<svg width="12" height="12" viewBox="0 0 20 20" fill="%23cbd5e1" xmlns="http://www.w3.org/2000/svg"><path d="M5.25 7.5l4.75 5 4.75-5" stroke="%23cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');
  background-repeat: no-repeat;
  background-position: right 8px center;
  background-size: 12px 12px;
  padding-right: 28px;
}
.select::-ms-expand { display: none; }

/* Subtle motion */
@keyframes fadeSlide {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.panel { animation: fadeSlide .18s ease both; }
.btn { transition: transform .06s ease, box-shadow .18s ease, background .18s ease; }
.btn:hover { box-shadow: 0 6px 18px rgba(0,0,0,.24); }
.btn:active { transform: translateY(1px) scale(.99); }

/* Scrollbars (WebKit) */
.table-wrap::-webkit-scrollbar, .menu::-webkit-scrollbar { width: 8px; height: 8px; }
.table-wrap::-webkit-scrollbar-thumb, .menu::-webkit-scrollbar-thumb {
  background: rgba(124,58,237,.35);
  border-radius: 10px;
}
.table-wrap::-webkit-scrollbar-thumb:hover, .menu::-webkit-scrollbar-thumb:hover {
  background: rgba(124,58,237,.6);
}

/* Custom dropdown (NiceSelect / NiceCombobox) */
.custom-select { position: relative; display: inline-block; }
.custom-trigger {
  width: 100%;
  min-height: 34px;
  background: #0c111b;
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 10px;
  padding: 8px 28px 8px 10px;
  text-align: left;
  cursor: pointer;
}
.custom-trigger:hover { background: var(--hover); }
.custom-trigger:after {
  content: "";
  position: absolute; right: 10px; top: 50%; width: 12px; height: 12px; transform: translateY(-50%);
  background-image: url('data:image/svg+xml;utf8,<svg width="12" height="12" viewBox="0 0 20 20" fill="%23cbd5e1" xmlns="http://www.w3.org/2000/svg"><path d="M5.25 7.5l4.75 5 4.75-5" stroke="%23cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');
  background-size: 12px 12px; background-repeat: no-repeat;
}
.menu {
  position: absolute; left: 0; right: 0; z-index: 50; margin-top: 6px;
  background: rgba(16,20,31,.98);
  border: 1px solid var(--border); border-radius: 12px; padding: 6px;
  box-shadow: 0 16px 40px rgba(0,0,0,.35);
  max-height: 260px; overflow: auto; animation: fadeSlide .16s ease both;
  backdrop-filter: blur(6px);
}
.menu .item {
  padding: 8px 10px; border-radius: 8px; cursor: pointer;
}
  .menu .item + .item { margin-top: 6px; }
  .menu .item:hover, .menu .item.active {
    background: rgba(124,58,237,.18);
  }
  .menu .search {
    width: 100%; margin: 4px 0 6px; padding: 8px 10px;
    background: #0c111b; border: 1px solid var(--border); border-radius: 8px; color: var(--text);
  }

.label{font-size:12px;color:var(--muted);margin-bottom:6px}
.form-row{display:grid;gap:12px;grid-template-columns:repeat(3,1fr)}
.form-row.data-grid{grid-template-columns:repeat(2,1fr);grid-template-rows:repeat(3,auto)}
.form-row.save{grid-template-columns:repeat(3,1fr) auto}
@media (max-width:900px){.form-row{grid-template-columns:1fr}.form-row.save{grid-template-columns:1fr}}
.table-wrap{overflow:auto;border-radius:10px}
table{width:100%;border-collapse:collapse;background:var(--panel)}
th,td{padding:8px 10px;border-top:1px solid var(--border)} th{text-align:left;font-size:12px;color:var(--muted);background:#0f1420;position:sticky;top:0;z-index:1}
tr:hover td{background:rgba(124,58,237,.08)}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums;font-feature-settings:"tnum";white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap: 8px} @media (max-width:900px){.kpis{grid-template-columns:1fr}}
.help{color:var(--muted);font-size:12px}
.toast{position:fixed;right:16px;bottom:16px;padding:10px 12px;border-radius:10px;background:#0e1320;border:1px solid var(--border);color:var(--text);box-shadow:0 10px 30px rgba(0,0,0,.35);max-width:360px}
small.code{font-family:ui-monospace, SFMono-Regular, Menlo, monospace;background:rgba(124,58,237,.18);padding:2px 6px;border-radius:6px}
.pref-card{padding:16px;display:flex;flex-direction:column;gap:16px}
.pref-grid{display:grid;grid-template-columns:2fr 1fr;gap:16px}
@media (max-width:900px){.pref-grid{grid-template-columns:1fr}}
.pref-input{height:340px;resize:none;font-family:Inter, ui-sans-serif;line-height:1.5}
.pref-summary{height:340px;overflow-y:auto;padding:12px}
.pref-summary .subtitle{font-size:15px;color:var(--muted);margin-bottom:8px}
.pref-summary ul{margin:0;padding-left:20px;list-style:disc;font-size:16px;line-height:1.5}
.pref-actions{display:flex;justify-content:flex-end;align-items:center;gap:8px}
.pref-count{font-size:12px;color:var(--muted);margin-right:auto}

.report-layout{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:8px;align-content:start}
.report-layout>*{min-width:0}
.report-card{display:flex;flex-direction:column;gap:16px;height:100%}
.report-card h3{margin-bottom:0}
.report-card .chart-meta,.report-card .report-stats,.report-card .report-table{margin-top:0}
.report-layout>.span-12{grid-column:span 12/span 12}
.report-layout>.span-8{grid-column:span 8/span 8}
.report-layout>.span-6{grid-column:span 6/span 6}
.report-layout>.span-4{grid-column:span 4/span 4}
@media (max-width:1200px){
  .report-layout{grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}
  .report-layout>.span-8,.report-layout>.span-4{grid-column:span 6/span 6}
  .report-layout>.span-6{grid-column:span 6/span 6}
}
@media (max-width:720px){
  .report-layout{grid-template-columns:1fr;gap:8px}
  .report-layout>[class*="span-"]{grid-column:span 1/span 1}
}
.report-chart{margin-top:8px}
.report-chart svg{display:block}
.chart-axis{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-top:6px}
.chart-meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:12px}
.stat-pill{display:flex;flex-direction:column;gap:4px;padding:10px;border:1px solid var(--border);border-radius:10px;background:#0f1420}
.stat-pill .label{font-size:12px;color:var(--muted);text-transform:none;letter-spacing:0}
.stat-pill .value{font-size:16px;font-weight:600;white-space:nowrap}
.report-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:10px}
.report-table{display:grid;gap:6px;margin-top:12px}
.report-row{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border:1px solid var(--border);border-radius:10px;background:#0f1420;font-variant-numeric:tabular-nums}
.report-row .date{font-size:13px;color:var(--muted)}
.report-row .pnl{font-size:14px;font-weight:600}

.indicator{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;border:1px solid var(--border);background:#0e1320}
.dot{width:8px;height:8px;border-radius:50%}
.dot.green{background:var(--green)} .dot.red{background:var(--red)}
.header-quick{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end;min-width:320px}

.sticky-controls{position: sticky; top: 0; background: #0f1420; padding: 6px 0; z-index: 2; border-bottom: 1px solid var(--border);}
.activity .sticky-controls{ background: transparent; border-bottom: 0; }
.activity-modern{display:flex;flex-direction:column;gap:16px}
.activity-main{display:flex;flex-direction:column;gap:18px}
.activity-header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.activity-header-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.activity-toolbar{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;padding:16px;border-radius:12px;background:linear-gradient(180deg,rgba(15,23,42,.96),rgba(11,17,29,.92));border:1px solid rgba(148,163,184,.16);box-shadow:0 18px 34px rgba(2,6,23,.28)}
.activity-toolbar .field{display:flex;flex-direction:column;gap:6px}
.activity-toolbar .field .label{font-size:12px;color:var(--muted);margin:0}
.activity-toolbar .field .input,.activity-toolbar .field .select,.activity-toolbar .field .custom-trigger{margin-top:-2px}
.activity-filters-row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.activity-count{font-size:12px;color:var(--muted)}
.activity-filters{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
.filter-chip{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;border:1px solid var(--border);background:#0e1320;color:var(--muted);font-size:12px;font-weight:600;cursor:pointer;transition:background .18s ease,border-color .18s ease,color .18s ease}
.filter-chip:hover{background:var(--hover);color:var(--text)}
.filter-chip.active{background:linear-gradient(135deg,rgba(124,58,237,.3),rgba(6,182,212,.25));border-color:rgba(124,58,237,.45);color:var(--text)}
.filter-chip .count{font-size:11px;opacity:.75}
@media (max-width:600px){.activity-filters-row{flex-direction:column;align-items:flex-start}.activity-filters{margin-top:6px}}
.activity-feed{display:flex;flex-direction:column;gap:12px}
.activity-event{position:relative;display:grid;grid-template-columns:140px 1fr auto;gap:16px;padding:16px 18px;border-radius:14px;border:1px solid rgba(148,163,184,.16);background:linear-gradient(180deg,rgba(15,23,42,.96),rgba(15,23,42,.88));box-shadow:0 18px 38px rgba(2,6,23,.32);overflow:hidden}
.activity-event::before{content:"";position:absolute;left:0;top:12px;bottom:12px;width:3px;border-radius:999px;background:rgba(148,163,184,.35)}
@media (max-width:900px){.activity-event{grid-template-columns:1fr;align-items:flex-start}}
.activity-event.good::before{background:rgba(34,197,94,.7)}
.activity-event.bad::before{background:rgba(239,68,68,.7)}
.activity-event.warn::before{background:rgba(250,204,21,.7)}
.activity-event__time{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted)}
.activity-event__time .ago{font-weight:700;color:var(--text);font-size:13px}
.activity-event__body{display:flex;flex-direction:column;gap:6px}
.activity-event__body .meta-top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;color:var(--muted)}
.activity-event__body .meta-top .stage{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text);padding:4px 8px;border-radius:999px;border:1px solid rgba(148,163,184,.2);background:rgba(15,23,42,.9)}
.activity-event__body .meta-top .symbol{font-size:14px;font-weight:700;color:var(--text)}
.activity-event__body .meta-top .side{font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;text-transform:uppercase}
.activity-event__body .meta-top .side.buy{background:rgba(34,197,94,.15);color:var(--green)}
.activity-event__body .meta-top .side.sell{background:rgba(239,68,68,.15);color:var(--red)}
.activity-event__body .meta-top .side.hold{background:rgba(148,163,184,.2);color:var(--muted)}
.activity-event__body .meta-bottom{display:flex;flex-wrap:wrap;gap:6px;font-size:13px;color:var(--muted)}
.activity-event__body .meta-bottom .action{font-weight:600;color:var(--text)}
.activity-event__status{display:flex;flex-direction:column;align-items:flex-end;gap:8px;font-size:12px}
@media (max-width:900px){.activity-event__status{align-items:flex-start}}
.status.neutral{color:var(--text-dim)}
.activity-empty{padding:24px;border:1px dashed rgba(148,163,184,.25);border-radius:12px;text-align:center;color:var(--muted);font-size:13px;background:rgba(15,23,42,.75)}
.btn.ghost{background:transparent;border:1px solid rgba(148,163,184,.35);color:var(--text);padding:6px 12px;border-radius:10px;transition:background .18s ease,border-color .18s ease,color .18s ease}
.btn.ghost:hover{background:rgba(148,163,184,.12);border-color:rgba(148,163,184,.5)}
.chart-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted);margin-top:6px}
.chart-legend span{display:inline-flex;align-items:center;gap:6px}
  .note{font-size:12px;color:var(--muted)}

  .indicator{font-size:12px;font-weight:600}

  .header, .title, .header-quick{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial }
.panel h2{ margin:0 0 6px; font-size:15px; color:var(--text); text-transform:uppercase; letter-spacing:.06em }
.title-lg{ font-size:20px; }

.grid-2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap: 8px;align-items:start}
@media (max-width:980px){.grid-2{grid-template-columns:1fr}}
.badge.neutral{color:var(--text-dim);border-color:rgba(148,163,184,.3);background:rgba(15,23,42,.7)}
.watchlist-trends{display:flex;flex-direction:column;gap:12px}
.watchlist-trends__title{margin:0;color:var(--text);font-size:20px;font-weight:700}
.watchlist-trends__header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.watchlist-trends__controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.refresh-btn{background:#0c1424;border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:8px;font-size:12px;cursor:pointer;transition:background .18s ease, transform .06s ease}
.refresh-btn:hover{background:var(--hover)}
.refresh-btn:active{transform:translateY(1px)}
.refresh-btn[disabled]{opacity:.55;cursor:not-allowed}
.watchlist-error{padding:10px 12px;border-radius:10px;background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.35);color:var(--red);font-size:12px}
.watchlist-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
@media (max-width:1200px){.watchlist-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:780px){.watchlist-grid{grid-template-columns:1fr}}
.trend-card{display:flex;flex-direction:column;gap:10px;padding:14px;border-radius:12px;border:1px solid var(--border);background:var(--card);box-shadow:none}
.trend-card__head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.trend-symbol{font-size:18px;font-weight:700}
.trend-change{font-size:16px;font-weight:600}
.trend-change.down{color:var(--red)}
.trend-change.up{color:var(--green)}
.trend-chart{border-radius:12px;overflow:hidden;background:#080f1d;border:1px solid rgba(148,163,184,.16)}
.trend-svg{width:100%;height:auto;display:block}
.trend-bg{fill:#0b1324;stroke:rgba(148,163,184,.12)}
.trend-area{stroke:none}
.trend-line{stroke-width:2.2;fill:none;stroke-linecap:round;stroke-linejoin:round}
.trend-slow{fill:none;stroke-width:1.1;stroke-linecap:round;opacity:.8}
.trend-fast{fill:none;stroke-width:1.1;stroke-linecap:round;stroke-dasharray:4 6;opacity:.9}
.trend-events line{stroke-width:1.2;stroke-dasharray:4 6}
.trend-event.entry line{stroke:rgba(34,197,94,.6)}
.trend-event.exit line{stroke:rgba(245,158,11,.7)}
.trend-event.entry circle{fill:var(--green);stroke:#07101f;stroke-width:1.4}
.trend-event.exit circle{fill:var(--amber);stroke:#07101f;stroke-width:1.4}
.trend-footer{display:flex;justify-content:flex-end;align-items:center;gap:10px;font-size:11px;color:var(--muted)}
.watchlist-trends__legend{display:flex;align-items:center;gap:18px;font-size:12px;color:var(--muted);flex-wrap:wrap;margin-bottom:4px}
.watchlist-trends__legend span{display:inline-flex;align-items:center;gap:6px}
.legend-dot{display:inline-block;width:10px;height:10px;border-radius:999px;margin-right:6px;background:rgba(148,163,184,.3)}
.legend-dot.entry{background:var(--green)}
.legend-dot.exit{background:var(--amber)}
.funnel-bars{display:grid;gap:12px;margin-top:6px}
.funnel-bar-row{display:grid;grid-template-columns:1fr minmax(0,1fr) auto;gap:12px;align-items:center}
.funnel-bar-label{display:flex;flex-direction:column;gap:2px}
.funnel-bar-label .label{text-transform:uppercase;font-size:11px;letter-spacing:.08em;color:var(--muted)}
.funnel-bar-label .value{font-size:16px;font-weight:600}
.funnel-bar-track{position:relative;height:10px;border-radius:999px;background:rgba(17,24,39,.9);border:1px solid rgba(148,163,184,.15);overflow:hidden}
.funnel-bar-fill{position:absolute;inset:0;height:100%;border-radius:999px;box-shadow:0 0 12px rgba(124,58,237,.2);transition:width .3s ease}
.funnel-bar-pct{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.strategy-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.strategy-tile{display:flex;align-items:center;gap:14px;padding:12px;border-radius:12px;border:1px solid var(--border);background:rgba(14,19,30,.85)}
.strategy-radial{position:relative;width:64px;height:64px;flex:0 0 64px}
.strategy-radial svg{width:64px;height:64px;display:block}
.strategy-radial circle.bg{stroke:rgba(148,163,184,.18);stroke-width:4;fill:none}
.strategy-radial circle.fg{stroke-width:4;fill:none;stroke-linecap:round;transform:rotate(-90deg);transform-origin:50% 50%}
.strategy-radial span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600}
.strategy-tile .meta{display:flex;flex-direction:column;gap:4px}
.strategy-tile .meta .name{text-transform:uppercase;font-size:11px;color:var(--muted);letter-spacing:.08em}
.strategy-tile .meta .value{font-size:18px;font-weight:600}
.strategy-tile .meta .share{font-size:11px;color:var(--muted)}
.symbol-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}
.symbol-card{display:flex;flex-direction:column;gap:10px;padding:12px;border-radius:12px;border:1px solid var(--border);background:#0f1420;min-height:140px}
.symbol-card .header{display:flex;justify-content:space-between;align-items:center}
.symbol-card .ticker{font-size:16px;font-weight:700}
.symbol-card .status{font-size:12px;color:var(--muted)}
.symbol-card .status.active{color:#38bdf8}
.symbol-card .status.ahead{color:var(--green)}
.symbol-card .meta{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
.symbol-card .ratio{font-weight:600}
.dot-progress{display:flex;gap:4px;margin-top:6px}
.dot-progress span{width:10px;height:10px;border-radius:3px;background:rgba(148,163,184,.18);box-shadow:inset 0 0 0 1px rgba(148,163,184,.25)}
.dot-progress span.active{background:linear-gradient(135deg, rgba(96,165,250,.8), rgba(14,165,233,.7));box-shadow:none}
.timeline{position:relative;display:flex;flex-direction:column;gap:12px;padding-left:18px;margin-top:6px}
.timeline::before{content:"";position:absolute;left:6px;top:6px;bottom:6px;width:1px;background:rgba(148,163,184,.22)}
.timeline-item{position:relative;padding-left:10px}
.timeline-item::before{content:"";position:absolute;left:-10px;top:6px;width:12px;height:12px;border-radius:50%;background:linear-gradient(180deg,rgba(248,113,113,.6),rgba(244,114,182,.45));box-shadow:0 0 0 3px rgba(10,14,24,1)}
.timeline-item .title{font-weight:600;font-size:13px}
.timeline-item .meta{font-size:12px;color:var(--muted);margin-top:2px}
.guardrail-list{display:grid;gap:8px;margin-top:6px}
.guardrail-entry{padding:10px;border-radius:10px;border:1px solid rgba(148,163,184,.18);background:rgba(12,18,30,.9);display:flex;flex-direction:column;gap:4px}
.guardrail-entry .row{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
.guardrail-entry .reason{font-size:13px;font-weight:600;color:var(--text)}
  .panel.thick{padding:22px}
  /* Autopilot toggle */
  .autopilot-toggle{display:inline-flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;padding:7px 12px;border-radius:8px;cursor:pointer;border:1px solid rgba(239,68,68,.45);background:linear-gradient(135deg, rgba(239,68,68,.18), rgba(239,68,68,.06));color:var(--red);transition:transform .06s ease,border-color .18s ease;width:170px}
.autopilot-toggle.on{border-color:rgba(16,185,129,.45);color:var(--green);background:linear-gradient(135deg, rgba(16,185,129,.18), rgba(16,185,129,.06))}
  .autopilot-toggle:active{transform:translateY(1px)}

  /* Align panels to KPI layout */
  .panels3{display:grid;grid-template-columns:repeat(3, minmax(0,1fr));gap: 8px}
.panels3 .span-2{grid-column:span 2 / span 2}
@media (max-width:980px){.panels3{grid-template-columns:1fr}.panels3 .span-2{grid-column:auto}}

.panels2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap: 8px}
.panels2.w23{grid-template-columns:2fr 3fr}
@media (max-width:980px){.panels2{grid-template-columns:1fr}.panels2.w23{grid-template-columns:1fr}}

  /* Fixed gradient overlay to avoid scroll seams */
.bgfx{position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:
    radial-gradient(1200px 600px at 20% -10%, rgba(139,92,246,.12), transparent 60%),
    radial-gradient(1000px 500px at 100% 0%, rgba(34,211,238,.10), transparent 60%);

}

/* --- Assistant chat styles --- */
.chatbox{display:grid;grid-template-rows:1fr auto;gap:8px;background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:12px}
.chat-list{overflow:auto;height:520px;display:flex;flex-direction:column;gap:10px;padding:4px}
.msg{display:flex}
.msg.user{justify-content:flex-end}
.msg.assistant{justify-content:flex-start}
.bubble-block{display:flex;flex-direction:column;max-width:72%}
.msg.user .bubble-block{max-width:88%; min-width:40%; align-items:flex-end}
.bubble{max-width:72%;padding:10px 12px;border-radius:12px;border:1px solid var(--border);background:#0f1420;box-shadow:0 6px 24px rgba(0,0,0,.2)}
.label-row{display:flex;gap:8px;align-items:center;margin:6px 0 0 0;color:#a3e635;font-size:12px}
.label-row .icon{width:14px;height:14px}
.assistant .bubble{background:linear-gradient(180deg, rgba(124,58,237,.18), rgba(6,182,212,.12));border-color:rgba(124,58,237,.35)}
.user .bubble{background:linear-gradient(180deg, rgba(15,23,42,.9), rgba(15,23,42,.7));}
.bubble .role{font-size:12px;color:var(--muted);margin-bottom:4px}
.bubble .text{line-height:1.55;white-space:normal}
.bubble .text p{margin:0 0 6px 0}
.bubble .text p:last-child{margin-bottom:0}
.bubble .text ul,.bubble .text ol{margin:6px 0 0 0;padding-left:18px}
.bubble .text li{margin:4px 0;line-height:1.55}
.bubble .text strong{font-weight:600}
.bubble .saved{margin-top:6px;font-size:12px;color:#a3e635;opacity:.9;display:flex;align-items:center;gap:6px}
.bubble .saved svg{width:14px;height:14px;display:block}
.inner-card{background:var(--card); border:1px solid var(--border); border-radius:10px; padding:10px}
.inner-card.editing{border-color:rgba(124,58,237,.6); box-shadow: inset 0 0 0 1px rgba(124,58,237,.35), 0 0 0 2px rgba(124,58,237,.15)}
.style-block{white-space:pre-wrap;background:transparent;padding:0;border:none;outline:none;margin:0;height:280px;overflow-y:auto;font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 14px; line-height: 1.6}
.editable-content{white-space:pre-wrap;background:transparent;padding:0;border:none;outline:none;margin:0;height:280px;overflow-y:auto;caret-color:#e5e7eb;font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 14px; line-height: 1.6}
.typing{opacity:.7;font-size:12px}
.chat-input{display:flex;gap:8px;align-items:flex-end}
.chat-input .input{height:74px}
  
  .health { display:grid; grid-template-columns:auto 1fr; grid-template-areas:"top metrics"; gap:12px 18px; align-items:start; }
.health .health-top { grid-area:top; display:flex; align-items:center; gap:8px; margin-top:6px; }
.health .health-badge { font-size:12px; padding:3px 8px; border-radius:6px; }
.health .health-metrics { grid-area:metrics; display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:10px 22px; align-items:start; justify-self:end; align-self:start; text-align:left; }
.health .stat { font-size:13px; color:var(--muted); letter-spacing:.02em; }

  /* Split card sections */
  .split-card { display: flex; flex-direction: column; }
.split-card .section { flex: 1 1 0; display: flex; flex-direction: column; justify-content: center; }
.split-card .section + .section { margin-top: 8px; padding-top: 8px; }
.split-card .section.top{padding-bottom:6px padding-top:10px}
.split-card .section.bottom{padding-top:8px}

.split-card .section.top .row{ margin-top:6px }

  /* Advanced layout and widgets */
  .panel.no-bottom-line{border-bottom:0}

/* Compact variant for tighter cards */
.panel.compact{padding:12px}
.panel.compact h2{margin-bottom:6px}
.panel.compact .form-row{gap:8px}
.panel.compact .label{margin-bottom:4px}
.panel.compact .input,.panel.compact .select,.panel.compact .custom-trigger{padding:6px 8px}
.panel.compact .custom-trigger{min-height:30px}
.panel.compact .row{gap:8px}
.prefs-grid{margin-top:12px}

.panels2.vsplit{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:12px}
.panels2.vsplit > .panel{min-height:0}
@media (max-width:980px){.panels2.vsplit{grid-template-columns:1fr;grid-template-rows:auto}}

.strat-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap: 8px}
@media (max-width:980px){.strat-grid{grid-template-columns:1fr}}
.strat{border:1px solid var(--border);border-radius:12px;background:#151d26;
  padding:12px; display:flex; align-items:flex-start; gap:12px; cursor:pointer; transition:transform .06s ease, border-color .18s ease; min-height:74px;}
  .strat:hover{ box-shadow:none; }

  /* Modern tables and utilities */
  .table-modern{
  width:100%;
  border-collapse:separate;
  border-spacing:0;
  font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}
.table-modern thead th{
  position:sticky; top:0; z-index:1;
    background:#0f1420;
    color:var(--muted);
  font-weight:700; font-size:12px; letter-spacing:.05em;
  text-transform:uppercase;
  border-bottom:1px solid var(--border);
}

.table-modern thead th.num{ text-align:right; }

  .table-modern th, .table-modern td{
  padding:10px 12px;
  vertical-align:middle;
  border-bottom:1px solid var(--border);
}

.table-modern thead th.num{ text-align:right; }

  .table-modern tbody tr:hover{ background:var(--hover); }
  .table-modern .small{ font-size:12px; opacity:.9; }
  .mono{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-variant-numeric:tabular-nums; }
  .num { text-align:right; font-variant-numeric:tabular-nums; }

  /* Shared table scrollbar */
  .table-wrap{ overflow:auto; border-radius:0; }
.table-wrap::-webkit-scrollbar{ height:10px; width:10px; }
.table-wrap::-webkit-scrollbar-track{ background:#0c111b; border-radius:8px; }
.table-wrap::-webkit-scrollbar-thumb{ background:#1f2937; border-radius:8px; }
.table-wrap::-webkit-scrollbar-thumb:hover{ background:#2a3446; }

  /* Text-only status */
  .status{
  display:inline-flex; flex-direction:column; align-items:flex-start;
  font-size:12px; font-weight:700; letter-spacing:.04em; text-transform:uppercase;
  color:var(--muted);
}
.status::after{ content:""; height:2px; width:100%; border-radius:2px; margin-top:2px; background:currentColor; opacity:.24; }
.status.good{ color:var(--green); }
.status.bad { color:var(--red);   }
.status.warn{ color:var(--amber); }

  /* Truncate long ids */
  .truncate{ max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.strat.on{ border-color: rgba(16,185,129,.45); box-shadow:none; background: rgba(16,185,129,.05); }
.strat .dot{ width:10px; height:10px; margin-top:3px; }
.strat .info{ flex:1 1 auto; }
.strat .name{ font-weight:700; margin-bottom:2px; }
.strat .desc{ font-size:12px; color:var(--muted); }
.btn-ghost{ background:linear-gradient(180deg, rgba(124,58,237,.14), rgba(6,182,212,.10)); border:1px solid rgba(124,58,237,.45); padding:6px 10px; border-radius:8px; }

.pref-list{display:grid;gap:8px}
.pref-row{display:flex;align-items:center;justify-content:space-between;gap:8px}
.pref-row .k{font-size:12px;color:var(--muted)}
.delta{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--border);background:#0e1320;display:inline-flex;align-items:center;gap:6px}
.delta.up{color:var(--green);border-color:rgba(16,185,129,.45);background:rgba(16,185,129,.10)}
.delta.down{color:var(--red);border-color:rgba(239,68,68,.45);background:rgba(239,68,68,.10)}
.delta.neutral{color:var(--muted);opacity:.9}
  .pref-row .val{font-size:12px;color:var(--muted);text-align:right;white-space:nowrap}

  /* Account metrics layout */
  /* Align with KPI card color */
  .acctcard{padding:12px;border:1px solid var(--border);background:var(--card);border-radius:10px}
.acctgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
@media (max-width:980px){.acctgrid{grid-template-columns:1fr}}
.acctcell{display:flex;flex-direction:column;gap:4px}
.acctcell .label{font-size:12px;color:var(--muted)}
.acctcell .value{font-weight:700;font-variant-numeric:tabular-nums}
.acctcell .usage{display:flex;align-items:center;gap:8px}
.acctcell .usage .bar{flex:1;height:6px;border-radius:4px;background:var(--border);overflow:hidden}
.acctcell .usage .bar .fill{height:100%;background:var(--green)}
.acctcell.lever{grid-column:1/-1}
  .acctcell .usage .value{min-width:40px;text-align:right}


  /* Current stats list */
  .statlist{display:block}
.statrow{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:10px;padding:6px 0;border-top:1px solid var(--border)}
.statrow:first-child{border-top:0;padding-top:0}
.statrow .k{font-size:12px;color:var(--muted)}
  .statrow .v{font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
  .statrow .delta{white-space:nowrap}
  /* Numeric steppers */
  /* Hide native spinners */
.input[type=number]::-webkit-outer-spin-button,
.input[type=number]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
  .input[type=number]{ -moz-appearance: textfield; }
  /* Custom number input arrows */
  .num{ position: relative; }
.num > .input{ padding-right: 28px; text-align:left; } /* room for arrows */
.num .spin{ position:absolute; right:4px; top:50%; transform:translateY(-50%); display:flex; flex-direction:column; gap:0; align-items:center; }
.num .spin button{ width:16px; height:14px; display:flex; align-items:center; justify-content:center; border:0; background:transparent; padding:0; cursor:pointer; color:var(--muted); line-height:1; }
.num .spin button:hover{ filter: brightness(1.08); }
.num .spin button:active{ transform: translateY(1px); }
.num .spin button + button{ margin-top:-10px; }
.num .spin svg{ width:12px; height:12px; display:block; }

`;

// ---------- Types ----------
type Mode = "automatic" | "manual";
type RiskConfig = {
  enabled?: boolean;
  max_usd_per_trade?: number;
  max_open_positions?: number;
  max_daily_loss_usd?: number;
  trading_hours_pt?: { start: string; end: string };
  flatten_before_close_min?: number;
};

type StrategyKind = "ma-crossover" | "ma-grid";

// ---------- Small helpers ----------
export function useLocalStorage<T>(key: string, initial: T) {
  const [v, setV] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch { return initial; }
  });

  // Broadcast local changes and persist
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(v)); } catch {}
    // Notify other hook instances in this document
    try { window.dispatchEvent(new CustomEvent(`ls:${key}`, { detail: v as any })); } catch {}
  }, [key, v]);

  // Listen for updates from other instances (same tab) and from other tabs
  useEffect(() => {
    const onCustom = (e: Event) => {
      const ce = e as CustomEvent;
      const next = ce?.detail as T;
      // Avoid redundant state updates
      if (JSON.stringify(next) !== JSON.stringify(v)) {
        setV(next);
      }
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key !== key) return;
      try {
        const next = e.newValue ? (JSON.parse(e.newValue) as T) : initial;
        if (JSON.stringify(next) !== JSON.stringify(v)) setV(next);
      } catch {}
    };
    try { window.addEventListener(`ls:${key}` as any, onCustom as any); } catch {}
    try { window.addEventListener('storage', onStorage); } catch {}
    return () => {
      try { window.removeEventListener(`ls:${key}` as any, onCustom as any); } catch {}
      try { window.removeEventListener('storage', onStorage); } catch {}
    };
  }, [key, v, initial]);

  return [v, setV] as const;
}

async function askConfirm(message: string) {
  const g = (window as any);
  try {
    if (g.__TAURI__?.dialog?.confirm) {
      return await g.__TAURI__.dialog.confirm(message, { title: "Confirm", type: "warning" });
    }
  } catch {}
  return window.confirm(message);
}

const sleep = (ms: number) => new Promise(res => setTimeout(res, ms));
const nowIso = () => new Date().toLocaleTimeString();
const shortId = (s?: string) => {
  const id = String(s || '');
  return id.length > 14 ? `${id.slice(0,8)}…${id.slice(-4)}` : id;
};

// Text-only status label used in tables
function statusTag(status?: string) {
  const s = String(status ?? '').toLowerCase();
  let cls = "status";
  if (["filled","done","completed","executed"].includes(s)) cls += " good";
  else if (s.includes("hold")) cls += " warn";
  else if (["canceled","cancelled","rejected","expired","failed","error"].includes(s)) cls += " bad";
  else if (["open","pending","working","new","partially_filled","partial","accepted"].includes(s)) cls += " warn";
  return <span className={cls}>{status ?? ""}</span>;
}

  // ---------- API bindings ----------
  // (moved to src/api.ts and imported as `api`)

// ---------- Toast ----------
function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  function show(message: string, timeout = 2800) {
    setMsg(message);
    window.clearTimeout(timer.current!);
    timer.current = window.setTimeout(() => setMsg(null), timeout);
  }
  return { msg, show };
}

// ---------- App ----------
enum Tab { Settings=0, Status=1, Activity=2, Reports=3, Assistant=4 }

export default function App() {
  const toast = useToast();
  const [tab, setTab] = useLocalStorage<Tab>("ui.tab", Tab.Settings);

  // Refresh signal state
  const [stratRefreshTick, setStratRefreshTick] = useState(0);

  // connection state (persist inputs)
  const [host, setHost] = useLocalStorage("conn.host", "127.0.0.1");
  const [port, setPort] = useLocalStorage("conn.port", 11111);
  const [clientId, setClientId] = useLocalStorage("conn.clientId", 1);
  const [accountId, setAccountId] = useLocalStorage("conn.accountId", "");
  const [connected, setConnected] = useState(false);
  const [activeAccount, setActiveAccount] = useState<{ account_id: string | null; trd_env: string | null; account_type?: string | null } | null>(null);

  // bot state
  const [mode, setMode] = useState<Mode>("manual");
  const [cfg, setCfg] = useState<RiskConfig | null>(null);
  const [riskEnabled, setRiskEnabled] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);

  // status
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResult, setPreviewResult] = useState<any|null>(null);

  const [pnl, setPnl] = useState<number | null>(null);
  const [openPositions, setOpenPositions] = useState<number | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [autoStatus, setAutoStatus] = useState<any|null>(null);
  const [autoEvery, setAutoEvery] = useLocalStorage("auto.ms", 4000);
  const [autoAt, setAutoAt] = useState<string>("—");
  const [autoRefresh, setAutoRefresh] = useLocalStorage("status.auto", true);
  const [statusEvery, setStatusEvery] = useLocalStorage("status.ms", 5000);
  const [statusAt, setStatusAt] = useState<string>("—");
  const [weekly, setWeekly] = useState<any|null>(null);
  const [pnlSeries, setPnlSeries] = useState<Array<{ date: string; realized_pnl: number }>>([]);
  const [lastDiff, setLastDiff] = useState<any|null>(null);
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const watchlistFetchAt = useRef(0);

  // logs
  const [logs, setLogs] = useState<any[]>([]);
  const [logSymbol, setLogSymbol] = useLocalStorage("logs.symbol", "");
  const [logSince, setLogSince] = useLocalStorage("logs.sinceH", 24);
  const [logLimit, setLogLimit] = useLocalStorage("logs.limit", 200);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsAuto, setLogsAuto] = useLocalStorage("logs.auto", true);
  const [logsEvery, setLogsEvery] = useLocalStorage("logs.ms", 2500);
  const [logsSource, setLogsSource] = useLocalStorage<"system"|"autopilot">("logs.source", "system");
  const [logsAt, setLogsAt] = useState<string>("—");

  // execution (orders/fills)
  const [exSymbol, setExSymbol] = useLocalStorage("exec.symbol", "");
  const [exAuto, setExAuto] = useLocalStorage("exec.auto", true);
  const [exEvery, setExEvery] = useLocalStorage("exec.ms", 5000);
  const [exAt, setExAt] = useState<string>("—");
  const [orders, setOrders] = useState<any[]>([]);
  const [openOrderCount, setOpenOrderCount] = useState<number | null>(null);
  const [exposureMV, setExposureMV] = useState<number | null>(null);
  const exReqId = useRef(0);

  
  // preference targets (read-only for Current Stats)
  const [prefWinRate] = useLocalStorage<number>("pref.winRate", 55);
  const [prefRR] = useLocalStorage<number>("pref.rr", 1.5);
  const [prefStop] = useLocalStorage<number>("pref.stop", 1.0);
  const [prefTP] = useLocalStorage<number>("pref.tp", 2.0);
  const [prefMM] = useLocalStorage<number>("pref.mm", 1.0);
  const [prefMaxDD] = useLocalStorage<number>("pref.maxdd", 5.0);
// Bot Status live autopilot decisions
  const [statusLogs, setStatusLogs] = useState<any[]>([]);
  const [statusLogsAt, setStatusLogsAt] = useState<string>("—");

  // Explain modal for a decision
  const [explainOpen, setExplainOpen] = useState(false);
  const [explainRow, setExplainRow] = useState<any|null>(null);
  const [explainData, setExplainData] = useState<any|null>(null);

  const [exLoading, setExLoading] = useState(false);
  // positions
  const [posSymbol, setPosSymbol] = useLocalStorage("pos.symbol", "");
  const [posAuto, setPosAuto] = useLocalStorage("pos.auto", true);
  const [posEvery, setPosEvery] = useLocalStorage("pos.ms", 5000);
  const [posAt, setPosAt] = useState<string>("—");
  const [positions, setPositions] = useState<any[]>([]);
  const posReqId = useRef(0);

  const [posLoading, setPosLoading] = useState(false);



  // initial: load session + mode + risk
  useEffect(() => {
    (async () => {
      try {
        const st = await api.sessionStatus();
        if (st.connected) {
          setConnected(true);
          setActiveAccount(st.active_account || null);
        } else if (st.saved?.host && st.saved?.port) {
          try {
            await api.connect(String(st.saved.host), Number(st.saved.port), Number(st.saved?.client_id ?? clientId));
            if (st.saved?.account_id) {
              try { await api.selectAccount(String(st.saved.account_id)); } catch {}
            }
            const st2 = await api.sessionStatus();
            setConnected(!!st2.connected);
            setActiveAccount(st2.active_account || null);
          } catch {}
        }
        if (st.saved?.host) setHost(String(st.saved.host));
        if (st.saved?.port) setPort(Number(st.saved.port));
        if (st.saved?.client_id) setClientId(Number(st.saved.client_id));
        if (st.saved?.account_id) setAccountId(String(st.saved.account_id));
      } catch {}
      try { setMode((await api.getBotMode()).mode); } catch {}
      try { const c = await api.getRiskConfig(); setCfg(c); setRiskEnabled(typeof c?.enabled === 'boolean' ? !!c.enabled : null); } catch {}
      await refreshStatus(false);
      await refreshAutoStatus();
      await refreshWatchlist(true);
      await refreshLogs(false);
      await refreshExec(false);
      await refreshPositions(false);
    })();
// eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!autoRefresh || (tab !== Tab.Status && tab !== Tab.Reports)) return;
    const id = window.setInterval(() => refreshStatus(false), statusEvery);
    const idAuto = window.setInterval(() => refreshAutoStatus(), autoEvery);
    return () => { window.clearInterval(id); window.clearInterval(idAuto); };
  }, [autoRefresh, tab, statusEvery, autoEvery]);

  // Background prefetch for Activity market data even when Activity tab is not open
  useEffect(() => {
    let t: any;
    const load = async () => {
      try { await GET<any>("/debug/bars", { symbol: "US.AAPL", ktype: "K_1M", n: 3 }); } catch {}
    };
    load();
    t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  // Background prefetch watchlist/discovery cache
  useEffect(() => {
    let t: any;
    const load = async () => { try { await api.getDiscovery(); } catch {} };
    load();
    t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);

  
  useEffect(() => {
    if (tab !== Tab.Status) return;
    const pull = async () => {
      try {
        const ls = await api.autopilotLogs(100);
        setStatusLogs(ls || []);
        setStatusLogsAt(nowIso());
      } catch {}
    };
    pull();
    const id = window.setInterval(pull, 2500);
    return () => window.clearInterval(id);
  }, [tab]);
useEffect(() => {
    if (tab !== Tab.Activity || !logsAuto) return;
    const interval = Math.max(1000, Number(logsEvery) || 0);
    refreshLogs(false);
    const id = window.setInterval(() => refreshLogs(false), interval);
    return () => window.clearInterval(id);
  }, [tab, logsAuto, logsEvery, logSymbol, logSince, logLimit, logsSource]);

  useEffect(() => {
    if (tab !== Tab.Status) return;
    const id = window.setInterval(() => refreshExec(false), exEvery);
    return () => window.clearInterval(id);
  }, [tab, exEvery, exSymbol]);
  useEffect(() => {
    if (tab !== Tab.Status) return;
    const id = window.setInterval(() => refreshPositions(false), posEvery);
    return () => window.clearInterval(id);
  }, [tab, posEvery, posSymbol]);



  
  async function refreshStatus(show = true) {
    try {
      setStatusLoading(true);
      // 1) Realized PnL (today)
      try {
        const p = await api.getPnlToday();
        setPnl(p?.realized_pnl ?? null);
      } catch {}
      // 2) Positions -> count + exposure MV
      try {
        const pos = await api.listExecPositions({});
        const count = Array.isArray(pos) ? pos.length : 0;
        const mv = Array.isArray(pos)
          ? pos.reduce((acc:number, r:any) => acc + Math.abs(Number(r?.mv || 0)), 0)
          : null;
        setOpenPositions(count || 0);
        setExposureMV(mv == null ? null : Number(Number(mv).toFixed(2)));
      } catch {}
      // 3) Orders pending
      try {
        const ords = await api.listExecOrders({});
        const pending = Array.isArray(ords)
          ? ords.filter((o:any) => {
              const s = String(o?.status || "").toLowerCase();
              return !["filled", "cancelled", "canceled", "rejected", "done", "completed"].includes(s);
            }).length
          : 0;
        setOpenOrderCount(pending);
      } catch {}
      setStatusAt(nowIso());
    } catch (e:any) {
      show && toast.show(`Status refresh failed: ${brief(e)}`);
    } finally {
      setStatusLoading(false);
    }
  }

  async function refreshLogs(show = true) {
    try {
      setLogsLoading(true);
      if (logsSource === "autopilot") {
        const ls = await api.autopilotLogs(Math.max(10, Number(logLimit) || 100));
        setLogs(ls || []);
      } else {
        const q: any = { limit: Math.max(10, Number(logLimit) || 100) };
        if (logSymbol) q.symbol = logSymbol;
        if (logSince) q.since_hours = Number(logSince) || 24;
        const ls = await api.getActionLogs(q);
        setLogs(ls || []);
      }
      setLogsAt(nowIso());
    } catch (e:any) {
      show && toast.show(`Logs refresh failed: ${brief(e)}`);
    } finally {
      setLogsLoading(false);
    }
  }

  async function flattenSymbol(sym: string) {
    if (!sym) return;
    try {
      await api.flattenExecPositions([sym]);
      toast.show(`Flatten sent: ${sym}`);
      await refreshPositions(true);
      await refreshStatus(false);
      await refreshExec(false);
    } catch (e:any) {
      toast.show(`Flatten failed: ${brief(e)}`);
    }
  }

  async function flattenVisible() {
    try {
      const list = positions || [];
      const filtered = posSymbol
        ? list.filter((r:any) => String(r?.symbol || "").toLowerCase().includes(String(posSymbol).toLowerCase()))
        : list;
      const symbols = Array.from(new Set(filtered.map((r:any) => r.symbol).filter(Boolean)));
      if (!symbols.length) { toast.show("No visible positions to flatten."); return; }
      await api.flattenExecPositions(symbols);
      toast.show(`Flatten sent: ${symbols.join(", ")}`);
      await refreshPositions(true);
      await refreshStatus(false);
      await refreshExec(false);
    } catch (e:any) {
      toast.show(`Flatten failed: ${brief(e)}`);
    }
  }

  async function cancelOrder(id: string) {
    if (!id) return;
    try {
      await api.cancelExecOrder(id);
      toast.show(`Cancel sent: ${id}`);
      await refreshExec(false);
    } catch (e:any) {
      toast.show(`Cancel failed: ${brief(e)}`);
    }
  }

  // Cancel all visible orders
  async function cancelAll() {
    try {
      const list = orders || [];
      const filtered = exSymbol
        ? list.filter((o:any) => String(o?.symbol || "").toLowerCase().includes(String(exSymbol).toLowerCase()))
        : list;
      const targets = filtered.filter((o:any) => o.status === "open" || o.status === "pending");
      if (!targets.length) { toast.show("No orders to cancel."); return; }
      await Promise.all(targets.map((o:any) => api.cancelExecOrder(o.order_id)));
      toast.show(`Cancel sent: ${targets.length} order${targets.length===1?"":"s"}`);
      await refreshExec(false);
    } catch (e:any) {
      toast.show(`Cancel failed: ${brief(e)}`);
    }
  }

async function refreshExec(show = true) {
    const reqId = ++exReqId.current;
    try {
      setExLoading(true);
      try { await api.syncDealsNow(); } catch {}
      const q: any = {};
      if (exSymbol) q.symbol = exSymbol;
      const list = await api.listExecOrders(q);
      if (reqId !== exReqId.current) return;
      if (Array.isArray(list) && list.length === 0 && (orders?.length || 0) > 0) {
        setExAt(nowIso());
        setExLoading(false);
        return;
      }
      setOrders(list);
      setExAt(nowIso());
    } catch (e:any) {
      show && toast.show(`Exec refresh failed: ${brief(e)}`);
    } finally {
      if (reqId === exReqId.current) setExLoading(false);
    }
  }
  

async function refreshPositions(acceptEmpty = false) {
    const reqId = ++posReqId.current;
    try {
      setPosLoading(true);
      const data = await api.listExecPositions({ fresh: acceptEmpty });
      // Drop stale responses from earlier requests to prevent flicker
      if (reqId !== posReqId.current) return;
      let arr: any[] = data || [];
      // If not a forced fresh request and API returns an empty list intermittently, keep previous non-empty snapshot
      if (!acceptEmpty && Array.isArray(arr) && arr.length === 0 && (positions?.length || 0) > 0) {
        setPosAt(nowIso());
        setPosLoading(false);
        return;
      }
      if (posSymbol) {
        const q = String(posSymbol).toLowerCase();
        arr = arr.filter((r:any) => String(r?.symbol || "").toLowerCase().includes(q));
      }
      setPositions(arr);
      setPosAt(nowIso());
    } catch (e:any) {
      if (reqId === posReqId.current) {
        toast.show(`Positions refresh failed: ${brief(e)}`);
      }
    } finally {
      if (reqId === posReqId.current) setPosLoading(false);
    }
  }



async function refreshWatchlist(force = false) {
  const now = Date.now();
  if (!force && now - watchlistFetchAt.current < 60000) return;
  watchlistFetchAt.current = now;
  try {
    const disc = await api.getDiscovery();
    const raw = Array.isArray(disc?.preview) && disc.preview.length
      ? disc.preview
      : Array.isArray(disc?.seed)
        ? disc.seed
        : [];
    const list = (raw || [])
      .map((sym: any) => String(sym || '').toUpperCase())
      .filter(Boolean);
    setWatchlistSymbols(list);
  } catch {}
}

async function refreshAutoStatus() {
  try {
    const st = await api.autopilotStatus();
    setAutoStatus(st || null);
    setAutoAt(nowIso());
    try { const wk = await api.autopilotWeekly(); setWeekly(wk || null); } catch {}
    try { const ps = await api.getPnlSeries(30); setPnlSeries((ps as any)?.series || []); } catch {}
    try { const df = await api.autopilotLastDiff(); setLastDiff(df || null); } catch {}
    await refreshWatchlist();
  } catch (e:any) {
    // silent
  }
}


// ---------- Helpers (UI) ----------
function timeAgo(iso?: string) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - t);
  const s = Math.floor(diff/1000); if (s<60) return `${s}s ago`;
  const m = Math.floor(s/60); if (m<60) return `${m}m ago`;
  const h = Math.floor(m/60); return `${h}h ago`;
}
function shortReason(r:any): string {
  const txt = r?.reason || r?.note || `${r.action||""} ${r.side||""} ${r.symbol||""}`.trim();
  if (!txt) return "";
  try {
    const extra = r?.extra_json ? JSON.parse(r.extra_json) : (r.extra||{});
    const rationale = extra?.rationale || r?.rationale;
    const base = rationale ? `${txt} — ${String(rationale)}` : String(txt);
    return base.length>180 ? base.slice(0,180)+"…" : base;
  } catch {
    return String(txt).length>120 ? String(txt).slice(0,120)+"…" : String(txt);
  }
}
async function openExplain(r:any) {
  setExplainRow(r);
  setExplainOpen(true);
  try {
    const [ctx, last, diff] = await Promise.all([
      api.autopilotContext?.().catch(()=>null),
      api.autopilotLastOutput?.().catch(()=>null),
      api.autopilotLastDiff?.().catch(()=>null),
    ]);
    (window as any).__autopilotLastDiff = diff;
    setExplainData({ ctx, last, row: r });
  } catch {
    setExplainData({ row: r });
  }
}

function formatUsd(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const v = Number(value);
  const abs = Math.abs(v);
  const opts: Intl.NumberFormatOptions = digits > 0
    ? { minimumFractionDigits: digits, maximumFractionDigits: digits }
    : { minimumFractionDigits: 0, maximumFractionDigits: 0 };
  const formatted = abs.toLocaleString(undefined, opts);
  return `${v >= 0 ? "+" : "-"}$${formatted}`;
}

function formatPct(value: number | null | undefined, digits = 1) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(digits)}%`;
}

function shortDateLabel(iso?: string) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}
  // ---------- Derived (reports) ----------
  const pnlData = Array.isArray(pnlSeries) ? pnlSeries : [];
  const pnlLast7 = pnlData.slice(-7);
  const pnlTotal7 = pnlLast7.reduce((sum, row) => sum + Number(row?.realized_pnl ?? 0), 0);
  const bestDay = pnlLast7.reduce<{ date?: string; value: number } | null>((acc, row) => {
    const val = Number(row?.realized_pnl ?? 0);
    if (!acc || val > acc.value) return { date: row?.date, value: val };
    return acc;
  }, null);
  const worstDay = pnlLast7.reduce<{ date?: string; value: number } | null>((acc, row) => {
    const val = Number(row?.realized_pnl ?? 0);
    if (!acc || val < acc.value) return { date: row?.date, value: val };
    return acc;
  }, null);
  const greenDays = pnlLast7.filter(row => Number(row?.realized_pnl ?? 0) >= 0).length;
  const chartStart = pnlLast7[0]?.date;
  const chartEnd = pnlLast7[pnlLast7.length - 1]?.date;

  const weeklyPerf = (weekly as any)?.performance_7d || {};
  const weeklyPnl = weeklyPerf?.realized_pnl != null ? Number(weeklyPerf.realized_pnl) : null;
  const weeklyTrades = weeklyPerf?.trades != null ? Number(weeklyPerf.trades) : null;
  const weeklyWins = weeklyPerf?.wins != null ? Number(weeklyPerf.wins) : null;
  const weeklyLosses = weeklyPerf?.losses != null ? Number(weeklyPerf.losses) : null;
  const weeklyAvgMove = weeklyPerf?.avg_realized_move_pct != null ? Number(weeklyPerf.avg_realized_move_pct) : null;
  const weeklyMaxDD = weeklyPerf?.max_dd != null ? Number(weeklyPerf.max_dd) : null;
  const reweights = (weekly as any)?.auto_weight_adjustments != null ? Number((weekly as any).auto_weight_adjustments) : null;

  const dropped = (weekly as any)?.dropped || {};
  const proposedTotal = dropped?.proposed_total != null ? Number(dropped.proposed_total) : 0;
  const validatorDrops = dropped?.validator_dropped != null ? Number(dropped.validator_dropped) : 0;
  const evaluatorDrops = dropped?.evaluator_dropped != null ? Number(dropped.evaluator_dropped) : 0;
  const droppedPct = dropped?.pct_dropped_validator != null
    ? Number(dropped.pct_dropped_validator)
    : (proposedTotal ? Math.round((validatorDrops / proposedTotal) * 1000) / 10 : null);

  const missedRules = (weekly as any)?.missed_rules || {};
  const plannerInvalid = missedRules?.planner_invalid_json != null ? Number(missedRules.planner_invalid_json) : 0;
  const guardrailCount = missedRules?.guardrails != null ? Number(missedRules.guardrails) : 0;

  const executedCountsRaw: Record<string, number> = (weekly as any)?.executed_counts || {};
  const proposedCountsRaw: Record<string, number> = (weekly as any)?.proposed_counts || {};
  const executedCounts: Record<string, number> = {};
  Object.entries(executedCountsRaw).forEach(([sym, val]) => {
    const key = String(sym || '').toUpperCase();
    if (!key) return;
    executedCounts[key] = (executedCounts[key] || 0) + Number(val ?? 0);
  });
  const proposedCounts: Record<string, number> = {};
  Object.entries(proposedCountsRaw).forEach(([sym, val]) => {
    const key = String(sym || '').toUpperCase();
    if (!key) return;
    proposedCounts[key] = (proposedCounts[key] || 0) + Number(val ?? 0);
  });
  const executedTotal = Object.values(executedCounts).reduce((sum, val) => sum + Number(val ?? 0), 0);

  const funnelRows = [
    { key: "proposed", label: "Proposed", value: proposedTotal, pct: proposedTotal ? 100 : 0 },
    { key: "executed", label: "Executed", value: executedTotal, pct: proposedTotal ? (executedTotal / proposedTotal) * 100 : 0 },
    { key: "validator", label: "Validator drops", value: validatorDrops, pct: proposedTotal ? (validatorDrops / proposedTotal) * 100 : 0 },
    { key: "evaluator", label: "Evaluator drops", value: evaluatorDrops, pct: proposedTotal ? (evaluatorDrops / proposedTotal) * 100 : 0 },
  ];
  const funnelPalette: Record<string, string> = {
    proposed: "#7c3aed",
    executed: "#22c55e",
    validator: "#f97316",
    evaluator: "#38bdf8",
  };

  const attribution: Record<string, number> = (weekly as any)?.attribution || {};
  const attrEntries = Object.entries(attribution)
    .sort((a, b) => Number(b[1] ?? 0) - Number(a[1] ?? 0))
    .slice(0, 8);
  const attrTotal = attrEntries.reduce((sum, [, val]) => sum + Number(val ?? 0), 0);
  const attrPalette = ["#60a5fa", "#34d399", "#fbbf24", "#f472b6", "#a855f7", "#38bdf8", "#f97316", "#818cf8"];

  const watchlistOrder = new Map<string, number>();
  watchlistSymbols.forEach((sym, idx) => {
    const key = String(sym || '').toUpperCase();
    if (key) watchlistOrder.set(key, idx);
  });
  const symbolUniverse = Array.from(new Set([
    ...watchlistSymbols.map(sym => String(sym || '').toUpperCase()),
    ...Object.keys(proposedCounts),
    ...Object.keys(executedCounts),
  ])).filter(Boolean);
  const symbolRows = symbolUniverse
    .sort((a, b) => {
      const valA = Number(proposedCounts[a] ?? executedCounts[a] ?? 0) || 0;
      const valB = Number(proposedCounts[b] ?? executedCounts[b] ?? 0) || 0;
      if (valA !== valB) return valB - valA;
      const orderA = watchlistOrder.has(a) ? watchlistOrder.get(a)! : Number.MAX_SAFE_INTEGER;
      const orderB = watchlistOrder.has(b) ? watchlistOrder.get(b)! : Number.MAX_SAFE_INTEGER;
      if (orderA !== orderB) return orderA - orderB;
      return a.localeCompare(b);
    })
    .map(sym => {
      const proposedRaw = Number(proposedCounts[sym] ?? 0);
      const executedRaw = Number(executedCounts[sym] ?? 0);
      const proposed = Number.isFinite(proposedRaw) ? proposedRaw : 0;
      const executed = Number.isFinite(executedRaw) ? executedRaw : 0;
      const pct = proposed ? Math.min(100, (executed / proposed) * 100) : (executed > 0 ? 100 : 0);
      return { sym, proposed, executed, pct };
    });

  const pnlLast30 = pnlData.slice(-30);
  let runningTotal = 0;
  const cumulativeSeries = pnlLast30.map(row => {
    const raw = Number(row?.realized_pnl ?? 0);
    const value = Number.isFinite(raw) ? raw : 0;
    runningTotal += value;
    return { date: row?.date, value: runningTotal };
  });
  const cumulativeChange = cumulativeSeries.length ? cumulativeSeries[cumulativeSeries.length - 1].value : 0;
  const cumulativeMax = cumulativeSeries.length
    ? cumulativeSeries.reduce((max, row) => Math.max(max, Number(row.value ?? 0) || 0), Number.NEGATIVE_INFINITY)
    : 0;
  const cumulativeMin = cumulativeSeries.length
    ? cumulativeSeries.reduce((min, row) => Math.min(min, Number(row.value ?? 0) || 0), Number.POSITIVE_INFINITY)
    : 0;
  const rollingSeries = pnlLast30.map((row, idx) => {
    const start = Math.max(0, idx - 6);
    const window = pnlLast30.slice(start, idx + 1);
    const total = window.reduce((sum, cur) => {
      const raw = Number(cur?.realized_pnl ?? 0);
      return sum + (Number.isFinite(raw) ? raw : 0);
    }, 0);
    const avg = window.length ? total / window.length : 0;
    return { date: row?.date, value: avg };
  });
  const rollingLatest = rollingSeries.length ? rollingSeries[rollingSeries.length - 1].value : null;
  const rollingHigh = rollingSeries.length
    ? rollingSeries.reduce((max, row) => Math.max(max, Number(row.value ?? 0) || 0), Number.NEGATIVE_INFINITY)
    : 0;
  const rollingLow = rollingSeries.length
    ? rollingSeries.reduce((min, row) => Math.min(min, Number(row.value ?? 0) || 0), Number.POSITIVE_INFINITY)
    : 0;

  const decisionReasons: Record<string, string[]> = (weekly as any)?.decision_reasons || {};
  const reasonCounts: Record<string, number> = {};
  Object.values(decisionReasons).forEach(list => {
    if (Array.isArray(list)) {
      list.forEach(reason => {
        const key = String(reason || "").trim();
        if (key) reasonCounts[key] = (reasonCounts[key] || 0) + 1;
      });
    }
  });
  const reasonEntries = Object.entries(reasonCounts)
    .sort((a, b) => Number(b[1] ?? 0) - Number(a[1] ?? 0))
    .slice(0, 6);

  const dailyRows = pnlLast7.slice().reverse();
  const guardrailEvents = Array.isArray((autoStatus as any)?.recent_guardrails)
    ? ((autoStatus as any).recent_guardrails as any[])
    : [];

// ---------- Render ----------
  return (
    <div className="app">
      <div className="bgfx" aria-hidden="true"></div>
      <style>{css}</style>

      <style>{`/* overrides: autopilot health metrics alignment and compact spacing */
.panels2.vsplit{gap:8px}
.panel{padding:14px}
.stack{gap: 8px}
.strat-grid{gap: 8px}
.card-lg{padding:16px}

.health{ align-items: center !important; }
.health .health-metrics{ justify-self: center !important; align-self: center !important; margin-top: -14px; gap: 8px 24px; }
.health .stat{ font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; white-space: nowrap; }
.autopilot-controls{ margin-top: 11px; }`}</style>


      <header className="header">
        <div className="title">
          <div>
            <div style={{fontSize:28,fontWeight:800}}>Moomoo ChatGPT Trading Bot</div>
            <div className="help">API: <small className="code">{API_BASE}</small></div>
          </div>
        </div>

        <div className="header-quick">
          <span className="indicator" title={connected ? "Broker connection OK" : "Not connected"}>
            <span className={`dot ${connected ? "green" : "red"}`} />
            {connected ? "Connected" : "Not connected"}
          </span>
          <span className="indicator" title="Active account">
            <span>{activeAccount?.account_id || "—"}</span>
            {activeAccount?.trd_env ? <span>• {activeAccount.trd_env}</span> : null}
          </span>
          <span className="indicator" title="Risk Guardrail">
            <span className={`dot ${riskEnabled ? "green" : "red"}`} />
            Risk: {riskEnabled==null ? "—" : (riskEnabled ? "On" : "Off")}
          </span>
          <span className="indicator" title="Bot Mode"><span>Bot mode: {mode==="automatic" ? "Automatic" : "Manual"}</span></span>
        </div>
      </header>

      <nav className="tabs">
        {["Settings","Bot Status","Activity Log","Reports","Assistant"].map((t,i)=>(
          <button key={t} className={`tab ${tab===i?'active':''}`} onClick={()=>setTab(i as Tab)}>{t}</button>
        ))}
      </nav>

      {!connected && (
        <div className="panel" role="alert" style={{borderColor:"rgba(239,68,68,.45)", background:"linear-gradient(90deg, rgba(239,68,68,.1), transparent)"}}>
          <strong>Not connected.</strong> Connect to OpenD and select an account in <em>Settings → Connection</em>.
        </div>
      )}

      {/* Settings */}
      {tab===Tab.Settings && (
        <div className="stack">
          <SectionCard id="connection" title="Connection">
            <SettingsConnection
              host={host} setHost={setHost}
              port={port} setPort={setPort}
              clientId={clientId} setClientId={setClientId}
              accountId={accountId} setAccountId={setAccountId}
              doConnect={doConnect} doSelect={doSelect}
              connected={connected} activeAccount={activeAccount} toast={toast}
            />
          </SectionCard>

          <SectionCard id="risk" title="Risk">
            <SettingsRisk cfg={cfg} setCfg={setCfg} cfgGet={cfgGet} saveRisk={saveRisk} saving={saving} toast={toast} />
          </SectionCard>

          {/* Keep original heights; make columns equal width to align vertical seams with Watchlist/Signals below */}
          <div className="panels2" style={{ gridTemplateRows: "repeat(2,minmax(0,1fr))" }}>
            <SectionCard id="data" title="Data" style={{ gridRow: "span 2" }}>
              <SettingsData toast={toast} />
            </SectionCard>
            <SectionCard id="planner" title="Planner">
              <SettingsPlanner toast={toast} />
            </SectionCard>
            <SectionCard id="news" title="News">
              <SettingsNews toast={toast} />
            </SectionCard>
          </div>

          <div className="panels2" style={{ alignItems: "stretch" }}>
            <SectionCard id="watchlist" title="Watchlist">
              <SettingsWatchlist toast={toast} />
            </SectionCard>
            <SectionCard id="signals" title="Signals">
              <SettingsSignals toast={toast} />
            </SectionCard>
          </div>
          <SectionCard id="trading" title="Trading Preferences">
            <SettingsTrading />
          </SectionCard>

          <SectionCard id="preferences" title="Preferences & Memory">
            <AssistantMemory />
          </SectionCard>
        </div>
      )}

      
      {/* Bot Status */}
      {tab===Tab.Status && (
        <section className="stack">
          {/* KPIs */}
          
          
          
          {/* KPI strip */}
          <div className="grid-3">
            <div className="card card-lg" style={{gridColumn:"span 2"}}>
  <h3>Autopilot Health</h3>
    <div className="health">
    <div className="health-top">
      <span className={`badge ${autoStatus?.on ? "good" : "bad"} health-badge`}>
        {autoStatus?.on ? "ON" : "OFF"}
      </span>
      <span
        className={`badge ${(autoStatus as any)?.planner_info?.enabled ? "good" : "bad"} health-badge`}
        title="Planner provider/model"
      >
        {(() => {
          const pi:any = (autoStatus as any)?.planner_info || {};
          const model = pi.model || (autoStatus as any)?.stats?.model || "stub";
          return pi.enabled ? `GPT: ${model}` : `Planner: Stub`;
        })()}
      </span>
    </div>
    <div className="health-metrics">
      <span className="stat">Last tick: {autoStatus?.last_tick ? timeAgo(autoStatus.last_tick) : "-"}</span>
      <span className="stat">Reject streak: {autoStatus?.reject_streak ?? "-"}</span>
      <span className="stat">Decisions: {autoStatus?.stats?.decisions_today ?? autoStatus?.stats?.decisions ?? "-"}</span>
      <span className="stat">Uptime: {autoStatus?.stats?.uptime ?? "-"}</span>
      <span className="stat">Avg think: {autoStatus?.stats?.avg_think_ms ? `${autoStatus.stats.avg_think_ms} ms` : "-"}</span>
      <span className="stat">Guardrails: {riskEnabled==null ? "-" : (riskEnabled ? "On" : "Off")}</span>
    </div>
  </div>
</div>
            <div className="card split-card" style={{ gridRow: "span 2" }}>
  <div className="section top">
    <h3>Autopilot</h3>
    <div className="row autopilot-controls" style={{alignItems:"center", justifyContent:"space-between"}}>
      <div className="row">
        <button
          className={`autopilot-toggle ${mode==="automatic" ? "on" : ""}`}
          onClick={async()=> {
            try { await api.autopilotEnable(mode!=="automatic"); }
            catch(e:any) { toast.show(`Autopilot toggle failed: ${brief(e)}`); }
            setMode(mode!=="automatic" ? "automatic" : "manual");
          }}
          title={mode==="automatic" ? "Disable Autopilot" : "Enable Autopilot"}
        >
          {mode==="automatic" ? "Running..." : "Click to Enable"}
        </button>
      </div>
      <button className="btn brand" style={{marginRight:16}} onClick={doPreview}>Preview Plan</button>
    </div>
  </div>
  <div className="section bottom">
    <h3>Positions & Orders</h3>
    <div className="row" style={{alignItems:"baseline",gap:16}}>
      <div><div className="help">Open positions</div><div className="value">{openPositions ?? "—"}</div></div>
      <div><div className="help">Orders pending</div><div className="value">{openOrderCount ?? "—"}</div></div>
    </div>
  </div>
            </div>
            <div className="card"><h3>Realized PnL (Today)</h3>
              <div className="value" style={{color: pnl==null ? "inherit" : pnl>=0 ? "var(--green)" : "var(--red)"}}>
                {pnl==null ? "—" : `$${Number(pnl).toLocaleString(undefined,{minimumFractionDigits:2, maximumFractionDigits:2})}`}
              </div>
            </div>
            <div className="card">
              <h3>Exposure (MV)</h3>
              <div className="value">{exposureMV==null ? "—" : (exposureMV?.toFixed ? exposureMV.toFixed(2) : exposureMV)}</div>
            </div>
            {/* moved Plan Diff and Weekly Report to Reports tab */}
          </div>
          {/* Controls + Autopilot */}
          
          {/* Autopilot & Active Strategies */}
          
          {/* Strategy & Account row */}
          <div className="panels2 vsplit">
            <div className="panel no-bottom-line" style={{ gridRow: "span 2" }}>
              <h2 style={{marginTop:0}}>Active Strategies</h2>
              <StrategyPicker />
            </div>
            <div className="panel compact">
              <h2 style={{marginTop:0}}>Account</h2>
              <AccountCard connected={connected} activeAccount={activeAccount} />
            </div>
            <div className="panel compact">
              <h2 style={{marginTop:0}}>Current Stats</h2>
            <div className="statlist">
      {/* Win rate vs target */}
      <div className="statrow">
        <div className="k">Win rate</div>
        <div className="v">{autoStatus?.stats?.win_rate ?? autoStatus?.win_rate ?? "—"}{(autoStatus?.stats?.win_rate ?? autoStatus?.win_rate) != null ? "%" : ""}</div>
        <span className={`delta ${(() => {
          const v = (autoStatus?.stats?.win_rate ?? autoStatus?.win_rate);
          const t = prefWinRate;
          if (v==null || t==null) return "neutral";
          return v >= t ? "up" : "down";
        })()}`}>{(() => {
          const v = (autoStatus?.stats?.win_rate ?? autoStatus?.win_rate);
          const t = prefWinRate;
          if (v==null || t==null) return `target ${t ?? "—"}%`;
          const d = (v - t).toFixed(0);
          return `${v >= t ? "↑" : "↓"} ${d}% vs ${t}%`;
        })()}</span>
      </div>

      {/* Avg R multiple vs target RR */}
      <div className="statrow">
        <div className="k">Avg R multiple</div>
        <div className="v">{autoStatus?.stats?.avg_rr ?? autoStatus?.avg_rr ?? "—"}{(autoStatus?.stats?.avg_rr ?? autoStatus?.avg_rr) != null ? "R" : ""}</div>
        <span className={`delta ${(() => {
          const v = (autoStatus?.stats?.avg_rr ?? autoStatus?.avg_rr);
          const t = prefRR;
          if (v==null || t==null) return "neutral";
          return v >= t ? "up" : "down";
        })()}`}>{(() => {
          const v = (autoStatus?.stats?.avg_rr ?? autoStatus?.avg_rr);
          const t = prefRR;
          if (v==null || t==null) return `target ${t ?? "—"}R`;
          const d = (v - t).toFixed(2);
          return `${v >= t ? "↑" : "↓"} ${d}R vs ${t}R`;
        })()}</span>
      </div>

      {/* Avg realized move vs TP threshold */}
      <div className="statrow">
        <div className="k">Avg realized move</div>
        <div className="v">{autoStatus?.stats?.avg_realized_move_pct ?? autoStatus?.avg_realized_move_pct ?? "—"}{(autoStatus?.stats?.avg_realized_move_pct ?? autoStatus?.avg_realized_move_pct) != null ? "%" : ""}</div>
        <span className={`delta ${(() => {
          const v = (autoStatus?.stats?.avg_realized_move_pct ?? autoStatus?.avg_realized_move_pct);
          const t = prefTP;
          if (v==null || t==null) return "neutral";
          return v >= t ? "up" : "down";
        })()}`}>{(() => {
          const v = (autoStatus?.stats?.avg_realized_move_pct ?? autoStatus?.avg_realized_move_pct);
          const t = prefTP;
          if (v==null || t==null) return `target ${t ?? "—"}%`;
          const d = (v - t).toFixed(1);
          return `${v >= t ? "↑" : "↓"} ${d}% vs ${t}%`;
        })()}</span>
      </div>

      {/* Drawdown vs Max drawdown (lower is better) */}
      <div className="statrow">
        <div className="k">Drawdown</div>
        <div className="v">{autoStatus?.stats?.drawdown_pct ?? autoStatus?.drawdown_pct ?? "—"}{(autoStatus?.stats?.drawdown_pct ?? autoStatus?.drawdown_pct) != null ? "%" : ""}</div>
        <span className={`delta ${(() => {
          const v = (autoStatus?.stats?.drawdown_pct ?? autoStatus?.drawdown_pct);
          const t = prefMaxDD;
          if (v==null || t==null) return "neutral";
          return v <= t ? "up" : "down";
        })()}`}>{(() => {
          const v = (autoStatus?.stats?.drawdown_pct ?? autoStatus?.drawdown_pct);
          const t = prefMaxDD;
          if (v==null || t==null) return `max ${t ?? "—"}%`;
          const d = (t - v).toFixed(1);
          return `${v <= t ? "↑" : "↓"} ${d}% headroom`;
        })()}</span>
      </div>
    </div>
            </div>


            </div>
          <div className="panel thick">
            <WatchlistTrends />
          </div>
{/* Positions – its own panel */}
          <div className="panel">
            <div className="row" style={{justifyContent:"space-between", alignItems:"center", marginTop:2}}>
              <h2 className="title-lg" style={{margin:0}}>Positions</h2>
            </div>
            <div className="row" style={{alignItems:"end", gap:12, marginTop:12}}>
              <div style={{minWidth:220}}>
                <input className="input search" value={posSymbol}
                       onChange={e=>setPosSymbol(e.target.value)}
                       placeholder="US.AAPL" autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false} />
              </div>
              <button className="btn amber" onClick={flattenVisible}>Flatten Visible</button>
              <div className="row" style={{marginLeft:"auto", gap:10}}><span className="help">Last updated: {posAt}</span></div>
            </div>
            <div className="table-wrap" style={{maxHeight: 360, marginTop: 10}}>
              <table className="table-modern">
                <thead>
                  <tr>
                    <th>Symbol</th><th className="num">Qty</th><th className="num">Avg</th><th className="num">Last</th>
                    <th className="num">MV</th><th className="num">UPL</th><th className="num">RPL Today</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(positions||[]).filter(p=>(p?.qty ?? 0)!==0)
                    .filter(p=>!posSymbol || String(p.symbol||"").toLowerCase().includes(String(posSymbol).toLowerCase()))
                    .length ? (positions||[])
                    .filter(p=>(p?.qty ?? 0)!==0)
                    .filter(p=>!posSymbol || String(p.symbol||"").toLowerCase().includes(String(posSymbol).toLowerCase()))
                    .map((p:any)=>( 
                      <tr key={p.symbol}>
                        <td>{p.symbol}</td>
                        <td className="num">{p.qty}</td>
                        <td className="num">{p.avg_cost?.toFixed ? p.avg_cost.toFixed(2) : p.avg_cost}</td>
                        <td className="num">{p.last==null ? "" : (p.last?.toFixed ? p.last.toFixed(2) : p.last)}</td>
                        <td className="num">{p.mv==null ? "" : (p.mv?.toFixed ? p.mv.toFixed(2) : p.mv)}</td>
                        <td className="num" style={{color: p.upl==null ? "inherit" : (p.upl>=0 ? "var(--green)" : "var(--red)")}}>
                          {p.upl==null ? "" : (p.upl?.toFixed ? p.upl.toFixed(2) : p.upl)}
                        </td>
                        <td className="num" style={{color: p.rpl_today==null ? "inherit" : (p.rpl_today>=0 ? "var(--green)" : "var(--red)")}}>
                          {p.rpl_today==null ? "" : (p.rpl_today?.toFixed ? p.rpl_today.toFixed(2) : p.rpl_today)}
                        </td>
                        <td><button className="btn red" onClick={()=>flattenSymbol(p.symbol)}>Flatten</button></td>
                      </tr>
                    ))
                  : <tr><td colSpan={8}>No positions.</td></tr>}
                </tbody>
              </table>
            </div>
            
          </div>

          {/* Orders & Fills – separate panel */}
          <div className="panel">
            <div className="row" style={{justifyContent:"space-between", alignItems:"center", marginTop:2}}>
              <h2 className="title-lg" style={{margin:0}}>Orders</h2>

            </div>
            <div className="row" style={{alignItems:"end", gap:12, marginTop:12}}>
              <div style={{minWidth:220}}>
                <input className="input search" value={exSymbol}
                       onChange={e=>setExSymbol(e.target.value)}
                       placeholder="US.AAPL" />
              </div>
              <button className="btn amber" onClick={cancelAll}>Cancel All</button>
              <div className="row" style={{marginLeft:"auto", gap:10}}>
                <span className="help">Last updated: {exAt}</span>
              </div>
            </div>

            <div className="table-wrap" style={{maxHeight: 360, marginTop: 10}}>
              <table className="table-modern">
                <thead>
                  <tr>
                    <th>Created</th><th>Order ID</th><th>Symbol</th><th>Side</th>
                    <th>Type</th><th>TIF</th><th>Status</th><th className="num">Req Qty</th>
                    <th className="num">Filled</th><th className="num">Avg</th><th className="num">Limit</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {orders?.length ? orders
                    .filter((o:any)=>!exSymbol || String(o.symbol||"").toLowerCase().includes(String(exSymbol).toLowerCase()))
                    .map((o:any)=>(
                    <tr key={o.order_id}>
                      <td className="small mono">{o.created_at}</td>
                      <td className="small mono truncate" title={o.order_id}>{shortId(o.order_id)}</td>
                      <td>{o.symbol}</td>
                      <td>{o.side}</td>
                      <td>{o.order_type}</td>
                      <td>{o.tif}</td>
                      <td>{statusTag(o.status)}</td>
                      <td className="num">{o.requested_qty}</td>
                      <td className="num">{o.filled_qty}</td>
                      <td className="num">{o.avg_fill_price==null ? "" : Number(o.avg_fill_price).toFixed(2)}</td>
                      <td className="num">{o.limit_price==null ? "" : Number(o.limit_price).toFixed(2)}</td>
                      <td>
                        <button className="btn red" disabled={o.status!=="open" && o.status!=="pending"} onClick={()=>cancelOrder(o.order_id)}>Cancel</button>
                      </td>
                    </tr>
                  )) : <tr><td colSpan={12}>No orders yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* Activity Log */}
      {tab===Tab.Activity && (
        <ActivityLog
          logs={logs} logsAt={logsAt}
          logsEvery={logsEvery} setLogsEvery={setLogsEvery}
          logsAuto={logsAuto} setLogsAuto={setLogsAuto}
          logSymbol={logSymbol} setLogSymbol={setLogSymbol}
          logSince={logSince} setLogSince={setLogSince}
          logLimit={logLimit} setLogLimit={setLogLimit}
          logsSource={logsSource} setLogsSource={setLogsSource}
          onExplain={openExplain}
          refreshLogs={()=>refreshLogs(true)} logsLoading={logsLoading}
        />
      )}

      {/* Reports tab */}
      {tab===Tab.Reports && (
        <section className="report-layout">
          <div className="card card-lg report-card span-8">
            <h3>Realized PnL (7d)</h3>
            {pnlLast7.length ? (() => {
              const series = pnlLast7;
              const W = 720; const H = 200; const P = 30;
              const xs = series.map((_, i) => i);
                const ys = series.map(r => Number(r?.realized_pnl ?? 0));
                const minY = Math.min(0, ...ys);
                const maxY = Math.max(0, ...ys);
                const spanY = (maxY - minY) || 1;
                const spanX = Math.max(1, xs[xs.length - 1] - xs[0]);
                const getX = series.length === 1
                  ? () => W / 2
                  : (x: number) => P + (x - xs[0]) / spanX * (W - 2 * P);
                const getY = (y: number) => H - P - (y - minY) / spanY * (H - 2 * P);
                let linePath = '';
                series.forEach((row, idx) => {
                  const X = getX(xs[idx]);
                  const Y = getY(ys[idx]);
                  linePath += (idx === 0 ? `M ${X} ${Y}` : ` L ${X} ${Y}`);
                });
                const zeroY = getY(0);
                let areaPath = '';
                if (series.length > 1) {
                  areaPath = `M ${getX(xs[0])} ${zeroY}`;
                  series.forEach((row, idx) => {
                    const X = getX(xs[idx]);
                    const Y = getY(ys[idx]);
                    areaPath += ` L ${X} ${Y}`;
                  });
                  areaPath += ` L ${getX(xs[xs.length - 1])} ${zeroY} Z`;
                }
                return (
                  <div className="report-chart">
                    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{background:'#0f1420', border:'1px solid var(--border)', borderRadius:10}}>
                      <defs>
                        <linearGradient id="pnlLine" x1="0" y1="0" x2="1" y2="0">
                          <stop offset="0%" stopColor="rgba(124,58,237,1)"/>
                          <stop offset="100%" stopColor="rgba(6,182,212,1)"/>
                        </linearGradient>
                        <linearGradient id="pnlArea" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="rgba(124,58,237,0.45)"/>
                          <stop offset="100%" stopColor="rgba(6,182,212,0.05)"/>
                        </linearGradient>
                      </defs>
                      <path d={`M ${P} ${zeroY} L ${W-P} ${zeroY}`} stroke="rgba(148,163,184,.35)" strokeWidth="1" strokeDasharray="4 6" fill="none"/>
                      {areaPath ? <path d={areaPath} fill="url(#pnlArea)" stroke="none"/> : null}
                      <path d={linePath} stroke="url(#pnlLine)" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                      {series.map((row, idx) => {
                        const X = getX(xs[idx]);
                        const Y = getY(ys[idx]);
                        const positive = ys[idx] >= 0;
                        return <circle key={row?.date || idx} cx={X} cy={Y} r={3.2} fill={positive ? 'var(--green)' : 'var(--red)'} stroke="#0f1420" strokeWidth="1.4"/>;
                      })}
                    </svg>
                    <div className="chart-axis">
                      <span>{shortDateLabel(chartStart)}</span>
                    <span>{shortDateLabel(chartEnd)}</span>
                  </div>
                </div>
              );
            })() : <div className="help">No realized PnL tracked for the past week.</div>}
            <div className="chart-meta">
              <div className="stat-pill">
                <span className="label">Total</span>
                <span className="value" style={{color: pnlTotal7 >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(pnlTotal7)}</span>
              </div>
              <div className="stat-pill">
                <span className="label">Best day</span>
                {bestDay ? (
                  <>
                    <span className="value" style={{color: bestDay.value >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(bestDay.value)}</span>
                    <span className="help">{shortDateLabel(bestDay.date)}</span>
                  </>
                ) : <span className="value">—</span>}
              </div>
              <div className="stat-pill">
                <span className="label">Worst day</span>
                {worstDay ? (
                  <>
                    <span className="value" style={{color: worstDay.value >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(worstDay.value)}</span>
                    <span className="help">{shortDateLabel(worstDay.date)}</span>
                  </>
                ) : <span className="value">—</span>}
              </div>
              <div className="stat-pill">
                <span className="label">Green days</span>
                <span className="value">{pnlLast7.length ? `${greenDays}/${pnlLast7.length}` : '—'}</span>
                {pnlLast7.length ? <span className="help">{formatPct((greenDays / pnlLast7.length) * 100, (greenDays === pnlLast7.length || greenDays === 0) ? 0 : 1)}</span> : null}
              </div>
            </div>
          </div>
          <div className="card card-lg report-card span-4">
              <h3>Weekly Snapshot</h3>
              <div className="report-stats">
                <div className="stat-pill">
                  <span className="label">7d realized PnL</span>
                  <span className="value" style={{color: (weeklyPnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'}}>{weeklyPnl==null ? '—' : formatUsd(weeklyPnl)}</span>
                </div>
                <div className="stat-pill">
                  <span className="label">Trades</span>
                  <span className="value">{weeklyTrades==null ? '—' : weeklyTrades.toLocaleString()}</span>
                  {(weeklyWins!=null || weeklyLosses!=null) ? <span className="help">W {weeklyWins ?? 0} / L {weeklyLosses ?? 0}</span> : null}
                </div>
                <div className="stat-pill">
                  <span className="label">Max drawdown</span>
                  <span className="value">{weeklyMaxDD==null ? '—' : formatPct(weeklyMaxDD, 1)}</span>
                </div>
                <div className="stat-pill">
                  <span className="label">Avg move</span>
                  <span className="value">{weeklyAvgMove==null ? '—' : formatPct(weeklyAvgMove, 1)}</span>
                </div>
                <div className="stat-pill">
                  <span className="label">Auto reweights</span>
                  <span className="value">{reweights==null ? '—' : reweights.toLocaleString()}</span>
                </div>
                <div className="stat-pill">
                  <span className="label">Validator drop rate</span>
                  <span className="value">{droppedPct==null ? '—' : formatPct(droppedPct, droppedPct >= 10 ? 0 : 1)}</span>
                  {proposedTotal ? <span className="help">{validatorDrops.toLocaleString()} / {proposedTotal.toLocaleString()}</span> : null}
                </div>
                <div className="stat-pill">
                  <span className="label">Planner errors</span>
                  <span className="value">{plannerInvalid.toLocaleString()}</span>
                  <span className="help">Guardrails {guardrailCount.toLocaleString()}</span>
                </div>
              </div>
            </div>
          <div className="card card-lg report-card span-6">
            <h3>30d Cumulative PnL</h3>
            {cumulativeSeries.length ? (() => {
                  const series = cumulativeSeries;
                  const W = 720; const H = 220; const P = 32;
                  const xs = series.map((_, idx) => idx);
                  const ys = series.map(row => Number(row.value ?? 0) || 0);
                  const minY = Math.min(0, ...ys);
                  const maxY = Math.max(0, ...ys);
                  const spanY = (maxY - minY) || 1;
                  const spanX = Math.max(1, xs.length > 1 ? xs[xs.length - 1] - xs[0] : 1);
                  const getX = series.length === 1
                    ? () => W / 2
                    : (x: number) => P + (x - xs[0]) / spanX * (W - 2 * P);
                  const getY = (y: number) => H - P - (y - minY) / spanY * (H - 2 * P);
                  let linePath = '';
                  series.forEach((row, idx) => {
                    const X = getX(xs[idx]);
                    const Y = getY(ys[idx]);
                    linePath += idx === 0 ? `M ${X} ${Y}` : ` L ${X} ${Y}`;
                  });
                  let areaPath = '';
                  if (series.length > 1) {
                    areaPath = `M ${getX(xs[0])} ${getY(minY)}`;
                    series.forEach((row, idx) => {
                      const X = getX(xs[idx]);
                      const Y = getY(ys[idx]);
                      areaPath += ` L ${X} ${Y}`;
                    });
                    areaPath += ` L ${getX(xs[xs.length - 1])} ${getY(minY)} Z`;
                  }
                  const zeroY = getY(0);
                  const startDate = series[0]?.date;
                  const endDate = series[series.length - 1]?.date;
                  return (
                    <div className="report-chart">
                      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{background:'#0f1420', border:'1px solid var(--border)', borderRadius:10}}>
                        <defs>
                          <linearGradient id="cumLine" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor="rgba(96,165,250,1)" />
                            <stop offset="100%" stopColor="rgba(14,165,233,1)" />
                          </linearGradient>
                          <linearGradient id="cumArea" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="rgba(59,130,246,0.45)" />
                            <stop offset="100%" stopColor="rgba(15,23,42,0.05)" />
                          </linearGradient>
                        </defs>
                        <path d={`M ${P} ${zeroY} L ${W - P} ${zeroY}`} stroke="rgba(148,163,184,.35)" strokeWidth="1" strokeDasharray="4 6" fill="none" />
                        {areaPath ? <path d={areaPath} fill="url(#cumArea)" stroke="none" /> : null}
                        <path d={linePath} stroke="url(#cumLine)" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                        {series.map((row, idx) => {
                          const X = getX(xs[idx]);
                          const Y = getY(ys[idx]);
                          const positive = ys[idx] >= 0;
                          return <circle key={row?.date || idx} cx={X} cy={Y} r={3.2} fill={positive ? 'var(--green)' : 'var(--red)'} stroke="#0f1420" strokeWidth="1.4"/>;
                        })}
                      </svg>
                      <div className="chart-axis">
                        <span>{shortDateLabel(startDate)}</span>
                    <span>{shortDateLabel(endDate)}</span>
                  </div>
                  <div className="chart-legend">
                    <span><span className="legend-dot" style={{background:'rgba(96,165,250,0.85)'}}></span>Cumulative PnL</span>
                  </div>
                </div>
              );
            })() : <div className="help">Not enough realized PnL history yet.</div>}
            <div className="chart-meta">
              <div className="stat-pill">
                <span className="label">Net change</span>
                <span className="value" style={{color: (cumulativeChange ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(cumulativeChange)}</span>
              </div>
              <div className="stat-pill">
                <span className="label">High watermark</span>
                <span className="value" style={{color: (cumulativeMax ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(cumulativeMax)}</span>
              </div>
              <div className="stat-pill">
                <span className="label">Low watermark</span>
                <span className="value" style={{color: (cumulativeMin ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(cumulativeMin)}</span>
              </div>
            </div>
          </div>
          <div className="card card-lg report-card span-6">
            <h3>7d Rolling Avg PnL</h3>
            {rollingSeries.length ? (() => {
                  const series = rollingSeries;
                  const W = 720; const H = 200; const P = 30;
                  const xs = series.map((_, idx) => idx);
                  const ys = series.map(row => Number(row.value ?? 0) || 0);
                  const minY = Math.min(0, ...ys);
                  const maxY = Math.max(0, ...ys);
                  const spanY = (maxY - minY) || 1;
                  const spanX = Math.max(1, xs.length > 1 ? xs[xs.length - 1] - xs[0] : 1);
                  const getX = series.length === 1
                    ? () => W / 2
                    : (x: number) => P + (x - xs[0]) / spanX * (W - 2 * P);
                  const getY = (y: number) => H - P - (y - minY) / spanY * (H - 2 * P);
                  let linePath = '';
                  series.forEach((row, idx) => {
                    const X = getX(xs[idx]);
                    const Y = getY(ys[idx]);
                    linePath += idx === 0 ? `M ${X} ${Y}` : ` L ${X} ${Y}`;
                  });
                  let areaPath = '';
                  if (series.length > 1) {
                    areaPath = `M ${getX(xs[0])} ${getY(0)}`;
                    series.forEach((row, idx) => {
                      const X = getX(xs[idx]);
                      const Y = getY(ys[idx]);
                      areaPath += ` L ${X} ${Y}`;
                    });
                    areaPath += ` L ${getX(xs[xs.length - 1])} ${getY(0)} Z`;
                  }
                  const zeroY = getY(0);
                  const startDate = series[0]?.date;
                  const endDate = series[series.length - 1]?.date;
                  return (
                    <div className="report-chart">
                      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{background:'#0f1420', border:'1px solid var(--border)', borderRadius:10}}>
                        <defs>
                          <linearGradient id="rollLine" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor="rgba(168,85,247,1)" />
                            <stop offset="100%" stopColor="rgba(244,114,182,1)" />
                          </linearGradient>
                          <linearGradient id="rollArea" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="rgba(168,85,247,0.35)" />
                            <stop offset="100%" stopColor="rgba(15,23,42,0.05)" />
                          </linearGradient>
                        </defs>
                        <path d={`M ${P} ${zeroY} L ${W - P} ${zeroY}`} stroke="rgba(148,163,184,.35)" strokeWidth="1" strokeDasharray="4 6" fill="none" />
                        {areaPath ? <path d={areaPath} fill="url(#rollArea)" stroke="none" /> : null}
                        <path d={linePath} stroke="url(#rollLine)" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                        {series.map((row, idx) => {
                          const X = getX(xs[idx]);
                          const Y = getY(ys[idx]);
                          const positive = ys[idx] >= 0;
                          return <circle key={row?.date || idx} cx={X} cy={Y} r={3} fill={positive ? 'var(--green)' : 'var(--red)'} stroke="#0f1420" strokeWidth="1.2"/>;
                        })}
                      </svg>
                      <div className="chart-axis">
                        <span>{shortDateLabel(startDate)}</span>
                    <span>{shortDateLabel(endDate)}</span>
                  </div>
                  <div className="chart-legend">
                    <span><span className="legend-dot" style={{background:'rgba(168,85,247,0.85)'}}></span>Rolling average</span>
                  </div>
                </div>
              );
            })() : <div className="help">Not enough realized PnL history yet.</div>}
            <div className="chart-meta">
              <div className="stat-pill">
                <span className="label">Latest average</span>
                <span className="value" style={{color: (rollingLatest ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'}}>{rollingLatest == null ? '—' : formatUsd(rollingLatest)}</span>
              </div>
              <div className="stat-pill">
                <span className="label">Best avg</span>
                <span className="value" style={{color: (rollingHigh ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(rollingHigh)}</span>
              </div>
              <div className="stat-pill">
                <span className="label">Soft floor</span>
                <span className="value" style={{color: (rollingLow ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(rollingLow)}</span>
              </div>
            </div>
          </div>
          <div className="card card-lg report-card span-6">
            <h3>Execution Funnel (7d)</h3>
            {(proposedTotal || executedTotal || validatorDrops || evaluatorDrops) ? (
              <div className="funnel-bars">
                {funnelRows.map(row => {
                  const ratio = row.key === 'proposed' ? 1 : (proposedTotal ? Math.max(0, Math.min(1, row.value / proposedTotal)) : 0);
                  const pctLabel = row.key === 'proposed' ? '100%' : (proposedTotal ? formatPct(row.pct, row.pct >= 10 ? 0 : 1) : '—');
                  const accent = funnelPalette[row.key] || '#7c3aed';
                  return (
                    <div key={row.key} className="funnel-bar-row">
                      <div className="funnel-bar-label">
                        <span className="label">{row.label}</span>
                        <span className="value">{row.value.toLocaleString()}</span>
                      </div>
                      <div className="funnel-bar-track">
                        <div
                          className="funnel-bar-fill"
                          style={{ width: `${Math.min(100, Math.max(0, ratio * 100))}%`, background: `linear-gradient(90deg, ${accent}, rgba(148,163,184,.25))` }}
                        />
                      </div>
                      <span className="funnel-bar-pct">{pctLabel}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="help">No planner activity captured over the past week.</div>
            )}
          </div>
          <div className="card card-lg report-card span-6">
            <h3>Strategy Attribution (7d)</h3>
            {attrEntries.length ? (
              <div className="strategy-grid">
                {attrEntries.map(([name, val], idx) => {
                    const value = Number(val ?? 0);
                    const share = attrTotal > 0 ? Math.max(0, value / attrTotal) : 0;
                    const circumference = 2 * Math.PI * 19;
                    const offset = circumference * (1 - Math.min(1, share));
                    const color = attrPalette[idx % attrPalette.length];
                    return (
                      <div key={name} className="strategy-tile">
                        <div className="strategy-radial">
                          <svg viewBox="0 0 44 44">
                            <circle className="bg" cx="22" cy="22" r="19" />
                            <circle
                              className="fg"
                              cx="22"
                              cy="22"
                              r="19"
                              stroke={color}
                              strokeDasharray={`${circumference} ${circumference}`}
                              strokeDashoffset={offset}
                            />
                          </svg>
                          <span>{formatPct(share * 100, share >= 0.1 ? 0 : 1)}</span>
                        </div>
                        <div className="meta">
                          <span className="name">{name}</span>
                          <span className="value">{value.toFixed(2)}</span>
                          <span className="share">of total PnL</span>
                        </div>
                      </div>
                    );
                })}
              </div>
            ) : (
              <div className="help">No strategy attribution captured for the past week.</div>
            )}
          </div>
          <div className="card card-lg report-card span-6">
            <h3>Symbol Follow-through (7d)</h3>
            {symbolRows.length ? (
              <div className="symbol-grid">
                {symbolRows.map(row => {
                    const ratio = row.proposed ? Math.max(0, Math.min(1, row.executed / row.proposed)) : (row.executed > 0 ? 1 : 0);
                    const statusClass = ratio >= 1 ? 'ahead' : ratio > 0 ? 'active' : 'idle';
                    const dots = 10;
                    const filled = Math.round(ratio * dots);
                    return (
                      <div key={row.sym} className="symbol-card">
                        <div className="header">
                          <span className="ticker">{row.sym}</span>
                          <span className={`status ${statusClass}`}>{row.executed.toLocaleString()} filled</span>
                        </div>
                        <div className="meta">
                          <span>{row.proposed ? `${row.proposed.toLocaleString()} proposed` : 'No proposals'}</span>
                          <span className={`ratio ${statusClass}`}>{row.proposed ? formatPct(row.pct, row.pct >= 10 ? 0 : 1) : '—'}</span>
                        </div>
                        <div className="dot-progress" title={`${(ratio * 100).toFixed(0)}% follow-through`}>
                          {Array.from({ length: dots }).map((_, idx) => (
                            <span key={idx} className={idx < filled ? 'active' : ''} />
                          ))}
                        </div>
                      </div>
                    );
                })}
              </div>
            ) : (
              <div className="help">No planner proposals recorded in the past week.</div>
            )}
          </div>
          <div className="card card-lg report-card span-6">
            <h3>Guardrail &amp; Planner Notes (7d)</h3>
            {guardrailEvents.length ? (
              <>
                <div className="help" style={{ fontWeight: 600 }}>Recent guardrail triggers</div>
                <div className="guardrail-list">
                  {guardrailEvents.map((evt, idx) => (
                    <div key={`${evt?.ts || idx}-${idx}`} className="guardrail-entry">
                      <div className="row">
                        <span>{evt?.sym || evt?.symbol || '—'}</span>
                        <span>{timeAgo(evt?.ts)}</span>
                      </div>
                      <div className="reason">{evt?.reason || evt?.status || 'Guardrail tripped'}</div>
                      <div className="row" style={{ justifyContent: 'flex-start', gap: 12 }}>
                        {evt?.action && <span>action {evt.action}</span>}
                        {evt?.side && <span>{String(evt.side).toUpperCase()}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
            {reasonEntries.length ? (
              <>
                <div className="help" style={{ fontWeight: 600, marginTop: guardrailEvents.length ? 12 : 0 }}>Planner drop reasons</div>
                <div className="timeline">
                  {reasonEntries.map(([reason, count], idx) => (
                    <div key={reason || idx} className="timeline-item">
                      <div className="title">{reason}</div>
                      <div className="meta">{count} events</div>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
            {!guardrailEvents.length && !reasonEntries.length ? (
              guardrailCount > 0 ? (
                <div className="help">Guardrails triggered {guardrailCount.toLocaleString()} times over the past week.</div>
              ) : (
                <div className="help">No guardrail actions logged over the past week.</div>
              )
            ) : null}
          </div>
          <div className="card card-lg report-card span-12">
            <h3>Daily Realized PnL (7d)</h3>
            {dailyRows.length ? (
              <div className="report-table">
                {dailyRows.map((row, idx) => {
                  const value = Number(row?.realized_pnl ?? 0);
                  return (
                    <div key={row?.date || idx} className="report-row">
                      <span className="date">{shortDateLabel(row?.date)}</span>
                      <span className="pnl" style={{color: value >= 0 ? 'var(--green)' : 'var(--red)'}}>{formatUsd(value)}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="help">No realized trades logged in the last 7 days.</div>
            )}
          </div>
        </section>
      )}

      {/* Assistant tab */}
      {tab===Tab.Assistant && (
        <section className="stack">
          <div className="card" style={{gridColumn:"span 3"}}>
            <h3>Trading Assistant</h3>
            <AssistantChat />
          </div>
        </section>
      )}

      {/* Backtest tab removed */}

      {previewOpen && createPortal(
        <div id="preview-modal" style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.55)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000
        }} onClick={()=>setPreviewOpen(false)}>
          <div className="panel" style={{width: "min(860px, 94vw)", maxHeight: "80vh", overflow: "auto"}} onClick={e=>e.stopPropagation()}>
            <h2 style={{marginTop:0}}>Autopilot Preview</h2>
            <div className="help" style={{marginBottom:8}}>Raw planner input/output and validation (read-only)</div>
            <pre style={{whiteSpace:"pre-wrap", background:"#0b1220", padding:"12px", borderRadius:"8px", border:"1px solid var(--border)"}}>
{JSON.stringify(previewResult, null, 2)}
            </pre>
            <div className="row" style={{marginTop:12, justifyContent:"flex-end"}}>
              <button className="btn" onClick={()=>setPreviewOpen(false)}>Close</button>
            </div>
          </div>
        </div>, document.body
      )}

      {explainOpen && createPortal(
        <div id="explain-modal" style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.55)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000
        }} onClick={()=>setExplainOpen(false)}>
          <div className="panel" style={{width: "min(860px, 94vw)", maxHeight: "80vh", overflow: "auto"}} onClick={e=>e.stopPropagation()}>
            <h2 style={{marginTop:0}}>Decision Details</h2>
            <div className="help" style={{marginBottom:8}}>What the bot was thinking and why it acted</div>
            {(() => {
              try {
                const row:any = explainRow || {};
                const extra:any = row.extra_json ? JSON.parse(row.extra_json) : (row.extra || {});
                const sigs:any[] = Array.isArray(extra?.signals_used) ? extra.signals_used : [];
                const tone = extra?.news_tone;
                const conf = extra?.conf; const minc = extra?.min_conf;
                const rationale = extra?.rationale || row?.rationale;
                // policy from planner context if available in explainData
                let pol:any = undefined;
                try { pol = (explainData?.ctx || explainData?.context || {}).policy; } catch {}
                const rc:any = extra?.rule_checks || null;
                let polsum:any = undefined;
                try { polsum = (explainData?.last?.last_output || {}).policy_summary; } catch {}
                if (!sigs.length && !tone && conf==null) return null;
                return (
                  <div className="panel compact" style={{background:"#0e1320", marginBottom:8}}>
                    <div className="row" style={{gap:8, flexWrap:"wrap"}}>
                      {polsum && <span className="badge" title="Policy summary">{String(polsum).slice(0,80)}</span>}
                      {typeof conf === 'number' && typeof minc === 'number' && (
                        <span className="badge" title="Confidence gate">conf {conf.toFixed(2)} ≥ {minc.toFixed(2)}</span>
                      )}
                      {tone && <span className="badge" title="News tone">news {String(tone)}</span>}
                      {rationale && <span className="badge" title="Rationale">{String(rationale).slice(0,80)}</span>}
                      {pol && pol.reduce_only && <span className="badge" title="Policy">reduce-only</span>}
                      {pol && pol.long_only && <span className="badge" title="Policy">long-only</span>}
                      {pol && pol.short_only && <span className="badge" title="Policy">short-only</span>}
                      {pol && pol.forbid_new && <span className="badge" title="Policy">no-new</span>}
                      {rc && <>
                        {rc.strict_prefs_ok!=null && <span className="badge" title="Strict prefs">prefs {rc.strict_prefs_ok?"ok":"fail"}</span>}
                        {rc.policy_ok!=null && <span className="badge" title="Policy check">policy {rc.policy_ok?"ok":"fail"}</span>}
                        {rc.near_earnings!=null && <span className="badge" title="Earnings window">earn {rc.near_earnings?"near":"-"}</span>}
                        {rc.valuation_ok!=null && <span className="badge" title="Valuation">val {rc.valuation_ok?"ok":"rich"}</span>}
                        {rc.conflict!=null && <span className="badge" title="Conflict index">conflict {rc.conflict?"hi":"lo"}</span>}
                        {rc.unusual_flow!=null && <span className="badge" title="Unusual flow">flow {rc.unusual_flow?Number(rc.unusual_flow_strength||0).toFixed(2):"-"}</span>}
                      </>}
                      {sigs.slice(0,6).map((s:any, i:number)=> (
                        <span key={i} className="badge" title={`${s.strategy} ${s.signal}`}>{s.strategy}:{s.signal} {Number(s.strength||0).toFixed(2)}</span>
                      ))}
                    </div>
                  </div>
                );
              } catch { return null; }
            })()}
            {(() => {
              // Proposed vs Kept diff (best-effort)
              try {
                const diff:any = (window as any).__autopilotLastDiff || null;
                if (!diff) return null;
                const propSyms = (diff.proposed||[]).map((d:any)=>d.sym).filter(Boolean);
                const keptSyms = (diff.kept||[]).map((d:any)=>d.sym).filter(Boolean);
                return (
                  <div className="panel compact" style={{background:"#0e1320", marginBottom:8}}>
                    <div className="row" style={{gap:8, flexWrap:"wrap"}}>
                      <span className="badge" title="Proposed count">proposed {propSyms.length}</span>
                      <span className="badge" title="Kept after evaluator">kept {keptSyms.length}</span>
                      {propSyms.length>0 && (
                        <span className="badge" title="Proposed syms">{propSyms.slice(0,6).join(", ")}</span>
                      )}
                      {keptSyms.length>0 && (
                        <span className="badge" title="Kept syms">{keptSyms.slice(0,6).join(", ")}</span>
                      )}
                    </div>
                  </div>
                );
              } catch { return null; }
            })()}
            <pre style={{whiteSpace:"pre-wrap", background:"#0b1320", padding:"12px", borderRadius:"8px", border:"1px solid var(--border)"}}>
{JSON.stringify(explainData || explainRow, null, 2)}
            </pre>
            <div className="row" style={{marginTop:12, justifyContent:"flex-end"}}>
              <button className="btn" onClick={()=>setExplainOpen(false)}>Close</button>
            </div>
          </div>
        </div>, document.body
      )}

      {toast.msg && <div className="toast" role="status" aria-live="polite">{toast.msg}</div>}
    </div>
  );

// Handlers and helpers (scoped to App)
async function doConnect() {
  try {
    await api.connect(String(host), Number(port), Number(clientId));
    setConnected(true);
    try { setActiveAccount(await api.accountsActive()); } catch {}
    toast.show("Connected.");
  } catch (e:any) {
    toast.show(`Connect failed: ${brief(e)}`);
  }
}

async function doSelect() {
  try {
    const resp = await api.selectAccount(String(accountId));
    setActiveAccount(resp as any);
    toast.show("Account selected.");
  } catch (e:any) {
    toast.show(`Select failed: ${brief(e)}`);
  }
}

function cfgGet<K extends keyof RiskConfig, T = any>(key: K, def: T): any {
  const c: any = cfg || {};
  const v = c[key];
  if (v === undefined || v === null) return def;
  return v;
}


async function saveRisk() {
  if (!cfg) return;
  try {
    setSaving(true);
    const r = await api.putRiskConfig(cfg);
    setCfg(r);
    // Instantly reflect header pill without waiting for poll / reload
    const en = (typeof (r as any)?.enabled === "boolean")
      ? !!(r as any).enabled
      : (typeof cfg?.enabled === "boolean" ? !!cfg.enabled : null);
    setRiskEnabled(en);
    // Pull fresh status and autopilot snapshot
    await refreshStatus(false);
    await refreshAutoStatus();
    toast.show("Risk config saved.");
  } catch (e:any) {
    toast.show(`Save failed: ${brief(e)}`);
  } finally {
    setSaving(false);
  }
}


async function killSwitch() {
  const ok = await askConfirm("Stop all running automations NOW?");
  if (!ok) return;
  try {
    await SEND("/automation/stop_all", {});
    toast.show("Kill switch sent.");
    setStratRefreshTick((t: number)=>t+1);
  } catch (e:any) {
    toast.show(`Kill switch failed: ${brief(e)}`);
  }
}

async function doFlattenAll() {
  const ok = await askConfirm("Flatten ALL positions now? (SIMULATE is allowed; REAL is blocked by server)");
  if (!ok) return;
  try {
    await api.flattenAll();
    toast.show("Flatten sent.");
  } catch (e:any) {
    toast.show(`Flatten failed: ${brief(e)}`);
  }
}

async function applyMode(next: Mode) {
  try {
    const r = await api.setBotMode(next);
    setMode(r.mode as Mode);
  } catch (e:any) {
    toast.show(`Set mode failed: ${brief(e)}`);
  }
}

async function doPreview() {
  try {
    setPreviewLoading(true);
    const r = await api.autopilotPreview();
    setPreviewResult(r);
    setPreviewOpen(true);
  } catch (e:any) {
    toast.show(`Preview failed: ${brief(e)}`);
  } finally {
    setPreviewLoading(false);
  }
}


  function brief(err: any) {
    try { const j = JSON.parse(String(err?.message || err)); return j?.detail || err?.message || String(err); }
    catch { return err?.message || String(err); }
  }
}

// ---------- Subcomponents ----------

// ---------- Fancy dropdowns (portal-based, non-clipping) ----------
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
  const [pos, setPos] = useState<{ left: number; top: number; width: number; openUp: boolean }>(
    { left: 0, top: 0, width: 0, openUp: false }
  );

  useEffect(() => {
    if (!open || !trigger) return;

    // capture a non-null handle for the closure
    const el: HTMLElement = trigger;

    function place() {
      const r = el.getBoundingClientRect(); // <- no null warning now
      const width = Math.max(r.width, 160);
      let left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
      let top = r.bottom + 6;
      let openUp = false;

      // open upward if not enough room below
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
  value, onChange, options, width = "100%", placeholder = "Select…"
}: { value: string; onChange: (v: string) => void; options: Opt[]; width?: number | string; placeholder?: string }) {
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
          style={{
            position: "fixed",
            left: pos.left,
            top: pos.top,
            width: pos.width,
            maxHeight: 260,
            zIndex: 10000,
          }}
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
  value, onChange, options, width = "100%", placeholder = "Search…"
}: { value: string; onChange: (v: string) => void; options: Opt[]; width?: number | string; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const outsideRef = useOutsideClose<HTMLDivElement>(open, () => setOpen(false));
  const pos = useAnchorPosition(btnRef.current, open);
  const current = options.find(o => o.value === value);
  const filtered = q
    ? options.filter(o => o.label.toLowerCase().includes(q.toLowerCase()) || o.value.toLowerCase().includes(q.toLowerCase()))
    : options;

  return (
    <div className="custom-select" style={{ width }}>
      <button className="custom-trigger" ref={btnRef} type="button" onClick={() => setOpen(o => !o)}>
        {current?.label ?? <span style={{ color: "var(--muted)" }}>Select…</span>}
      </button>

      {open && createPortal(
        <div
          ref={outsideRef}
          className="menu"
          style={{
            position: "fixed",
            left: pos.left,
            top: pos.top,
            width: pos.width,
            maxHeight: 260,
            zIndex: 10000,
          }}
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



function AccountCard({ connected, activeAccount }: { connected: boolean; activeAccount: { account_id: string | null; trd_env: string | null; account_type?: string | null } | null }) {
  const [assets, setAssets] = useState<{ equity?: number | null; bp?: number | null; cash?: number | null } | null>(null);

  useEffect(() => {
    let timer: any;
    const load = async () => {
      if (!connected || !activeAccount?.account_id) {
        setAssets(null);
        return;
      }
      try {
        const a: any = await api.getAccountAssets();
        setAssets(a || null);
      } catch {}
    };
    load();
    timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [connected, activeAccount?.account_id]);

  const equity = assets?.equity ?? null;
  const cash = assets?.cash ?? null;
  const bp = assets?.bp ?? null;
  const usage = bp != null && cash != null ? Math.min(1, Math.max(0, (bp - cash) / bp)) : null;
  const leverage = equity != null && bp != null && equity !== 0 ? bp / equity : null;

  return (
    <div className="stack">
      <div className="acctcard">
        <div className="acctgrid">
          <div className="acctcell">
            <div className="label">Equity</div>
            <div className="value">{equity != null ? `$${Number(equity).toFixed(2)}` : "—"}</div>
          </div>
          <div className="acctcell">
            <div className="label">Cash</div>
            <div className="value">{cash != null ? `$${Number(cash).toFixed(2)}` : "—"}</div>
          </div>
          <div className="acctcell">
            <div className="label">Buying Power</div>
            <div className="value">{bp != null ? `$${Number(bp).toFixed(2)}` : "—"}</div>
          </div>
          <div className="acctcell lever">
            <div className="label">Leverage</div>
            <div className="usage">
              <div className="bar"><div className="fill" style={{width: usage != null ? `${(usage*100).toFixed(0)}%` : "0%"}}></div></div>
              <span className="delta neutral">{usage != null ? `${(usage*100).toFixed(0)}%` : "—"}</span>
              <div className="value">{leverage != null ? `${leverage.toFixed(2)}x` : "—"}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ActivityLog(props: {
  logs: any[]; logsAt: string; logsEvery: number; setLogsEvery: (n:number)=>void;
  logsAuto: boolean; setLogsAuto: (b:boolean)=>void;
  logSymbol: string; setLogSymbol: (s:string)=>void;
  logSince: number; setLogSince: (n:number)=>void;
  logLimit: number; setLogLimit: (n:number)=>void;
  logsSource: "system" | "autopilot"; setLogsSource: (v: "system" | "autopilot") => void;
  onExplain: (row:any)=>void;
  refreshLogs: () => void; logsLoading: boolean;
}) {
  const { logs, logsAt, logsEvery, setLogsEvery, logsAuto, setLogsAuto,
          logSymbol, setLogSymbol, logSince, setLogSince, logLimit, setLogLimit,
          logsSource, setLogsSource, onExplain,
          refreshLogs, logsLoading } = props;

  const [activeCategory, setActiveCategory] = useState<string>("All");

  function titleize(text: string) {
    if (!text) return "";
    return text
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\b(\w)/g, (m) => m.toUpperCase());
  }

  function deriveCategory(mode: string, action: string, status: string, reason: string) {
    const text = `${mode} ${action} ${status} ${reason}`.toLowerCase();
    if (text.includes("hold")) return "Hold";
    if (text.includes("guardrail")) return "Guardrail";
    if (text.includes("validator")) return "Validator";
    if (text.includes("evaluator")) return "Evaluator";
    if (text.includes("planner") || text.includes("plan ")) return "Planner";
    if (text.includes("autopilot act") || text.includes("execution") || text.includes("fill") || text.includes("order")) return "Execution";
    if (text.includes("autopilot")) return "Autopilot";
    return mode ? mode : "System";
  }

  function deriveTone(status: string, action: string, reason: string): "good" | "bad" | "warn" | "neutral" {
    const combined = `${status} ${action} ${reason}`.toLowerCase();
    if (combined.includes("hold")) return "neutral";
    if (combined.includes("reject") || combined.includes("drop") || combined.includes("fail") || combined.includes("error") || combined.includes("cancel")) return "bad";
    if (combined.includes("exec") || combined.includes("fill") || combined.includes("accept") || combined.includes("complete") || combined.includes("sent")) return "good";
    if (combined.includes("pending") || combined.includes("plan") || combined.includes("queue") || combined.includes("proposed")) return "warn";
    return "neutral";
  }

  function relativeLabel(ts: any) {
    if (!ts) return "—";
    try {
      const d = new Date(ts);
      if (Number.isNaN(d.getTime())) return String(ts);
      const diff = Date.now() - d.getTime();
      if (diff < 0) return "just now";
      const s = Math.floor(diff / 1000);
      if (s < 60) return `${s}s ago`;
      const m = Math.floor(s / 60);
      if (m < 60) return `${m}m ago`;
      const h = Math.floor(m / 60);
      if (h < 48) return `${h}h ago`;
      const days = Math.floor(h / 24);
      return `${days}d ago`;
    } catch {
      return String(ts);
    }
  }

  function exactLabel(ts: any) {
    if (!ts) return "—";
    try {
      const d = new Date(ts);
      if (Number.isNaN(d.getTime())) return String(ts);
      return d.toLocaleString();
    } catch {
      return String(ts);
    }
  }

  const normalized = useMemo(() => {
    return logs.map((row, idx) => {
      const rawTs = row?.ts ?? row?.time ?? row?.timestamp ?? row?.created_at ?? row?.date ?? "";
      const symbolRaw = row?.symbol ?? row?.sym ?? row?.ticker ?? "";
      const modeRaw = row?.mode ?? row?.phase ?? row?.source ?? row?.origin ?? "";
      const actionRaw = row?.action ?? row?.event ?? row?.type ?? row?.decision ?? "";
      const statusRaw = row?.status ?? row?.result ?? row?.outcome ?? row?.decision ?? "";
      const reasonRaw = row?.reason ?? row?.message ?? row?.note ?? row?.detail ?? row?.description ?? "";
      const sideRaw = row?.side ?? row?.order_side ?? row?.direction ?? "";
      const qtyRaw = row?.qty ?? row?.quantity ?? row?.size ?? row?.volume ?? null;
      const priceRaw = row?.price ?? row?.limit_price ?? row?.avg_price ?? row?.fill_price ?? null;
      const hold = /hold/i.test(String(actionRaw)) || /hold/i.test(String(statusRaw)) || /hold/i.test(String(row?.decision ?? "")) || /hold/i.test(String(reasonRaw));
      const baseStatus = hold ? "Hold" : String(statusRaw || "");
      const actionText = String(actionRaw || (hold ? "Hold" : ""));
      const statusText = baseStatus || actionText || "";
      const category = titleize(deriveCategory(String(modeRaw || ""), actionText, statusText, String(reasonRaw || "")));
      const tone = deriveTone(statusText, actionText, String(reasonRaw || ""));
      const statusLabel = statusText ? titleize(statusText) : "—";
      const actionLabel = actionText ? titleize(actionText) : "";
      const symbol = symbolRaw ? String(symbolRaw).toUpperCase() : "";
      const sideUpper = typeof sideRaw === "string" ? String(sideRaw).toUpperCase() : "";
      let sideClass = "";
      if (sideUpper.startsWith("B")) sideClass = "buy";
      else if (sideUpper.startsWith("S")) sideClass = "sell";
      else if (sideUpper.startsWith("H")) sideClass = "hold";
      else if (sideUpper) sideClass = sideUpper.toLowerCase();
      const qtyNum = qtyRaw != null ? Number(qtyRaw) : null;
      const qty = qtyNum != null && Number.isFinite(qtyNum) ? qtyNum : null;
      const priceNum = priceRaw != null ? Number(priceRaw) : null;
      const price = priceNum != null && Number.isFinite(priceNum) ? priceNum : null;
      const reason = reasonRaw ? String(reasonRaw) : "";
      const trimmedReason = reason.length > 220 ? `${reason.slice(0, 220)}…` : reason;
      return {
        key: row?.id ?? `${rawTs || "row"}-${idx}`,
        raw: row,
        when: relativeLabel(rawTs),
        exact: exactLabel(rawTs),
        symbol,
        modeLabel: titleize(String(modeRaw || "")),
        actionLabel: actionLabel || statusLabel,
        reason: trimmedReason,
        status: statusLabel,
        tone,
        category,
        side: sideUpper,
        sideClass,
        qty,
        price,
      };
    });
  }, [logs]);

  const categoryCounts = useMemo(() => {
    const map = new Map<string, number>();
    normalized.forEach(entry => {
      const key = entry.category || "Other";
      map.set(key, (map.get(key) || 0) + 1);
    });
    return map;
  }, [normalized]);

  const categoryOptions = useMemo(() => {
    const keys = Array.from(categoryCounts.keys());
    const order = ["Autopilot", "Planner", "Execution", "Validator", "Evaluator", "Guardrail", "Hold", "System", "Other"];
    keys.sort((a, b) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      if (ia === -1 && ib === -1) return a.localeCompare(b);
      if (ia === -1) return 1;
      if (ib === -1) return -1;
      return ia - ib;
    });
    return ["All", ...keys];
  }, [categoryCounts]);

  const filtered = useMemo(() => (
    activeCategory === "All"
      ? normalized
      : normalized.filter(entry => entry.category === activeCategory)
  ), [normalized, activeCategory]);

  const refreshChoices = useMemo(() => [
    { value: "1000", label: "1s" },
    { value: "2500", label: "2.5s" },
    { value: "5000", label: "5s" },
    { value: "10000", label: "10s" },
    { value: "15000", label: "15s" },
  ], []);

  const showingTotal = filtered.length;
  const totalEvents = normalized.length;

  return (
    <section className="activity activity-modern">
      <div className="panel activity-main">
        <div className="activity-header">
          <div>
            <h2 className="title-lg" style={{marginTop:0}}>Activity Stream</h2>
            <span className="help">Updated {logsAt || "—"}{logsLoading ? " • refreshing…" : ""}</span>
          </div>
          <div className="activity-header-actions">
            <button className={`btn ${logsAuto ? "brand" : ""}`} onClick={() => setLogsAuto(!logsAuto)}>
              {logsAuto ? "Auto refresh: On" : "Auto refresh: Off"}
            </button>
            <button className="btn" onClick={refreshLogs} disabled={logsLoading}>{logsLoading ? "Refreshing…" : "Refresh now"}</button>
            <button className="btn ghost" onClick={() => exportCsv(logs)} disabled={!logs.length}>Export CSV</button>
          </div>
        </div>
        <div className="activity-toolbar">
          <div className="field">
            <span className="label">Source</span>
            <NiceSelect
              value={logsSource}
              onChange={(v)=>{ setLogsSource((v as any) as ("system"|"autopilot")); setTimeout(()=>refreshLogs(), 0); }}
              options={[{value:"system",label:"System"},{value:"autopilot",label:"Autopilot"}]}
              width="100%"
            />
          </div>
          <div className="field">
            <span className="label">Symbol (optional)</span>
            <input className="input search" value={logSymbol}
                   onChange={e=>setLogSymbol(e.target.value)}
                   placeholder="US.AAPL" />
          </div>
          <div className="field">
            <span className="label">Since (hours)</span>
            <input className="input" type="number" value={logSince}
                   onChange={e=>setLogSince(parseInt(e.target.value)||0)} />
          </div>
          <div className="field">
            <span className="label">Limit</span>
            <input className="input" type="number" value={logLimit}
                   onChange={e=>setLogLimit(parseInt(e.target.value)||0)} />
          </div>
          <div className="field">
            <span className="label">Refresh cadence</span>
            <NiceSelect
              value={String(logsEvery)}
              onChange={(v)=>setLogsEvery(parseInt(v) || logsEvery)}
              options={refreshChoices}
              width="100%"
            />
          </div>
        </div>
        <div className="activity-filters-row">
          <span className="activity-count">{`Showing ${showingTotal} of ${totalEvents} events`}</span>
          <div className="activity-filters">
            {categoryOptions.map(cat => {
              const count = cat === "All" ? totalEvents : (categoryCounts.get(cat) || 0);
              return (
                <button
                  key={cat}
                  className={`filter-chip ${activeCategory === cat ? "active" : ""}`}
                  onClick={() => setActiveCategory(cat)}
                  type="button"
                >
                  {cat}
                  <span className="count">{count}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="activity-feed">
          {filtered.length ? filtered.map(entry => {
            const qtyLabel = entry.qty != null ? entry.qty.toLocaleString() : null;
            const priceLabel = entry.price != null
              ? entry.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
              : null;
            const toneClass = entry.tone !== "neutral" ? entry.tone : "";
            const sideClass = entry.sideClass ? entry.sideClass.toLowerCase() : "";
            return (
              <div key={entry.key} className={`activity-event ${toneClass}`}>
                <div className="activity-event__time">
                  <span className="ago">{entry.when || "—"}</span>
                  <span className="exact">{entry.exact}</span>
                </div>
                <div className="activity-event__body">
                  <div className="meta-top">
                    <span className="stage">{entry.category || "Update"}</span>
                    {entry.symbol && <span className="symbol">{entry.symbol}</span>}
                    {entry.side && <span className={`side ${sideClass}`}>{entry.side}</span>}
                    {qtyLabel && <span className="mono">Qty {qtyLabel}</span>}
                    {priceLabel && <span className="mono">@ {priceLabel}</span>}
                  </div>
                  <div className="meta-bottom">
                    <span className="action">{entry.actionLabel || "—"}</span>
                    {entry.reason && <span className="reason">{entry.reason}</span>}
                  </div>
                </div>
                <div className="activity-event__status">
                  <span className={`status ${entry.tone !== "neutral" ? entry.tone : "neutral"}`}>{entry.status}</span>
                  <button className="btn ghost" onClick={() => onExplain(entry.raw)}>Explain</button>
                </div>
              </div>
            );
          }) : (
            <div className="activity-empty">
              <span>{logs.length ? "No log entries match this view." : "No log entries yet."}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );

  function exportCsv(rows: any[]) {
    if (!rows?.length) { alert("No rows to export"); return; }
    const cols = ["ts","mode","action","symbol","side","qty","price","reason","status"];
    const escape = (s:any) => String(s ?? "").replace(/"/g,'""');
    const csv = [cols.join(",")].concat(rows.map(r=>cols.map(c=>`"${escape(r[c])}"`).join(","))).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `activity_${new Date().toISOString().replace(/[:.]/g,"-")}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }
}

function ActiveStrategies({ onStopped, refreshKey }: { onStopped?: () => void; refreshKey?: number }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(()=>{ refresh(); }, []);           // initial load
  useEffect(()=>{ refresh(); }, [refreshKey]); // reload after Kill Switch

  async function refresh() {
    try {
      setLoading(true);
      const ls = await GET<any[]>("/automation/strategies");
      setItems((ls || []).filter((s:any)=>s.active));
    } finally {
      setLoading(false);
    }
  }

  async function stop(id: number) {
    try {
      await SEND(`/automation/stop/${id}`, {}, "POST");
      onStopped?.();  // this will bump stratRefreshTick in App
      refresh();
    } catch {}
  }

  return (
    <div className="stack">
      <div className="row">
        <button className="btn" onClick={refresh}>{loading?"Refreshing…":"Refresh"}</button>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr>{["id","name","symbol","active","actions"].map(h=><th key={h}>{h}</th>)}</tr></thead>
          <tbody>
            {(items?.length?items:[]).map((s:any)=>(
              <tr key={s.id}>
                <td>{s.id}</td><td>{s.name}</td><td>{s.symbol}</td>
                <td>{String(s.active)}</td>
                <td>{s.active && <button className="btn red" onClick={()=>stop(Number(s.id))}>Stop</button>}</td>
              </tr>
            ))}
            {!items?.length && <tr><td>No strategies</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Strategies catalog
function StrategyCatalog({ connected }: { connected: boolean }) {
  const [kind, setKind] = useLocalStorage<StrategyKind>("strat.kind", "ma-crossover");

  // shared
  const [symbol, setSymbol] = useLocalStorage("strat.symbol", "US.AAPL");

  // ma-crossover params
  const [fast, setFast] = useLocalStorage("strat.ma.fast", 20);
  const [slow, setSlow] = useLocalStorage("strat.ma.slow", 50);
  const [ktype, setKType] = useLocalStorage("strat.ma.ktype", "K_1M");
  const [interval, setIntervalSec] = useLocalStorage("strat.ma.interval", 15);
  const [qty, setQty] = useLocalStorage("strat.ma.qty", 1.0);
  const [sizeMode, setSizeMode] = useLocalStorage<"shares"|"usd">("strat.ma.sizeMode", "shares");
  const [dollarSize, setDollarSize] = useLocalStorage("strat.ma.dollar", 0.0);
  const [allowReal, setAllowReal] = useLocalStorage("strat.ma.allowReal", false);

  // grid (placeholder fields)
  const [gridFast, setGridFast] = useLocalStorage("strat.grid.fast", 20);
  const [gridSlow, setGridSlow] = useLocalStorage("strat.grid.slow", 50);

  // presets (localStorage-based)
  const PRESETS_KEY = "strat.presets.v1";
  const [presets, setPresets] = useState<Record<string, any>>(() => {
    try { return JSON.parse(localStorage.getItem(PRESETS_KEY) || "{}"); } catch { return {}; }
  });
  function savePresets(next: Record<string, any>) {
    setPresets(next);
    try { localStorage.setItem(PRESETS_KEY, JSON.stringify(next)); } catch {}
  }
  function makePresetPayload() {
    if (kind === "ma-crossover") {
      return { kind, symbol, fast, slow, ktype, interval_sec: interval, qty, size_mode: sizeMode, dollar_size: dollarSize, allow_real: allowReal };
    } else {
      return { kind, symbol, fast: gridFast, slow: gridSlow };
    }
  }
  function onSavePreset() {
    const name = prompt("Preset name?");
    if (!name) return;
    const next = { ...presets, [name]: makePresetPayload() };
    savePresets(next);
  }
  function onLoadPreset(name: string) {
    const p = presets[name];
    if (!p) return;
    setKind(p.kind as StrategyKind);
    setSymbol(p.symbol || symbol);
    if (p.kind === "ma-crossover") {
      setFast(p.fast ?? fast); setSlow(p.slow ?? slow); setKType(p.ktype ?? ktype);
      setIntervalSec(p.interval_sec ?? interval); setQty(p.qty ?? qty);
      setSizeMode((p.size_mode as any) ?? sizeMode); setDollarSize(p.dollar_size ?? dollarSize);
      setAllowReal(!!p.allow_real);
    } else {
      setGridFast(p.fast ?? gridFast); setGridSlow(p.slow ?? gridSlow);
    }
  }
  function onDeletePreset(name: string) {
    const next = { ...presets }; delete next[name]; savePresets(next);
  }

  async function startStrategy() {
    if (!connected) { alert("Not connected"); return; }
    if (kind === "ma-crossover") {
      const payload = {
        symbol, fast, slow, ktype,
        qty, size_mode: sizeMode, dollar_size: dollarSize,
        interval_sec: interval, allow_real: allowReal,
      };
      try { await api.startMA(payload); alert("MA strategy started."); }
      catch (e:any) { alert(`Start failed: ${brief(e)}`); }
    } else {
      alert("Grid live start requires a /automation/start/ma-grid endpoint. (Backtest supports grid.)");
    }
  }

  function brief(err: any) {
    try { const j = JSON.parse(String(err?.message || err)); return j?.detail || err?.message || String(err); }
    catch { return err?.message || String(err); }
  }

  return (
    <div className="panel">
      <h2 style={{marginTop:0,marginBottom:10}}>Strategies</h2>
      <div className="form-row">
        <div>
          <div className="label">Strategy</div>
          <NiceSelect
            value={kind}
            onChange={(v)=>setKind(v as StrategyKind)}
            options={[
              { value: "ma-crossover", label: "MA Crossover" },
              { value: "ma-grid", label: "MA Grid (beta)"},
            ]}
            width={200}
          />
        </div>
        <div>
          <div className="label">Symbol</div>
          <input className="input" value={symbol} onChange={e=>setSymbol(e.target.value)} />
        </div>
        <div style={{display:"flex", alignItems:"flex-end", gap:12}}>
          <button className="btn brand" onClick={startStrategy} disabled={!connected}>Start</button>
          <button className="btn" onClick={onSavePreset}>Save Preset</button>
          <PresetPicker presets={presets} onLoad={onLoadPreset} onDelete={onDeletePreset}/>
        </div>
      </div>

      {kind === "ma-crossover" ? (
        <>
          <div className="form-row" style={{marginTop:12}}>
            <div><div className="label">Fast MA</div><input className="input" type="number" value={fast} onChange={e=>setFast(parseInt(e.target.value)||1)} /></div>
            <div><div className="label">Slow MA</div><input className="input" type="number" value={slow} onChange={e=>setSlow(parseInt(e.target.value)||2)} /></div>
            <div><div className="label">KType</div>
              <NiceCombobox
                value={ktype}
                onChange={setKType}
                options={["K_1M","K_5M","K_15M","K_30M","K_60M","K_1D"].map(k=>({value:k,label:k}))}
                width="100%"
                placeholder="Search ktype…"
              />
            </div>
          </div>
          <div className="form-row">
            <div><div className="label">Interval (sec)</div><input className="input" type="number" value={interval} onChange={e=>setIntervalSec(parseInt(e.target.value)||1)} /></div>
            <div><div className="label">Qty (shares)</div><input className="input" type="number" value={qty} onChange={e=>setQty(parseFloat(e.target.value)||0)} /></div>
            <div>
              <div className="label">Size Mode</div>
              <NiceSelect
                value={sizeMode}
                onChange={(v)=>setSizeMode(v as any)}
                options={[{value:"shares",label:"shares"},{value:"usd",label:"usd"}]}
                width="100%"
              />
            </div>
          </div>
          <div className="form-row">
            <div><div className="label">Dollar Size</div><input className="input" type="number" value={dollarSize} onChange={e=>setDollarSize(parseFloat(e.target.value)||0)} /></div>
            <div>
              <div className="label">Allow Real Trading</div>
              <NiceSelect
                value={String(allowReal)}
                onChange={(v)=>setAllowReal(v==="true")}
                options={[{value:"false",label:"False"},{value:"true",label:"True"}]}
                width="100%"
              />
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="form-row" style={{marginTop:12}}>
            <div><div className="label">Fast MA</div><input className="input" type="number" value={gridFast} onChange={e=>setGridFast(parseInt(e.target.value)||1)} /></div>
            <div><div className="label">Slow MA</div><input className="input" type="number" value={gridSlow} onChange={e=>setGridSlow(parseInt(e.target.value)||2)} /></div>
          </div>
          <div className="help" style={{marginTop:4}}>
            Live Grid start requires a server endpoint <code>/automation/start/ma-grid</code>. Backtest is available in the Backtest tab.
          </div>
        </>
      )}
    </div>
  );
}

function PresetPicker({ presets, onLoad, onDelete }:{ presets: Record<string, any>, onLoad:(n:string)=>void, onDelete:(n:string)=>void }) {
  const names = Object.keys(presets);
  const [sel, setSel] = useState(names[0] || "");
  useEffect(()=>{ if (!names.includes(sel)) setSel(names[0] || ""); }, [JSON.stringify(names)]);
  if (!names.length) return <span className="help">No presets yet.</span>;
  return (
    <div className="row" style={{alignItems:"flex-end"}}>
      <div>
        <div className="label">Presets</div>
        <NiceCombobox
          value={sel}
          onChange={setSel}
          options={names.map(n=>({value:n,label:n}))}
          width={180}
          placeholder="Search presets…"
        />
      </div>
      <button className="btn" onClick={()=>onLoad(sel)} disabled={!sel}>Load</button>
      <button className="btn red" onClick={()=>onDelete(sel)} disabled={!sel}>Delete</button>
</div>
  );
}

// Backtest panel removed per new design


function StrategyPicker() {
  const CATALOG: { key: string; name: string; desc?: string }[] = [
    { key: "ma-crossover", name: "MA Crossover", desc: "Fast/slow cross with RSI gate" },
    { key: "rsi-gate", name: "RSI Gate", desc: "Enter on RSI cross; avoid extremes" },
    { key: "breakout-retest", name: "Breakout Retest", desc: "Range breakout then retest confirm" },
    { key: "mean-reversion", name: "Mean Reversion", desc: "Fade stretches (RSI)" },
    { key: "atr-trailer", name: "ATR Trailing Stop", desc: "Trend-follow with MA" },
    { key: "news-momo", name: "News Momentum", desc: "Spike-follow with risk caps" },
  ];
  const [selected, setSelected] = useLocalStorage<string[]>("pref.strategies", ["ma-crossover"]);

  // Map UI keys to backend signal strategy keys
  function mapToBackend(key: string): { signals?: Record<string, boolean>; newsEnabled?: boolean } {
    switch (key) {
      case "ma-crossover":
        return { signals: { macd_cross: true } };
      case "rsi-gate":
        return { signals: { stoch_rsi_extreme: true } };
      case "breakout-retest":
        return { signals: { bb_breakout: true } };
      case "mean-reversion":
        return { signals: { rsi_extreme: true } };
      case "atr-trailer":
        return { signals: { ma_trend: true } };
      case "news-momo":
        return { newsEnabled: true };
      default:
        return {};
    }
  }

  // Initialize from backend so toggles reflect real state
  useEffect(() => { (async () => {
    try {
      const sig = await api.getSignalsSettings();
      const news = await api.getNewsSettings();
      const enabled: string[] = [];
      if (sig?.strategies?.macd_cross) enabled.push("ma-crossover");
      if (sig?.strategies?.stoch_rsi_extreme) enabled.push("rsi-gate");
      if (sig?.strategies?.bb_breakout) enabled.push("breakout-retest");
      if (sig?.strategies?.rsi_extreme) enabled.push("mean-reversion");
      if (sig?.strategies?.ma_trend) enabled.push("atr-trailer");
      if (news?.enabled) enabled.push("news-momo");
      // keep any previously selected unknowns
      const known = new Set(CATALOG.map(s=>s.key));
      const prev = (selected || []).filter(k => !known.has(k));
      const merged = Array.from(new Set([...prev, ...enabled]));
      setSelected(merged);
    } catch {}
  })(); }, []);

  async function persistToggle(key: string, on: boolean) {
    // Persist to backend based on mapping
    const mapped = mapToBackend(key);
    try {
      if (mapped.signals) {
        // read existing to merge
        const cur = await api.getSignalsSettings();
        const next = { ...(cur?.strategies || {}) } as Record<string, boolean>;
        for (const k of Object.keys(mapped.signals)) next[k] = on;
        await api.putSignalsSettings({ strategies: next });
      } else if (mapped.newsEnabled !== undefined) {
        await api.putNewsSettings({ enabled: on });
      } else {
        // Unsupported today: no-op (kept locally)
      }
    } catch {}
  }
  function toggle(k: string) {
    setSelected(sel => {
      const on = !sel.includes(k);
      persistToggle(k, on);
      return on ? sel.concat(k) : sel.filter(x=>x!==k);
    });
  }
  return (
    <div className="stack">
      <div className="row" style={{justifyContent:"space-between", alignItems:"center", marginTop:2}}>
        <div className="help" style={{fontWeight:700}}>Selected: <b>{selected.length}</b> / {CATALOG.length}</div>
        <div className="row" style={{gap:8}}>
          <button className="btn" onClick={async()=>{
            const keys = CATALOG.map(s=>s.key);
            setSelected(keys);
            try {
              const cur = await api.getSignalsSettings();
              const next = { ...(cur?.strategies || {}) } as Record<string, boolean>;
              next.macd_cross = true; next.stoch_rsi_extreme = true; next.bb_breakout = true; next.rsi_extreme = true; next.ma_trend = true;
              await api.putSignalsSettings({ strategies: next });
              await api.putNewsSettings({ enabled: true });
            } catch {}
          }}>All</button>
          <button className="btn amber" onClick={async()=>{
            setSelected([]);
            try {
              const cur = await api.getSignalsSettings();
              const next = { ...(cur?.strategies || {}) } as Record<string, boolean>;
              next.macd_cross = false; next.stoch_rsi_extreme = false; next.bb_breakout = false; next.rsi_extreme = false; next.ma_trend = false;
              await api.putSignalsSettings({ strategies: next });
              await api.putNewsSettings({ enabled: false });
            } catch {}
          }}>Clear</button>
        </div>
      </div>
      <div className="strat-grid">
        {CATALOG.map(s => {
          const on = selected.includes(s.key);
          return (
            <div key={s.key} className={`strat ${on ? "on" : ""}`} onClick={()=>toggle(s.key)} role="button" aria-pressed={on}>
              <span className={`dot ${on ? "green" : "red"}`} />
              <div className="info">
                <div className="name">{s.name}</div>
                <div className="desc">{s.desc || ""}</div>
              </div>
              <span className={`badge-mini ${on ? "good" : ""}`}>{on ? "On" : "Off"}</span>
            </div>
          );
        })}
      </div>
      <div className="help" style={{marginTop:6}}></div>
    </div>
  );
}

/** Compact number input with custom, backgroundless arrows.
 *  Arrows use the same color as labels (var(--muted)).
 */
/** Compact number input with custom, backgroundless arrows.
 *  Arrows use the same color as labels (var(--muted)).
 *  Allows clearing the field while editing; value is validated on blur/Enter.
 */

function Num({
  value,
  setValue,
  step = 1,
  min,
  max,
  inputProps = {},
}: {
  value: number;
  setValue: (n: number) => void;
  step?: number;
  min?: number;
  max?: number;
  inputProps?: React.InputHTMLAttributes<HTMLInputElement>;
}) {
  const ref = useRef<HTMLInputElement | null>(null);
  const [text, setText] = useState<string>(
    Number.isFinite(value) ? String(value) : ""
  );

  useEffect(() => {
    // Sync from external value when not actively editing
    if (document.activeElement !== ref.current) {
      setText(Number.isFinite(value) ? String(value) : "");
    }
  }, [value]);

  const valid = (s: string) => /^-?\d*\.?\d*$/.test(s);

  function clamp(n: number) {
    if (min != null && n < min) n = min as number;
    if (max != null && n > max) n = max as number;
    return n;
  }

  function commit() {
    // If empty or partial number, settle to a safe value
    if (text === "" || text === "-" || text === "." || text === "-.") {
      const fallback = min != null ? Math.max(0, min) : 0;
      setValue(fallback);
      setText(String(fallback));
      return;
    }
    const n = clamp(Number(text));
    setValue(n);
    setText(String(n));
  }

  function bump(dir: 1 | -1) {
    const cur =
      text === "" || text === "-" || text === "." || text === "-."
        ? (Number.isFinite(value) ? value : 0)
        : Number(text);
    const s = Number(step) || 1;
    const next = clamp(Number((cur + dir * s).toFixed(6)));
    setValue(next);
    setText(String(next));
  }

  return (
    <div className="num">
      <input
        ref={ref}
        className="input"
        type="text"
        inputMode="decimal"
        value={text}
        onChange={(e) => {
          const s = e.target.value;
          if (valid(s)) setText(s);
        }}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === "NumpadEnter") { e.preventDefault(); commit(); (e.currentTarget as HTMLInputElement).blur(); } }}
        {...inputProps}
      />
      <span className="spin" aria-hidden="true">
        <button type="button" onClick={() => bump(1)} title="Increase">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 6l6 6H6z" />
          </svg>
        </button>
        <button type="button" onClick={() => bump(-1)} title="Decrease">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 18l-6-6h12z" />
          </svg>
        </button>
      </span>
    </div>
  );
}

function TradingPreferences() {
  const [winRate, setWinRate] = useLocalStorage<number>("pref.winRate", 55);
  const [rr, setRR] = useLocalStorage<number>("pref.rr", 1.5);
  const [stopLoss, setStopLoss] = useLocalStorage<number>("pref.stop", 1.0);
  const [takeProfit, setTakeProfit] = useLocalStorage<number>("pref.tp", 2.0);
  const [measuredMove, setMeasuredMove] = useLocalStorage<number>("pref.mm", 1.0);
  const [maxDD, setMaxDD] = useLocalStorage<number>("pref.maxdd", 5.0);
  const [loaded, setLoaded] = useState(false);
  const [saveTick, setSaveTick] = useState(0);

  // Load from server once
  useEffect(() => {
    (async () => {
      try {
        const p = await api.getAutoPrefs();
        if (p && typeof p === 'object') {
          if (p.target_winrate_pct != null) setWinRate(Number(p.target_winrate_pct));
          if (p.target_rr != null) setRR(Number(p.target_rr));
          if (p.stop_loss_pct != null) setStopLoss(Number(p.stop_loss_pct));
          if (p.take_profit_pct != null) setTakeProfit(Number(p.take_profit_pct));
          if (p.measured_move_atr_mult != null) setMeasuredMove(Number(p.measured_move_atr_mult));
          if (p.max_dd_pct != null) setMaxDD(Number(p.max_dd_pct));
        }
      } catch {}
      setLoaded(true);
    })();
  }, []);

  // Auto-save when values change (debounced)
  useEffect(() => {
    if (!loaded) return;
    const id = window.setTimeout(async () => {
      try {
        await api.putAutoPrefs({
          target_winrate_pct: winRate,
          target_rr: rr,
          stop_loss_pct: stopLoss,
          take_profit_pct: takeProfit,
          measured_move_atr_mult: measuredMove,
          max_dd_pct: maxDD,
        });
        setSaveTick((t: number) => t + 1);
      } catch {
        // silent in UI; backend logs
      }
    }, 500);
    return () => window.clearTimeout(id);
  }, [loaded, winRate, rr, stopLoss, takeProfit, measuredMove, maxDD]);
  return (
    <div className="stack">
      <div className="form-row prefs-grid">
        <div>
          <div className="label">Target win rate (%)</div>
          <Num value={winRate} setValue={setWinRate} step={1} min={0} max={100} />
        </div>
        <div>
          <div className="label">Reward ratio (R)</div>
          <Num value={rr} setValue={setRR} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Stop loss (% move)</div>
          <Num value={stopLoss} setValue={setStopLoss} step={0.1} min={0} />
        </div>
      </div>
      <div className="form-row">
        <div>
          <div className="label">Take profit (% move)</div>
          <Num value={takeProfit} setValue={setTakeProfit} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Measured move (ATR x)</div>
          <Num value={measuredMove} setValue={setMeasuredMove} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Max drawdown (%)</div>
          <Num value={maxDD} setValue={setMaxDD} step={0.1} min={0} max={100} />
        </div>
      </div>
    </div>
  );
}








function PreferenceIndicators({ autoStatus }: { autoStatus: any }) {
  // pull targets saved by Trading Preferences
  const getNum = (k: string, def: number) => {
    try { const raw = localStorage.getItem(k); if (!raw) return def; const v = JSON.parse(raw); return (typeof v === "number" ? v : Number(v) || def); }
    catch { const raw = localStorage.getItem(k); const n = Number(raw); return isFinite(n) ? n : def; }
  };
  const T = {
    win: getNum("pref.winRate", 55),
    r:   getNum("pref.rr", 1.5),
    dd:  getNum("pref.maxdd", 5),
  };

  const S = (autoStatus?.stats || {}) as any;
  const V = {
    win: Number.isFinite(S.win_rate_pct) ? Number(S.win_rate_pct) : NaN,
    r:   Number.isFinite(S.avg_r)        ? Number(S.avg_r)        : NaN,
    dd:  Number.isFinite(S.max_dd)       ? Number(S.max_dd)       : NaN,
  };

  type Row = { k: string; unit: string; target: number; value: number; higher: boolean };
  const rows: Row[] = [
    { k: "Win rate",     unit: "%", target: T.win, value: V.win, higher: true  },
    { k: "Reward ratio", unit: "R", target: T.r,   value: V.r,   higher: true  },
    { k: "Drawdown",     unit: "%", target: T.dd,  value: V.dd,  higher: false },
  ];

  const fmt = (v:number, unit:string, decimals=unit==="R"?2:0) =>
    (isFinite(v) ? `${Number(v.toFixed(decimals))}${unit}` : `—${unit}`);

  const Chip = ({ row }: { row: Row }) => {
    const hasLive = isFinite(row.value);
    if (!isFinite(row.target) || row.target === 0) {
      return <span className="delta neutral">target —</span>;
    }
    if (!hasLive) {
      return <span className="delta neutral">target {fmt(row.target, row.unit)}</span>;
    }
    const better = row.higher ? (row.value >= row.target) : (row.value <= row.target);
    const cls = better ? "delta up" : "delta down";
    const arrow = better ? "↑" : "↓";
    return <span className={cls}>{arrow} {fmt(row.value, row.unit)} <span style={{opacity:.8}}>vs {fmt(row.target, row.unit)}</span></span>;
  };

  return (
    <div className="pref-list">
      {rows.map((r,i)=> (
        <div className="pref-row" key={i}>
          <div className="k">{r.k}</div>
          <Chip row={r} />
        </div>
      ))}
    </div>
  );
}

function StyleAndWatchlist() {
  const [styleRaw, setStyleRaw] = useState("");
  const [styleSummary, setStyleSummary] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const s = await api.getAutoStyle();
        setStyleRaw(s?.raw || "");
        setStyleSummary(s?.summary || "");
      } catch {}
    })();
  }, []);

  async function saveStyle() {
    if (!styleRaw.trim()) return;
    try {
      setBusy(true);
      const r = await api.postAutoStyle(styleRaw);
      setStyleSummary(r?.summary || "");
    } finally {
      setBusy(false);
    }
  }

  async function deleteStyle() {
    try {
      setBusy(true);
      await api.deleteAutoStyle();
      setStyleRaw("");
      setStyleSummary("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="form-row">
        <div style={{flex:1}}>
          <div className="label">Style (natural language)</div>
          <textarea className="input" rows={4} value={styleRaw} onChange={e=>setStyleRaw(e.target.value)} placeholder="Describe your trading preferences, constraints, and style…" />
          <div className="row" style={{justifyContent:"space-between", marginTop:6}}>
            <div className="help">Write preferences like: "Focus on short-term trades, prefer small-caps, avoid biotech."</div>
            <div className="row" style={{gap:8}}>
              <button className="btn" onClick={deleteStyle} disabled={busy || (!styleRaw && !styleSummary)}>Delete Style</button>
              <button className="btn brand" onClick={saveStyle} disabled={busy || !styleRaw.trim()}>Summarize & Save</button>
            </div>
          </div>
        </div>
      </div>
      {styleSummary ? (
        <div className="panel compact" style={{background:"#0e1320"}}>
          <div className="label">Saved Style Summary</div>
          <div className="help" style={{whiteSpace:"pre-wrap"}}>{styleSummary}</div>
        </div>
      ) : null}
    </div>
  );
}

function DiscoverySettings() {
  const [discEnabled, setDiscEnabled] = useState<boolean>(true);
  const [discOnly, setDiscOnly] = useState<boolean>(false);
  const [seed, setSeed] = useState<string>("");
  const [preview, setPreview] = useState<string[]>([]);
  const [newsEnabled, setNewsEnabled] = useState<boolean>(true);
  const [newsTtl, setNewsTtl] = useState<number>(1800);
  const [newsProvider, setNewsProvider] = useState<string>("heuristic");
  const [ktype, setKtype] = useState<string>("K_DAY");
  const [barsTtl, setBarsTtl] = useState<number>(60);
  const [execMode, setExecMode] = useState<"sim"|"moomoo">("sim");
  const [dealsSync, setDealsSync] = useState<number>(180);
  const [dataSource, setDataSource] = useState<string>("futu");
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => {
    try {
      const d = await api.getDiscovery();
      setDiscEnabled(!!d?.enabled);
      setDiscOnly(!!d?.only);
      setSeed(Array.isArray(d?.seed) ? (d?.seed as string[]).join("\n") : "");
      setPreview(Array.isArray(d?.preview) ? d.preview : []);
    } catch {}
    try {
      const n = await api.getNewsSettings();
      setNewsEnabled(!!n?.enabled);
      setNewsTtl(Number(n?.ttl_sec || 1800));
      if (n?.provider) setNewsProvider(String(n.provider));
    } catch {}
    try {
      const dset = await api.getDataSettings();
      setKtype(String(dset?.ktype || "K_DAY"));
      setBarsTtl(Number(dset?.bars_ttl_sec || 60));
      if (dset?.deals_sync_sec != null) setDealsSync(Number(dset.deals_sync_sec));
      if (dset?.data_source) setDataSource(String(dset.data_source));
    } catch {}
    try {
      const em = await api.getExecMode(); setExecMode((em?.mode as any) || "sim");
    } catch {}
  })(); }, []);

  async function saveDiscovery() {
    setSaving(true);
    try {
      const parsed = seed.split(/\n+/).map(s=>s.trim()).filter(Boolean);
      await api.putDiscovery({ enabled: discEnabled, only: discOnly, seed: parsed });
      const d = await api.getDiscovery();
      setPreview(Array.isArray(d?.preview) ? d.preview : []);
    } finally { setSaving(false); }
  }
  async function saveNews() {
    setSaving(true);
    try {
      await api.putNewsSettings({ enabled: newsEnabled, ttl_sec: Number(newsTtl)||1800, provider: newsProvider });
      await api.putDataSettings({ ktype, bars_ttl_sec: Number(barsTtl)||60, deals_sync_sec: Number(dealsSync)||180, data_source: dataSource });
      await api.putExecMode(execMode);
    } finally { setSaving(false); }
  }

  return (
    <div className="stack">
      <div className="form-row">
        <div>
          <div className="label">Discovery Enabled</div>
          <NiceSelect
            value={String(discEnabled)}
            onChange={(v)=>setDiscEnabled(v==="true")}
            options={[{value:"true",label:"True"},{value:"false",label:"False"}]}
            width="100%"
          />
        </div>
        <div>
          <div className="label">Dynamic Only (no watchlist)</div>
          <NiceSelect
            value={String(discOnly)}
            onChange={(v)=>setDiscOnly(v==="true")}
            options={[{value:"false",label:"False"},{value:"true",label:"True"}]}
            width="100%"
          />
        </div>
        <div>
          <div className="label">Use News</div>
          <NiceSelect
            value={String(newsEnabled)}
            onChange={(v)=>setNewsEnabled(v==="true")}
            options={[{value:"true",label:"True"},{value:"false",label:"False"}]}
            width="100%"
          />
        </div>
        <div>
          <div className="label">News Provider</div>
          <NiceSelect
            value={newsProvider}
            onChange={(v)=>setNewsProvider(v)}
            options={[{value:"heuristic",label:"Heuristic"},{value:"gpt",label:"GPT"}]}
            width="100%"
          />
        </div>
        <div>
          <div className="label">News TTL (sec)</div>
          <input className="input" type="number" value={newsTtl} onChange={(e)=>setNewsTtl(parseInt(e.target.value)||1800)} />
        </div>
        <div>
          <div className="label">Timeframe (KType)</div>
          <NiceSelect
            value={ktype}
            onChange={(v)=>setKtype(v as string)}
            options={["K_1M","K_5M","K_15M","K_30M","K_60M","K_DAY"].map(k=>({value:k,label:k}))}
            width="100%"
          />
        </div>
        <div>
          <div className="label">Data Source</div>
          <NiceSelect
            value={dataSource}
            onChange={(v)=>setDataSource(v as string)}
            options={[{value:"futu",label:"Moomoo"},{value:"yfinance",label:"Yahoo Finance"}]}
            width="100%"
          />
        </div>
        <div>
          <div className="label">Bars cache TTL (sec)</div>
          <input className="input" type="number" value={barsTtl} onChange={(e)=>setBarsTtl(parseInt(e.target.value)||60)} />
        </div>
        <div>
          <div className="label">Execution Backend</div>
          <NiceSelect
            value={execMode}
            onChange={(v)=>setExecMode((v as any) as ("sim"|"moomoo"))}
            options={[{value:"sim",label:"SIM"},{value:"moomoo",label:"Moomoo"}]}
            width="100%"
          />
        </div>
        <div>
          <div className="label">Deals sync (sec)</div>
          <input className="input" type="number" value={dealsSync} onChange={(e)=>setDealsSync(parseInt(e.target.value)||180)} />
        </div>
      </div>
      <div className="form-row">
        <div style={{flex:1}}>
          <div className="label">Discovery Seed (US.TICKER per line)</div>
          <textarea className="input" rows={4} value={seed} onChange={(e)=>setSeed(e.target.value)} placeholder={"US.AAPL\nUS.MSFT\nUS.TSLA"} />
        </div>
      </div>
      <div className="row" style={{gap:8, justifyContent:"flex-end"}}>
        <button className="btn" onClick={saveNews} disabled={saving}>Save News</button>
        <button className="btn brand" onClick={saveDiscovery} disabled={saving}>{saving?"Saving…":"Save Discovery"}</button>
      </div>
  <div className="panel compact" style={{background:"#0e1320"}}>
    <div className="label">Preview (Top Candidates)</div>
    <div className="help" style={{whiteSpace:"pre-wrap"}}>{preview?.length ? preview.join(", ") : "—"}</div>
  </div>
  <PlannerSettings />
    </div>
  );
}

function SignalsSettings() {
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);

  useEffect(() => { (async () => {
    try {
      const s = await api.getSignalsSettings();
      setWeights(s?.weights || {});
    } catch {}
    setLoading(false);
  })(); }, []);

  function setWeight(name: string, v: number) {
    setWeights(prev => ({ ...prev, [name]: v }));
  }
  async function save() {
    setSaving(true);
    try {
      await api.putSignalsSettings({ weights });
    } finally { setSaving(false); }
  }

  const stratNames = Object.keys(weights).length
    ? Object.keys(weights)
    : [
        "macd_cross",
        "bb_breakout",
        "stoch_rsi_extreme",
        "ma_trend",
        "rsi_extreme",
        "news",
      ];

  return (
    <div className="stack">
      <h3 style={{margin:"4px 0 8px", fontSize:14, color:"var(--muted)", textTransform:"uppercase", letterSpacing:".06em"}}>Signal Weights</h3>
      <div className="table-wrap" style={{marginTop:8}}>
        <table className="table-modern">
          <thead>
            <tr>
              <th>Strategy</th>
              <th className="num" style={{width:160}}>Weight</th>
            </tr>
          </thead>
          <tbody>
            {stratNames.map(name => (
              <tr key={name}>
                <td>{name}</td>
                <td className="num">
                  <input
                    className="input"
                    type="number"
                    step={0.1}
                    min={0}
                    max={2}
                    value={(weights[name] ?? 1.0)}
                    onChange={e=>setWeight(name, Math.max(0, Math.min(2, parseFloat(e.target.value)||0)))}
                    style={{maxWidth:120}}
                  />
                </td>
              </tr>
            ))}
            {!stratNames.length && (
              <tr><td colSpan={2}>No strategies found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="row" style={{marginTop:10, justifyContent:"flex-end"}}>
        <button className="btn brand" onClick={save} disabled={saving || loading}>{saving?"Saving…":"Save Weights"}</button>
      </div>
    </div>
  );
}

function PlannerSettings() {
  const [minConf, setMinConf] = useState<number>(0.6);
  const [topN, setTopN] = useState<number>(8);
  const [strict, setStrict] = useState<boolean>(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => {
    try {
      const p = await api.getPlannerSettings();
      setMinConf(Number(p?.min_confidence ?? 0.6));
      setTopN(Number(p?.top_n ?? 8));
      setStrict(!!p?.strict_prefs);
    } catch {}
  })(); }, []);

  async function save() {
    setSaving(true);
    try { await api.putPlannerSettings({ min_confidence: minConf, top_n: topN, strict_prefs: strict }); }
    finally { setSaving(false); }
  }

  return (
    <div className="panel compact" style={{marginTop:12}}>
      <h2 style={{marginTop:0}}>Planner</h2>
      <div className="form-row">
        <div>
          <div className="label">Min confidence (0–1)</div>
          <input className="input" type="number" step={0.01} min={0} max={1} value={minConf} onChange={(e)=>setMinConf(parseFloat(e.target.value)||0)} />
        </div>
        <div>
          <div className="label">Top‑N Universe</div>
          <input className="input" type="number" min={1} value={topN} onChange={(e)=>setTopN(parseInt(e.target.value)||8)} />
        </div>
        <div>
          <div className="label">Strict Prefs (require stop/TP)</div>
          <NiceSelect
            value={String(strict)}
            onChange={(v)=>setStrict(v==="true")}
            options={[{value:"false",label:"False"},{value:"true",label:"True"}]}
            width="100%"
          />
        </div>
        <div className="row" style={{alignItems:"flex-end", marginLeft:"auto"}}>
          <button className="btn brand" onClick={save} disabled={saving}>{saving?"Saving…":"Save Planner"}</button>
        </div>
      </div>
    </div>
  );
}
function setPnlSeries(arg0: any) {
  throw new Error('Function not implemented.');
}
