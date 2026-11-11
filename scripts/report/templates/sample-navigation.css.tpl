@@WINGS:scripts/report/view-navigation.css@@
.wse-sample-workspace > .wse-sample-content { grid-column:2; grid-row:1; min-width:0; }
.wings-sample-navigated #quarto-sidebar,.wings-sample-navigated #quarto-margin-sidebar { display:none !important; }
.wse-sample-back { display:block; position:sticky; top:0; z-index:2; margin:14px 12px 4px; padding:12px; border:2px solid #8C1D40; border-radius:8px; background:#8C1D40; color:#FFFFFF; font:700 14px/1.4 Arial,Helvetica,sans-serif; text-align:center; text-decoration:none; }
.wse-sample-back:hover { background:#FFC627; color:#000000; border-color:#000000; }
.wse-sample-back:focus-visible,.wse-view-navigator a:focus-visible { outline:3px solid #8C1D40; outline-offset:2px; }
.wse-sample-content section[id],.wse-sample-content h2[id] { scroll-margin-top:18px; }
@media(max-width:1050px) { .wse-sample-workspace > .wse-sample-content { grid-column:1; grid-row:2; } }

/* GenoFLU constellation: recorded calls, independent of segment QC status. */
.wgc-layout { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr); gap:20px; align-items:start; margin:20px 0; }
.wgc-stage { min-width:0; border:1px solid #8C1D4025; border-radius:14px; padding:12px; background:#FFFFFF; }
.wgc-svg { display:block; width:100%; max-height:640px; }
.wgc-segment { cursor:pointer; outline:none; }
.wgc-wedge { stroke:#8C1D40; stroke-width:2; }
.wgc-segment.is-selected .wgc-wedge,.wgc-segment:focus-visible .wgc-wedge { stroke:#FFC627; stroke-width:9; filter:drop-shadow(0 0 7px #FFC627); }
.wgc-segment-label { font:900 31px Arial,Helvetica,sans-serif; pointer-events:none; }
.wgc-call-label { font:800 19px Arial,Helvetica,sans-serif; pointer-events:none; }
.wgc-center-kicker { fill:#FFC627; font:800 13px Arial,Helvetica,sans-serif; letter-spacing:1px; }
.wgc-center-status { fill:#FFFFFF; font:800 25px Arial,Helvetica,sans-serif; }
.wgc-center-count { fill:#FFC627; font:700 15px Arial,Helvetica,sans-serif; }
.wgc-detail { min-width:0; padding:24px; border-top:7px solid #FFC627; border-radius:14px; background:#000000; color:#FFFFFF; }
.wgc-kicker { color:#FFC627; font-size:12px; font-weight:800; letter-spacing:.09em; }
.wgc-detail .wgc-segment-title { color:#FFFFFF; margin:8px 0 24px; font-size:40px; font-weight:900; }
.wgc-facts { margin:0; }
.wgc-facts > div { display:grid; gap:5px; padding:12px 0; border-top:1px solid #FFFFFF40; }
.wgc-facts dt { color:#FFC627; font-size:13px; font-weight:700; }
.wgc-facts dd { color:#FFFFFF; margin:0; font-size:20px; font-weight:800; overflow-wrap:anywhere; }
.wgc-legend { display:flex; justify-content:center; flex-wrap:wrap; gap:18px; font-size:13px; color:#000000; }
.wgc-legend span::before { content:''; display:inline-block; width:11px; height:11px; border:1px solid #8C1D40; border-radius:50%; margin-right:6px; }
.wgc-legend-recorded::before { background:#8C1D40; }
.wgc-legend-missing::before { background:#FFFFFF; }
.wgc-recorded-output { margin:18px 0; }
.wgc-recorded-output > summary { cursor:pointer; color:#8C1D40; font-weight:700; }
@media(max-width:1100px) { .wgc-layout { grid-template-columns:minmax(0,1fr); } }
.wse-sample-file-intro { margin:12px 0; line-height:1.5; }
.wse-sample-status-guide { margin:12px 0 22px; padding:12px 16px; border:1px solid #8C1D4025; border-left:4px solid #FFC627; border-radius:8px; background:#FFFFFF; }
.wse-sample-status-guide > summary { cursor:pointer; color:#8C1D40; font-weight:700; }
.wse-sample-status-guide > p,.wse-sample-status-guide > ul { margin-top:12px; }

/* Compact collection cards retain the recorded metadata values. */
.wings-sample-profile { margin:20px 0; border:1px solid #8C1D4030; border-top:6px solid #FFC627; border-radius:16px; background:#FFFFFF; color:#000000; overflow:hidden; }
.wsp-heading { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; padding:12px 16px; border-bottom:1px solid #8C1D4020; }
.wsp-kicker { color:#8C1D40; font-size:12px; font-weight:800; letter-spacing:.14em; }
.wsp-sample-id { color:#000000; font-size:15px; font-weight:700; overflow-wrap:anywhere; }
.wsp-layout { display:grid; grid-template-columns:130px minmax(120px,.8fr) minmax(160px,1.2fr) minmax(180px,1.3fr); gap:12px; align-items:stretch; padding:16px; max-width:1000px; box-sizing:border-box; }
.wsp-date,.wsp-card { min-width:0; min-height:148px; box-sizing:border-box; border-radius:12px; padding:16px; }
.wsp-date { display:flex; flex-direction:column; justify-content:center; align-items:center; gap:6px; background:#8C1D40; color:#FFFFFF; text-align:center; }
.wsp-date-label { color:#FFC627; font-size:11px; font-weight:800; letter-spacing:.12em; }
.wsp-calendar { display:grid; gap:4px; }
.wsp-day { font-size:48px; font-weight:900; line-height:1.05; }
.wsp-month { color:#FFC627; font-size:14px; font-weight:800; }
.wsp-date-raw { font-size:18px; overflow-wrap:anywhere; }
.wsp-card { display:flex; flex-direction:column; justify-content:center; align-items:flex-start; gap:10px; border:1px solid #8C1D4030; border-top:4px solid #FFC627; background:#FFFFFF; }
.wsp-label { color:#8C1D40; font-size:11px; font-weight:800; letter-spacing:.08em; }
.wsp-host-value { font-size:28px; font-weight:900; line-height:1.2; overflow-wrap:anywhere; }
.wsp-specimen,.wsp-location { color:#000000; font-size:23px; font-weight:800; line-height:1.4; overflow-wrap:anywhere; }
.wsp-coordinates { display:flex; flex-wrap:wrap; gap:6px 14px; margin:0; }
.wsp-coordinates > div { display:grid; gap:2px; }
.wsp-coordinates dt { color:#8C1D40; font-size:10px; font-weight:700; }
.wsp-coordinates dd { margin:0; color:#000000; font-size:12px; font-weight:600; overflow-wrap:anywhere; }
.wsp-extra { display:flex; flex-wrap:wrap; gap:12px; margin:0; padding:0 16px 16px; }
.wsp-extra > div { padding:12px 16px; border:1px solid #8C1D4030; border-radius:12px; max-width:100%; box-sizing:border-box; }
.wsp-extra dt { font-size:11px; font-weight:700; color:#8C1D40; }
.wsp-extra dd { margin:5px 0 0; font-size:15px; font-weight:700; color:#000000; overflow-wrap:anywhere; }
@container wings-sample-profile (max-width:720px) { .wsp-layout { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@container wings-sample-profile (max-width:360px) { .wsp-layout { grid-template-columns:minmax(0,1fr); } }
.wings-sample-profile { container-type:inline-size; container-name:wings-sample-profile; }
@supports not (container-type:inline-size) { @media(max-width:1200px) { .wsp-layout { grid-template-columns:repeat(2,minmax(0,1fr)); } } @media(max-width:450px) { .wsp-layout { grid-template-columns:minmax(0,1fr); } } }
