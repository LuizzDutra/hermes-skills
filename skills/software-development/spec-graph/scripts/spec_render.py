#!/usr/bin/env python3
"""Render a spec-graph YAML file as a single-file interactive HTML graph.

Usage:
    python spec_render.py .specs/order-lifecycle/spec.yaml
    python spec_render.py spec.yaml --out graph.html --results results.json
    python spec_render.py spec.yaml --diff previous.yaml     # highlight changes

The output is dependency-free (no CDN, no fonts): open it directly or show it
in the Hermes preview pane with a ::preview{file="..."} line.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_model import SpecError, build_payload, dump_payload, load_spec, validate  # noqa: E402


def load_results(path: str | None) -> dict | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def diff_specs(old_data: dict, new_data: dict) -> dict:
    """Compare behaviour-level content between two spec versions."""

    def index(data: dict) -> dict:
        out = {}
        for beh in data.get("behaviours") or []:
            if isinstance(beh, dict) and beh.get("id"):
                out[str(beh["id"])] = json.dumps(beh, sort_keys=True, ensure_ascii=False)
        return out

    old, new = index(old_data), index(new_data)
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(bid for bid in set(old) & set(new) if old[bid] != new[bid]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", help="path to spec.yaml")
    parser.add_argument("--repo", help="repository root (default: discovered)")
    parser.add_argument("--out", help="output HTML (default: <spec dir>/graph.html)")
    parser.add_argument("--results", help="results.json produced by spec_verify.py")
    parser.add_argument("--diff", help="previous spec.yaml to diff against")
    parser.add_argument("--no-refs", action="store_true", help="skip file/symbol existence checks")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        spec = load_spec(args.spec, args.repo)
    except SpecError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    report = validate(spec.data, spec.root, check_refs=not args.no_refs)
    results = load_results(args.results)
    diff = None
    if args.diff:
        from spec_model import parse_yaml

        old = parse_yaml(Path(args.diff).read_text(encoding="utf-8")) or {}
        diff = diff_specs(old, spec.data)
        if spec.data.get("delta_of"):
            # a delta only carries what changes; the untouched behaviours are not "removed"
            diff["removed"] = []

    payload = build_payload(spec, report, results=results, diff=diff, check_refs=not args.no_refs)
    payload["rendered"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    title = str(payload.get("title") or payload.get("spec") or "spec")
    html = TEMPLATE.replace("__TITLE__", title.replace("&", "&amp;").replace("<", "&lt;"))
    html = html.replace("__DATA__", dump_payload(payload))

    out = Path(args.out) if args.out else spec.path.parent / "graph.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    if not args.quiet:
        print(f"✓ {out}")
        if report.errors:
            print(f"  ! {len(report.errors)} lint error(s) — the graph shows them, but fix the spec first")
        if diff:
            print(f"  diff: +{len(diff['added'])} ~{len(diff['changed'])} -{len(diff['removed'])} behaviours")
    return 0 if report.ok else 1


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{
    --fg: var(--foreground, #1f2328);
    --muted: var(--muted-foreground, #656d76);
    --acc: var(--accent, #4f46e5);
    --bd: var(--border, #d0d7de);
    --card: var(--card, transparent);
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0;background:transparent;color:var(--fg);
    font-family:inherit,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
  a{color:var(--acc);text-decoration:none}
  .wrap{display:flex;flex-direction:column;gap:14px;padding:2px 0 6px}
  header{display:flex;flex-direction:column;gap:8px}
  .titleline{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  h1{font-size:19px;line-height:1.2;margin:0;font-weight:650;letter-spacing:-.01em}
  .cap{color:var(--muted);font-family:var(--mono);font-size:12px}
  .pill{font-size:11px;line-height:1;padding:5px 8px;border-radius:999px;border:1px solid var(--bd);
    color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-weight:600}
  .obj{margin:0;color:var(--muted);font-size:13px;line-height:1.55;max-width:82ch}
  .stats{display:flex;gap:6px;flex-wrap:wrap}
  .stat{font-size:12px;color:var(--muted);border:1px solid var(--bd);border-radius:8px;padding:4px 8px;background:var(--card)}
  .stat b{color:var(--fg);font-weight:600}
  .stat[data-jump]{cursor:pointer}
  .stat[data-jump]:hover{border-color:var(--muted)}
  .stat.bad b{color:#cf222e}
  .toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding-bottom:10px;border-bottom:1px solid var(--bd)}
  .tabs{display:flex;gap:2px;background:transparent;border:1px solid var(--bd);border-radius:9px;padding:2px}
  .tab{font:inherit;font-size:12.5px;border:0;background:transparent;color:var(--muted);padding:5px 11px;border-radius:7px;cursor:pointer}
  .tab[aria-selected=true]{background:var(--acc);color:#fff;font-weight:600}
  .tab:disabled{opacity:.35;cursor:not-allowed}
  .grow{flex:1}
  input[type=search]{font:inherit;font-size:12.5px;color:var(--fg);background:transparent;border:1px solid var(--bd);
    border-radius:8px;padding:6px 9px;min-width:150px;max-width:220px}
  input[type=search]::placeholder{color:var(--muted)}
  .filters{display:flex;gap:5px;flex-wrap:wrap}
  .flabel{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
  .fchip{font:inherit;font-size:11px;border:1px solid var(--bd);background:transparent;color:var(--muted);
    border-radius:999px;padding:4px 8px;cursor:pointer;display:inline-flex;align-items:center;gap:5px}
  .fchip[data-on=true]{color:var(--fg);border-color:currentColor}
  .fchip .dot{width:7px;height:7px;border-radius:50%;background:currentColor;opacity:.85}
  .btn{font:inherit;font-size:12px;border:1px solid var(--bd);background:transparent;color:var(--fg);
    border-radius:8px;padding:5px 10px;cursor:pointer}
  .btn:hover{border-color:var(--muted)}
  main{position:relative;display:flex;gap:14px;min-height:0;align-items:flex-start}
  #stage{position:relative;flex:1;height:620px;border:1px solid var(--bd);border-radius:12px;overflow:hidden;background:transparent}
  #stage svg{width:100%;height:100%;display:block;cursor:grab;touch-action:none}
  #stage svg.dragging{cursor:grabbing}
  #stage.no-graph{display:none}
  .legend{position:absolute;left:10px;bottom:8px;display:flex;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--muted);
    background:var(--card);padding:2px 4px;border-radius:6px;pointer-events:none}
  .legend i{display:inline-block;width:11px;height:9px;border-radius:3px;margin-right:5px;vertical-align:middle}
  .legend span{white-space:nowrap}
  #body-beh,#body-trace,#body-table{flex:1;min-width:0}
  #inspector{flex:0 0 320px;width:320px;max-height:700px;overflow:auto;
    border:1px solid var(--bd);border-radius:12px;background:var(--card);
    padding:14px;display:none}
  #inspector.open{display:block}
  #inspector h2{font-size:14px;margin:0 0 2px;font-weight:650;line-height:1.35}
  #inspector .sub{color:var(--muted);font-family:var(--mono);font-size:11px;margin-bottom:10px;word-break:break-all}
  #inspector .close{position:absolute;top:8px;right:10px;border:0;background:transparent;color:var(--muted);
    font-size:18px;line-height:1;cursor:pointer;padding:2px}
  .sec{margin-top:14px}
  .sec h3{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 6px;font-weight:650}
  .rule{font-size:13px;line-height:1.5;border-left:2px solid var(--acc);padding-left:10px;margin:0}
  .sc{border:1px solid var(--bd);border-radius:9px;padding:8px 10px;margin-bottom:7px;font-size:12.5px;line-height:1.5}
  .sc .id{font-family:var(--mono);font-size:10.5px;color:var(--muted)}
  .kw{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-right:4px}
  ul.tight{margin:0;padding-left:16px;font-size:12.5px;line-height:1.55}
  .ref{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px;padding:4px 0;border-bottom:1px dashed var(--bd);word-break:break-all}
  .ref:last-child{border-bottom:0}
  .ref.bad{color:#cf222e}
  .ref button{border:0;background:transparent;color:var(--acc);cursor:pointer;font:inherit;font-size:10px;margin-left:auto;white-space:nowrap}
  .tdot{width:7px;height:7px;border-radius:50%;display:inline-block;flex:none}
  .acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:14px}
  .acts .btn{width:100%;text-align:center}
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;align-content:start;
    max-height:680px;overflow:auto;padding-right:4px}
  .card{border:1px solid var(--bd);border-radius:11px;padding:11px 12px;cursor:pointer;background:var(--card);position:relative;overflow:hidden}
  .card:hover{border-color:var(--muted)}
  .card .top{display:flex;align-items:center;gap:7px;margin-bottom:5px}
  .card .id{font-family:var(--mono);font-size:10.5px;color:var(--muted)}
  .card h3{font-size:13px;margin:0 0 6px;font-weight:600;line-height:1.35}
  .card p{margin:0;font-size:12px;color:var(--muted);line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .card .foot{display:flex;gap:8px;margin-top:8px;font-size:10.5px;color:var(--muted);font-family:var(--mono)}
  .card.dim{opacity:.28}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--bd);vertical-align:top}
  th{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:650}
  td.mono,span.mono{font-family:var(--mono);font-size:11px}
  tr.dim{opacity:.3}
  .empty{color:var(--muted);font-size:13px;padding:40px 0;text-align:center;border:1px dashed var(--bd);border-radius:12px}
  .banner{border:1px solid #cf222e;border-radius:9px;padding:8px 10px;font-size:12px;color:#cf222e}
  .banner.warn{border-color:#9a6700;color:#9a6700}
  footer{color:var(--muted);font-size:11px;display:flex;gap:10px;flex-wrap:wrap;font-family:var(--mono)}
  .tip{color:var(--muted);font-size:11.5px}
  @media (max-width:880px){
    #stage{height:460px}
    #inspector{position:absolute;right:8px;left:auto;top:8px;bottom:auto;width:320px;
      max-width:calc(100% - 16px);max-height:calc(100% - 16px);flex:none;
      z-index:5;box-shadow:0 8px 28px rgba(0,0,0,.2)}
    .cards{grid-template-columns:1fr}
  }
  @media (max-width:560px){
    #inspector{left:8px;right:8px;width:auto}
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="titleline">
      <h1 id="h-title"></h1>
      <span class="pill" id="h-status"></span>
      <span class="cap" id="h-cap"></span>
    </div>
    <p class="obj" id="h-obj"></p>
    <div class="stats" id="h-stats"></div>
  </header>
  <div class="toolbar">
    <nav class="tabs" role="tablist">
      <button class="tab" id="tab-graph" role="tab" data-tab="graph">Graph</button>
      <button class="tab" id="tab-beh" role="tab" data-tab="behaviours">Behaviours</button>
      <button class="tab" id="tab-trace" role="tab" data-tab="trace">Trace</button>
      <button class="tab" id="tab-table" role="tab" data-tab="table">Table</button>
    </nav>
    <button class="btn" id="fit" title="fit graph">Fit</button>
    <div class="grow"></div>
    <input type="search" id="q" placeholder="filter id, title, file…" aria-label="filter">
    <span class="flabel">status</span>
    <div class="filters" id="filters"></div>
  </div>
  <main>
    <div id="stage"><svg id="svg" role="img" aria-label="behaviour graph"><g id="view"></g></svg>
      <div class="legend" id="legend"></div>
    </div>
    <aside id="inspector" aria-live="polite"></aside>
    <div id="body-beh" style="display:none"></div>
    <div id="body-trace" style="display:none"></div>
    <div id="body-table" style="display:none"></div>
  </main>
  <footer id="foot"></footer>
</div>

<script id="payload" type="application/json">__DATA__</script>
<script>
(() => {
  "use strict";
  const DATA = JSON.parse(document.getElementById("payload").textContent);
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  // ---- theme -------------------------------------------------------------
  const css = getComputedStyle(document.documentElement);
  const v = (name, fallback) => (css.getPropertyValue(name) || "").trim() || fallback;
  const FG = v("--foreground", "#1f2328"), MUTED = v("--muted-foreground", "#656d76");
  const ACC = v("--accent", "#4f46e5"), BD = v("--border", "#d0d7de");
  const CARD = v("--card", "transparent");
  function luminance(color) {
    let r, g, b;
    const hex = color.replace("#", "").trim();
    if (/^[0-9a-f]{3}$/i.test(hex)) [r, g, b] = hex.split("").map(c => parseInt(c + c, 16));
    else if (/^[0-9a-f]{6}$/i.test(hex)) [r, g, b] = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
    else {
      const m = color.match(/\d+(\.\d+)?/g);
      if (!m) return 1;
      [r, g, b] = m.slice(0, 3).map(Number);
    }
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  }
  const DARK = luminance(FG) > 0.5;
  const PAL = DARK
    ? { implemented: "#3fb950", unverified: "#2dd4bf", fail: "#f85149", divergent: "#f85149", missing: "#d29922",
        approved: "#4493f8", proposed: "#d29922", draft: "#8b949e", none: "#8b949e", added: "#3fb950", changed: "#d29922" }
    : { implemented: "#1a7f37", unverified: "#0f766e", fail: "#cf222e", divergent: "#cf222e", missing: "#9a6700",
        approved: "#0969da", proposed: "#9a6700", draft: "#6e7781", none: "#6e7781", added: "#1a7f37", changed: "#9a6700" };
  const ORDER = ["fail", "divergent", "missing", "proposed", "draft", "approved", "unverified", "implemented"];
  const RANK = { fail: 9, divergent: 9, missing: 8, proposed: 7, draft: 6, approved: 5, unverified: 4, implemented: 3, none: 1 };
  const RANK_LABEL = { fail: "failing", divergent: "divergent", missing: "untested", proposed: "proposed",
                       draft: "draft", approved: "approved", unverified: "implemented, unverified", implemented: "implemented" };

  const KIND = DATA.kind || "behaviour";
  const IS_REF = KIND === "refactor";
  Object.assign(PAL, { done: PAL.implemented, doing: PAL.approved, todo: PAL.draft, blocked: PAL.fail });
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const behById = Object.fromEntries(DATA.behaviours.map(b => [b.id, b]));
  const trById = {};
  (DATA.machine?.transitions || []).forEach(t => trById[t.id] = t);
  const diffs = new Set([...(DATA.diff?.added || []), ...(DATA.diff?.changed || [])]);

  function effective(b) {
    if (b.result === "fail") return "fail";
    if (b.status === "implemented" && b.result === "missing") return "missing";
    // "implemented" is a claim until a test run backs it up.
    if (b.status === "implemented" && !DATA.generated) return "unverified";
    if (b.status === "divergent") return "divergent";
    return b.status || "draft";
  }
  const effOf = id => behById[id] ? effective(behById[id]) : "none";
  const worst = ids => ids.map(effOf).sort((a, b) => RANK[b] - RANK[a])[0] || "none";

  // ---- state -------------------------------------------------------------
  const state = { tab: "graph", sel: null, q: "", filters: new Set(), fitted: false };

  // ---- header ------------------------------------------------------------
  $("#h-title").textContent = DATA.title || DATA.spec || "spec";
  const st = $("#h-status");
  st.textContent = DATA.status; st.style.color = PAL[DATA.status] || MUTED; st.style.borderColor = "currentColor";
  $("#h-cap").textContent = `${DATA.spec} · v${DATA.version}` + (IS_REF ? " · refactor" : (DATA.tier ? ` · ${DATA.tier}` : ""));
  $("#h-obj").textContent = DATA.objective || "";
  const c = DATA.counts;
  let stats;
  if (IS_REF) {
    stats = [
      ["steps", c.steps, false, ""],
      ["done", c.done, false, ""],
      ["doing", c.doing, c.doing > 0, ""],
      [c.failing === 1 ? "check failing" : "checks failing", c.failing, c.failing > 0, ""],
      [c.passing === 1 ? "check passing" : "checks passing", c.passing, false, ""],
      ["invariants", c.invariants, false, ""],
    ];
  } else {
    const unverified = DATA.behaviours.filter(b => b.status === "implemented").length;
    stats = [["behaviours", c.behaviours, false, ""]];
    if (DATA.generated) stats.push(["passing", c.passing, false, ""], ["failing", c.failing, c.failing > 0, "fail"]);
    else stats.push(["implemented, unverified", unverified, unverified > 0, ""]);
    stats.push(
      ["untested", c.untested, c.untested > 0, "missing"],
      ["dead refs", c.deadRefs, c.deadRefs > 0, ""],
      [c.uncoveredTransitions === 1 ? "uncovered transition" : "uncovered transitions", c.uncoveredTransitions, c.uncoveredTransitions > 0, ""],
    );
  }
  $("#h-stats").innerHTML = stats.map(([label, n, bad, jump]) =>
    `<span class="stat${bad ? " bad" : ""}"${jump ? ` data-jump="${jump}" title="show these behaviours"` : ""}><b>${n}</b> ${label}</span>`).join("");

  // ---- tabs --------------------------------------------------------------
  const hasGraph = IS_REF || !!(DATA.machine || DATA.flow);
  const views = { graph: $("#stage"), behaviours: $("#body-beh"), trace: $("#body-trace"), table: $("#body-table") };
  if (!hasGraph) $("#tab-graph").disabled = true;
  if (IS_REF) {
    $("#tab-graph").textContent = "Plan";
    $("#tab-beh").textContent = "Steps";
    $("#tab-trace").textContent = "Checks";
    $$(".flabel").forEach(el => { el.style.display = "none"; });
    $("#filters").style.display = "none";
  }
  function setTab(tab) {
    if (tab === "graph" && !hasGraph) tab = "behaviours";
    state.tab = tab;
    $$(".tab").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    Object.entries(views).forEach(([k, el]) => el.style.display = k === tab ? "" : "none");
    if (tab === "graph") { draw(); }
    if (tab === "behaviours") { IS_REF ? renderStepCards() : renderCards(); }
    if (tab === "trace") { IS_REF ? renderChecks() : renderTrace(); }
    if (tab === "table") { IS_REF ? renderStepTable() : renderTable(); }
    if (tab !== "graph") $("#inspector").classList.remove("open");
  }
  $$(".tab").forEach(b => b.addEventListener("click", () => setTab(b.dataset.tab)));

  // ---- filters -----------------------------------------------------------
  const filterValues = ["implemented", "approved", "missing", "fail"];
  $("#filters").innerHTML = filterValues.map(s =>
    `<button class="fchip" data-v="${s}" data-on="false" style="color:${PAL[s]}"><span class="dot"></span>${RANK_LABEL[s]}</button>`).join("");
  $$(".fchip").forEach(chip => chip.addEventListener("click", () => {
    const s = chip.dataset.v;
    if (state.filters.has(s)) state.filters.delete(s); else state.filters.add(s);
    chip.dataset.on = String(state.filters.has(s));
    applyFilters();
  }));
  $("#q").addEventListener("input", e => { state.q = e.target.value.toLowerCase().trim(); applyFilters(); });
  $("#h-stats").addEventListener("click", ev => {
    const el = ev.target.closest("[data-jump]");
    if (!el) return;
    state.filters = new Set([el.dataset.jump]);
    $$(".fchip").forEach(chip => { chip.dataset.on = String(state.filters.has(chip.dataset.v)); });
    setTab("behaviours");
  });

  function matches(b) {
    if (state.filters.size) {
      const eff = effective(b);
      const untested = !(b.tests || []).length || eff === "missing";
      const ok = state.filters.has(eff) || (state.filters.has("missing") && untested);
      if (!ok) return false;
    }
    if (!state.q) return true;
    const hay = [b.id, b.title, b.rule, b.transition, ...(b.tests || []),
                 ...b.refs.map(r => r.path + " " + (r.symbol || ""))].join(" ").toLowerCase();
    return hay.includes(state.q);
  }
  function stepMatches(s) {
    if (!state.q) return true;
    const hay = [s.id, s.title, s.status, s.check, ...(s.touches || []).map(t => t.path)]
      .join(" ").toLowerCase();
    return hay.includes(state.q);
  }
  function applyFilters() {
    if (state.tab === "graph") draw();
    if (state.tab === "behaviours") { IS_REF ? renderStepCards() : renderCards(); }
    if (state.tab === "table") { IS_REF ? renderStepTable() : renderTable(); }
    if (state.tab === "trace") { IS_REF ? renderChecks() : renderTrace(); }
  }

  // ---- inspector ---------------------------------------------------------
  const insp = $("#inspector");
  function closeInspector() {
    state.sel = null;
    insp.classList.remove("open");
    if (state.tab === "graph") { state.fitted = false; draw(); }
    renderCards();
  }
  function focusNode(id) {
    const m = window.__model, vt = window.__vt;
    if (!m || !vt || !id) return;
    const n = m.byId[id];
    if (!n) return;
    const W = usableW(), H = $("#stage").clientHeight;
    const sx = vt.x + n.x * vt.k, sy = vt.y + n.y * vt.k;
    if (sx > 80 && sx < W - 80 && sy > 80 && sy < H - 80) return;
    vt.x = W / 2 - n.x * vt.k;
    vt.y = H / 2 - n.y * vt.k;
    window.__applyView();
  }
  function openInspector(html, focusId) {
    insp.innerHTML = `<button class="close" aria-label="close">×</button>` + html;
    insp.classList.add("open");
    if (state.tab === "graph") { state.fitted = false; draw(); focusNode(focusId); }
    $(".close", insp).addEventListener("click", closeInspector);
    $$("[data-hermes-send]", insp).forEach(el => { /* native dispatch handled by the host */ });
  }
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeInspector(); });

  const send = (prompt) => `data-hermes-send="${prompt.replace(/"/g, "&quot;")}"`;
  function refRows(refs) {
    if (!refs.length) return `<div class="tip">no files cited</div>`;
    return refs.map(r => {
      const bad = r.ok === false;
      const label = `${r.path}${r.symbol ? " · " + r.symbol : ""}`;
      const prompt = `Open ${r.path}${r.symbol ? " and show me " + r.symbol : ""}`;
      return `<div class="ref ${bad ? "bad" : ""}">${bad ? "✗" : "◦"}
        <span>${label}</span><button ${send(prompt)}>open</button></div>`;
    }).join("");
  }
  function showBehaviour(id) {
    const b = behById[id]; if (!b) return;
    state.sel = id;
    const eff = effective(b);
    const tr = trById[b.transition];
    const sc = b.scenarios.map(s => `
      <div class="sc"><div class="id">${s.id}</div>
        ${s.given.length ? `<div><span class="kw">given</span>${s.given.join("; ")}</div>` : ""}
        <div><span class="kw">when</span>${s.when}</div>
        <div><span class="kw">then</span>${s.then.join("; ")}</div></div>`).join("");
    const tests = b.tests.length
      ? b.tests.map(t => {
          const r = (b.results || []).find(x => x.name === t) || (b.results || [])[0];
          const ok = r ? r.ok : null;
          const dot = ok === true ? PAL.implemented : ok === false ? PAL.fail : MUTED;
          return `<div class="ref"><span class="tdot" style="background:${dot}"></span><span>${t}</span></div>`;
        }).join("")
      : `<div class="tip">no test linked yet</div>`;
    openInspector(`
      <h2>${b.title}</h2>
      <div class="sub">${b.id} · <span style="color:${PAL[eff]}">${RANK_LABEL[eff]}</span>${tr ? " · " + tr.id + " " + tr.event : ""}</div>
      <p class="rule">${b.rule}</p>
      <div class="sec"><h3>Scenarios (${b.scenarios.length})</h3>${sc}</div>
      <div class="sec"><h3>Tests</h3>${tests}</div>
      <div class="sec"><h3>Repo references</h3>${refRows(b.refs)}</div>
      <div class="acts"><button class="btn" ${send(`Change ${b.id} (${b.title}) in ${DATA.source}. Ask me what I want different, then show the spec diff before touching code.`)}>Ask to change this behaviour</button></div>
    `, tr ? tr.from[0] : "");
  }
  function metaEntry(id) {
    const conv = (DATA.conventions || []).find(c => c.id === id);
    if (conv) return { id, kind: "invariant", text: conv.rule, refs: conv.refs || [], tests: [], scope: "" };
    const ctx = (DATA.context || []).find(c => c.id === id);
    if (ctx) return { id, kind: "context", text: ctx.note, refs: ctx.refs || [], tests: [], scope: "" };
    const pinv = (DATA.invariants || []).find(c => c.id === id);
    if (pinv) return { id, kind: "invariant", text: pinv.rule, refs: pinv.refs || [], tests: pinv.tests || [], scope: "refactor plan" };
    return null;
  }
  // Invariant and context cards clamp their text to three lines; the inspector is
  // the only place the whole rule is readable, so it must open for them too.
  function showMeta(id) {
    const m = metaEntry(id); if (!m) return;
    state.sel = null;
    const tests = m.tests.length
      ? m.tests.map(t => `<div class="ref"><span>${esc(t)}</span></div>`).join("")
      : `<div class="tip">no test linked</div>`;
    openInspector(`
      <h2>${m.kind === "context" ? "Context" : "Invariant"}</h2>
      <div class="sub">${m.id}${m.scope ? " · " + m.scope : ""}</div>
      <p class="rule">${esc(m.text)}</p>
      <div class="sec"><h3>Repo references</h3>${refRows(m.refs)}</div>
      ${m.tests.length ? `<div class="sec"><h3>Tests that would catch a regression</h3>${tests}</div>` : ""}
      <div class="acts"><button class="btn" ${send(`Change ${m.id} (${m.kind}) in ${DATA.source}. Ask me what I want different, then show the spec diff before touching code.`)}>Ask to change this ${m.kind}</button></div>
    `);
  }
  function showState(node, incoming, outgoing) {
    const behs = (node.behaviours && node.behaviours.length)
      ? node.behaviours
      : [...new Set([...outgoing, ...incoming].flatMap(t => t.behaviours))];
    openInspector(`
      <h2>${node.name}</h2>
      <div class="sub">state · ${node.id}</div>
      ${node.description ? `<p class="rule">${node.description}</p>` : ""}
      <div class="sec"><h3>Outgoing (${outgoing.length})</h3>
        ${outgoing.map(t => `<div class="ref">${t.event} → ${t.to}<span style="color:${PAL[worst(t.behaviours)]}">${t.id}</span></div>`).join("") || `<div class="tip">none</div>`}</div>
      <div class="sec"><h3>Incoming (${incoming.length})</h3>
        ${incoming.map(t => `<div class="ref">${t.event} from ${t.from.join(", ")}<span style="color:${PAL[worst(t.behaviours)]}">${t.id}</span></div>`).join("") || `<div class="tip">none</div>`}</div>
      <div class="sec"><h3>Behaviours (${behs.length})</h3>
        ${behs.map(id => `<div class="ref"><span class="tdot" style="background:${PAL[effOf(id)]}"></span><span>${id} ${behById[id]?.title || ""}</span></div>`).join("") || `<div class="tip">none attached</div>`}</div>
    `, node.id);
    $$(".ref", insp).forEach(row => row.addEventListener("click", () => {
      const m = row.textContent.match(/BEH-\d{3}/); if (m) showBehaviour(m[0]);
    }));
  }
  function showTransition(t) {
    const behs = t.behaviours;
    openInspector(`
      <h2>${t.event}</h2>
      <div class="sub">${t.id} · ${t.from.join(" | ")} → ${t.to}</div>
      ${t.guard ? `<div class="sec"><h3>Guard</h3><p class="rule">${t.guard}</p></div>` : ""}
      ${t.effect ? `<div class="sec"><h3>Effect</h3><p class="rule">${t.effect}</p></div>` : ""}
      <div class="sec"><h3>Behaviours (${behs.length})</h3>
        ${behs.map(id => `<div class="ref" data-beh="${id}"><span class="tdot" style="background:${PAL[effOf(id)]}"></span><span>${id} ${behById[id]?.title || ""}</span></div>`).join("")
          || `<div class="tip">nothing specified on this transition</div>`}</div>
      <div class="sec"><h3>Repo references</h3>${refRows(t.refs || [])}</div>
    `, t.from[0]);
    $$("[data-beh]", insp).forEach(row => row.addEventListener("click", () => showBehaviour(row.dataset.beh)));
  }

  // ---- svg helpers -------------------------------------------------------
  function el(name, attrs = {}, parent) {
    const node = document.createElementNS(NS, name);
    for (const [k, val] of Object.entries(attrs)) if (val !== undefined && val !== null) node.setAttribute(k, val);
    if (parent) parent.appendChild(node);
    return node;
  }
  function wrap(text, max, maxLines = 3) {
    const words = String(text).split(/\s+/), lines = [];
    let cur = "";
    for (const w of words) {
      if ((cur + " " + w).trim().length > max && cur) { lines.push(cur); cur = w; }
      else cur = (cur + " " + w).trim();
    }
    if (cur) lines.push(cur);
    if (lines.length > maxLines) {
      const kept = lines.slice(0, maxLines);
      kept[maxLines - 1] = kept[maxLines - 1].replace(/[ ,;:]?\S*$/, "…");
      return kept;
    }
    return lines;
  }
  const svg = $("#svg"), view = $("#view");

  // graph model
  function model() {
    if (IS_REF) {
      const nodes = (DATA.steps || []).map(s => ({ id: s.id, name: s.title, description: s.note || "", status: s.status, step: s }));
      const edges = [];
      (DATA.steps || []).forEach(s => (s.depends_on || []).forEach(d => edges.push({
        id: s.id + "@" + d, from: d, to: s.id, event: "", guard: "", effect: "", behaviours: [], refs: [],
      })));
      const roots = nodes.filter(n => !(n.step.depends_on || []).length).map(n => n.id);
      return { kind: "plan", nodes, edges, initial: roots[0] || "", roots: roots.length ? roots : nodes.slice(0, 1).map(n => n.id) };
    }
    if (DATA.machine) {
      const nodes = DATA.machine.states.map(s => ({ ...s }));
      const edges = [];
      (DATA.machine.transitions || []).forEach(t => {
        (t.from.length ? t.from : [""]).forEach(f => edges.push({
          id: t.id + "@" + f, tid: t.id, from: f, to: t.to, event: t.event,
          guard: t.guard, effect: t.effect, behaviours: t.behaviours, refs: t.refs || [], transition: t,
        }));
      });
      return { kind: "machine", nodes, edges, initial: DATA.machine.initial };
    }
    if (DATA.flow) {
      const nodes = DATA.flow.steps.map(s => ({ id: s.id, name: s.name, description: s.description, behaviours: s.behaviours || [] }));
      const edges = [];
      DATA.flow.steps.forEach(s => (s.next || []).forEach(n => {
        const target = nodes.find(x => x.id === n) || { behaviours: [] };
        edges.push({
          id: s.id + "@" + n, tid: s.id, from: s.id, to: n, event: "", guard: "", effect: "",
          behaviours: [...new Set([...(s.behaviours || []), ...(target.behaviours || [])])], refs: [],
        });
      }));
      return { kind: "flow", nodes, edges, initial: DATA.flow.steps[0]?.id };
    }
    return null;
  }

  function layout(m) {
    const depth = new Map(m.nodes.map(n => [n.id, Infinity]));
    const roots = (m.roots && m.roots.length) ? m.roots : (m.initial ? [m.initial] : []);
    roots.forEach(r => { if (depth.has(r)) depth.set(r, 0); });
    for (let pass = 0; pass < m.nodes.length + 2; pass++) {
      let changed = false;
      for (const e of m.edges) {
        const d = depth.get(e.from);
        if (d !== undefined && d !== Infinity && depth.get(e.to) > d + 1) { depth.set(e.to, d + 1); changed = true; }
      }
      if (!changed) break;
    }
    const finite = [...depth.values()].filter(Number.isFinite);
    const maxDepth = finite.length ? Math.max(...finite) : 0;
    m.nodes.forEach(n => { if (!Number.isFinite(depth.get(n.id))) depth.set(n.id, maxDepth + 1); });

    const layers = new Map();
    m.nodes.forEach(n => {
      const d = depth.get(n.id);
      if (!layers.has(d)) layers.set(d, []);
      layers.get(d).push(n);
    });
    // one barycenter pass to reduce crossings
    const preds = new Map(m.nodes.map(n => [n.id, []]));
    m.edges.forEach(e => { if (e.from !== e.to) preds.get(e.to)?.push(e.from); });
    const pos = new Map();
    [...layers.keys()].sort((a, b) => a - b).forEach(d => {
      const layer = layers.get(d);
      layer.sort((a, b) => {
        const score = n => {
          const ps = preds.get(n.id) || [];
          const known = ps.map(p => pos.get(p)).filter(x => x !== undefined);
          return known.length ? known.reduce((s, x) => s + x, 0) / known.length : 9999;
        };
        return score(a) - score(b);
      });
      layer.forEach((n, i) => pos.set(n.id, i));
    });

    const R = m.kind === "plan" ? 52 : 44;
    const COL = m.kind === "plan" ? 215 : 190, ROW = m.kind === "plan" ? 160 : 140, PAD = 76;
    const tallest = Math.max(...[...layers.values()].map(l => l.length));
    layers.forEach((layer, d) => {
      const offset = (tallest - layer.length) * ROW / 2;
      layer.forEach((n, i) => {
        n.depth = d;
        n.x = PAD + d * COL;
        n.y = PAD + offset + i * ROW;
        n.r = R;
      });
    });
    m.byId = Object.fromEntries(m.nodes.map(n => [n.id, n]));
    return m;
  }

  function edgeGeometry(e, m) {
    const a = m.byId[e.from], b = m.byId[e.to];
    if (!a || !b) return null;
    if (e.from === e.to) {
      const r = a.r;
      // several self-loops on one state must not draw on top of each other
      const loops = m.edges.filter(o => o.from === e.from && o.to === e.from);
      const k = loops.length > 1 ? loops.indexOf(e) - (loops.length - 1) / 2 : 0;
      const lift = 1 + k * 0.4;
      return {
        d: `M ${a.x - r * 0.55} ${a.y - r * 0.83} C ${a.x - r * 1.5 * lift} ${a.y - r * 2.2 * lift}, ${a.x + r * 1.5 * lift} ${a.y - r * 2.2 * lift}, ${a.x + r * 0.55} ${a.y - r * 0.83}`,
        lx: a.x, ly: a.y - r * 1.98 * lift,
      };
    }
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.max(Math.hypot(dx, dy), 1);
    const ux = dx / dist, uy = dy / dist;
    const startX = a.x + ux * a.r, startY = a.y + uy * a.r;
    const endX = b.x - ux * (b.r + 10), endY = b.y - uy * (b.r + 10);
    const reverse = m.edges.some(o => o !== e && o.from === e.to && o.to === e.from);
    const bend = reverse ? 34 : 16;
    const mx = (startX + endX) / 2 - uy * bend, my = (startY + endY) / 2 + ux * bend;
    const c1x = startX + (mx - startX) * 0.55, c1y = startY + (my - startY) * 0.55;
    const c2x = endX + (mx - endX) * 0.55, c2y = endY + (my - endY) * 0.55;
    return {
      d: `M ${startX} ${startY} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${endX} ${endY}`,
      lx: (startX + 3 * c1x + 3 * c2x + endX) / 8,
      ly: (startY + 3 * c1y + 3 * c2y + endY) / 8,
    };
  }

  function nodeHealth(id, m) {
    const node = m.byId ? m.byId[id] : null;
    if (node && node.status) return node.status;
    if (node && node.behaviours && node.behaviours.length) return worst(node.behaviours);
    const attached = m.edges.filter(e => e.from === id || e.to === id).flatMap(e => e.behaviours);
    return worst([...new Set(attached)]);
  }

  function draw() {
    if (state.tab !== "graph" || !hasGraph) return;
    const m = layout(model());
    window.__model = m;
    const stage = $("#stage");
    const ys = m.nodes.map(n => n.y);
    const targetH = Math.round(Math.min(700, Math.max(340, (Math.max(...ys) - Math.min(...ys)) + 120)));
    if (Math.abs(stage.clientHeight - targetH) > 6) stage.style.height = targetH + "px";
    const W = stage.clientWidth, H = stage.clientHeight;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    view.innerHTML = "";

    const defsEl = el("defs", {}, view);
    const marker = el("marker", { id: "arrow", viewBox: "0 0 10 10", refX: "9", refY: "5",
      markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse" }, defsEl);
    el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "context-stroke" }, marker);

    const gEdges = el("g", {}, view);
    const gNodes = el("g", {}, view);
    const q = state.q;

    // edges
    for (const e of m.edges) {
      const geo = edgeGeometry(e, m);
      if (!geo) continue;
      const eff = worst(e.behaviours);
      const uncovered = !IS_REF && e.behaviours.length === 0;
      const color = IS_REF ? MUTED : (PAL[eff] || MUTED);
      const dim = IS_REF ? false : (q && !e.behaviours.some(id => matches(behById[id])) && !e.event.toLowerCase().includes(q));
      const path = el("path", {
        d: geo.d, fill: "none", stroke: color, "stroke-width": uncovered ? 1.4 : 1.8,
        "stroke-dasharray": uncovered ? "5 5" : null, "marker-end": "url(#arrow)",
        opacity: dim ? 0.16 : 0.95,
      }, gEdges);
      path.style.cursor = "pointer";
      path.addEventListener("click", ev => { ev.stopPropagation(); IS_REF ? showStep(e.to) : showTransition(e.transition); });

      if (e.event) {
        const label = el("g", { opacity: dim ? 0.2 : 1, transform: `translate(${geo.lx},${geo.ly})` }, gEdges);
        const text = el("text", {
          "text-anchor": "middle", "dominant-baseline": "middle", "font-size": "12.5",
          "font-family": "var(--mono)", fill: FG, "paint-order": "stroke",
          stroke: CARD === "transparent" ? "transparent" : CARD, "stroke-width": "4",
        }, label);
        text.textContent = e.event;
        const bb = text.getBBox ? text.getBBox() : { width: e.event.length * 7, height: 12 };
        if (e.behaviours.length) {
          const badge = el("g", { transform: `translate(${bb.width / 2 + 9},0)` }, label);
          el("circle", { r: "8.5", fill: color, "fill-opacity": "0.16", stroke: color, "stroke-width": "1" }, badge);
          const n = el("text", { "text-anchor": "middle", "dominant-baseline": "central", "font-size": "10.5",
            fill: color, "font-family": "var(--mono)" }, badge);
          n.textContent = e.behaviours.length;
        }
      }
    }

    // initial marker
    if (!IS_REF && m.initial && m.byId[m.initial]) {
      const n = m.byId[m.initial];
      const ig = el("g", { opacity: 0.8 }, gEdges);
      el("path", { d: `M ${n.x - n.r - 34} ${n.y} L ${n.x - n.r - 6} ${n.y}`,
        stroke: MUTED, "stroke-width": 1.6, "marker-end": "url(#arrow)", "stroke-dasharray": "3 3" }, ig);
      const t = el("text", { x: n.x - n.r - 38, y: n.y - 7, "text-anchor": "end", "font-size": "10",
        fill: MUTED, "font-family": "var(--mono)" }, ig);
      t.textContent = "start";
    }

    // nodes
    for (const n of m.nodes) {
      const health = nodeHealth(n.id, m);
      const color = PAL[health] || MUTED;
      const behs = (n.behaviours && n.behaviours.length)
        ? n.behaviours
        : [...new Set(m.edges.filter(e => e.from === n.id || e.to === n.id).flatMap(e => e.behaviours))];
      const checkRes = IS_REF ? (n.step?.checkResult || null) : null;
      const dim = IS_REF
        ? (q && !stepMatches(n.step))
        : (q && !n.id.toLowerCase().includes(q) && !n.name.toLowerCase().includes(q) &&
           !behs.some(id => matches(behById[id])));
      const g = el("g", {
        transform: `translate(${n.x},${n.y})`, opacity: dim ? 0.2 : 1,
        style: "cursor:pointer", tabindex: "0", role: "button",
      }, gNodes);
      el("circle", { r: n.r, fill: color, "fill-opacity": "0.10", stroke: color, "stroke-width": health === "none" ? 1.3 : 2 }, g);
      if (n.id === state.sel) el("circle", { r: n.r + 5, fill: "none", stroke: ACC, "stroke-width": 1.5, "stroke-dasharray": "3 3" }, g);
      // a state is touched when one of the behaviours attached to it changed
      const touched = diffs.has(n.id) || behs.some(id => diffs.has(id));
      if (touched) el("circle", { r: n.r + 9, fill: "none", stroke: PAL.changed, "stroke-width": 1.4, "stroke-dasharray": "2 3" }, g);

      const lines = wrap(n.name, IS_REF ? 15 : 12, IS_REF ? 4 : 3);
      const tip = el("title", {}, g);
      tip.textContent = n.name;
      const t = el("text", {
        "text-anchor": "middle", "dominant-baseline": "middle", "font-size": IS_REF ? "11" : "13", fill: FG,
        "font-weight": "600", "font-family": "inherit",
      }, g);
      const startY = -(lines.length - 1) * 7 + (behs.length ? -4 : 0);
      lines.forEach((line, i) => {
        const tspan = el("tspan", { x: 0, y: startY + i * 14 }, t);
        tspan.textContent = line;
      });
      if (behs.length) {
        const bt = el("text", { y: startY + lines.length * 14 + 2, "text-anchor": "middle", "font-size": "9.5",
          fill: MUTED, "font-family": "var(--mono)" }, g);
        bt.textContent = `${behs.length} beh`;
      } else if (IS_REF) {
        const bt = el("text", { y: startY + lines.length * 14 + 2, "text-anchor": "middle", "font-size": "9.5",
          fill: MUTED, "font-family": "var(--mono)" }, g);
        bt.textContent = `${n.id} · ${n.status}`;
        if (checkRes) {
          const badge = el("g", { transform: `translate(${n.r * 0.72},${-n.r * 0.72})` }, g);
          el("circle", { r: "9", fill: CARD === "transparent" ? FG : CARD, "fill-opacity": "0.92",
            stroke: checkRes.ok ? PAL.implemented : PAL.fail, "stroke-width": "1.4" }, badge);
          const glyph = el("text", { "text-anchor": "middle", "dominant-baseline": "central", "font-size": "10",
            fill: checkRes.ok ? PAL.implemented : PAL.fail, "font-family": "var(--mono)" }, badge);
          glyph.textContent = checkRes.ok ? "✓" : "✗";
        }
      }
      g.addEventListener("click", ev => {
        ev.stopPropagation();
        if (IS_REF) { showStep(n.id); draw(); return; }
        const outgoing = m.edges.filter(e => e.from === n.id).map(e => e.transition).filter(Boolean);
        const incoming = m.edges.filter(e => e.to === n.id).map(e => e.transition).filter(Boolean);
        showState(n, [...new Set(incoming)], [...new Set(outgoing)]);
        draw();
      });
      g.addEventListener("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") g.dispatchEvent(new MouseEvent("click")); });
    }

    // legend
    const legendItems = IS_REF
      ? [["done", "done"], ["doing", "doing"], ["todo", "todo"], ["blocked", "blocked"]]
      : DATA.generated
        ? [["implemented", "implemented & passing"], ["approved", "approved, not built"],
           ["missing", "untested"], ["fail", "failing"]]
        : [["unverified", "implemented, unverified"], ["approved", "approved, not built"],
           ["missing", "untested"], ["fail", "failing"]];
    $("#legend").innerHTML = legendItems.map(([k, label]) =>
      `<span><i style="background:${PAL[k]};opacity:.55"></i>${label}</span>`).join("") +
      (IS_REF
        ? `<span><i style="background:transparent;border:1px solid ${MUTED}"></i>arrow = prerequisite → next</span><span>badge = attached check</span>`
        : `<span><i style="background:transparent;border:1px dashed ${MUTED}"></i>dashed edge = no behaviour</span>`);

    // pan / zoom (rebind once)
    if (!draw.bound) {
      draw.bound = true;
      bindViewport(W, H);
    }
    if (!state.fitted) { fit(); state.fitted = true; }
  }

  function bindViewport(W, H) {
    let dragging = false, moved = false, sx = 0, sy = 0, ox = 0, oy = 0;
    const vt = { x: 0, y: 0, k: 1 };
    const apply = () => view.setAttribute("transform", `translate(${vt.x},${vt.y}) scale(${vt.k})`);
    window.__applyView = apply; window.__vt = vt;

    svg.addEventListener("pointerdown", e => {
      if (e.button !== 0) return;
      dragging = true; moved = false;
      sx = e.clientX; sy = e.clientY; ox = vt.x; oy = vt.y;
      svg.classList.add("dragging"); svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", e => {
      if (!dragging) return;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      vt.x = ox + dx; vt.y = oy + dy; apply(); state.userMoved = true;
    });
    const stop = e => {
      if (!dragging) return;
      dragging = false; svg.classList.remove("dragging");
      if (!moved) { /* background click */ state.sel = null; insp.classList.remove("open"); }
    };
    svg.addEventListener("pointerup", stop);
    svg.addEventListener("pointercancel", stop);
    svg.addEventListener("wheel", e => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const factor = Math.exp(-e.deltaY * 0.0015);
      const k = Math.min(3, Math.max(0.25, vt.k * factor));
      vt.x = mx - (mx - vt.x) * (k / vt.k);
      vt.y = my - (my - vt.y) * (k / vt.k);
      vt.k = k; apply(); state.userMoved = true;
    }, { passive: false });

    $("#fit").onclick = () => { state.fitted = false; fit(); };
    // Only react to width changes: our own dynamic height would otherwise
    // trigger a second fit right after opening the inspector.
    let lastW = $("#stage").clientWidth;
    new ResizeObserver(() => {
      const w = $("#stage").clientWidth;
      if (Math.abs(w - lastW) < 2) return;
      lastW = w;
      if (!state.userMoved && state.tab === "graph") { state.fitted = false; draw(); }
    }).observe($("#stage"));
  }

  function usableW() {
    const stage = $("#stage");
    const w = stage.clientWidth;
    if (!insp.classList.contains("open")) return w;
    if (getComputedStyle(insp).position !== "absolute") return w;
    return Math.max(300, w - insp.getBoundingClientRect().width - 24);
  }

  function fit() {
    const bbox = view.getBBox ? view.getBBox() : null;
    const W = usableW(), H = $("#stage").clientHeight;
    if (!bbox || !bbox.width || !window.__vt) return;
    const pad = 24;
    const raw = Math.min((W - pad * 2) / bbox.width, (H - pad * 2) / bbox.height, 1.4);
    const k = Math.min(1.4, Math.max(0.72, raw));
    window.__vt.k = k;
    const scaledW = bbox.width * k, scaledH = bbox.height * k;
    window.__vt.x = scaledW > W - pad * 2 ? pad - bbox.x * k : (W - scaledW) / 2 - bbox.x * k;
    window.__vt.y = scaledH > H - pad * 2 ? pad - bbox.y * k : (H - scaledH) / 2 - bbox.y * k;
    window.__applyView();
  }

  // ---- behaviours --------------------------------------------------------
  const OPEN_CUE = `<span style="margin-left:auto;color:var(--acc)">open ›</span>`;
  function renderCards() {
    const groups = {};
    DATA.behaviours.forEach(b => { const e = effective(b); (groups[e] = groups[e] || []).push(b); });
    const order = ORDER.filter(k => groups[k]);
    const html = order.map(k => {
      const cards = groups[k].map(b => {
        const dim = !matches(b);
        return `<div class="card ${dim ? "dim" : ""}" data-beh="${b.id}">
          <div class="top"><span class="tdot" style="background:${PAL[k]}"></span>
            <span class="id">${b.id}</span>${b.transition ? `<span class="id">${b.transition}</span>` : ""}
            ${DATA.diff?.added?.includes(b.id) ? `<span class="pill" style="color:${PAL.added};border-color:currentColor">new</span>`
              : DATA.diff?.changed?.includes(b.id) ? `<span class="pill" style="color:${PAL.changed};border-color:currentColor">changed</span>` : ""}</div>
          <h3>${b.title}</h3><p>${b.rule}</p>
          <div class="foot"><span>${b.scenarios.length} scenario${b.scenarios.length === 1 ? "" : "s"}</span>
            <span>${b.tests.length} test${b.tests.length === 1 ? "" : "s"}</span>
            ${b.refs.length ? `<span>${b.refs.length} ref${b.refs.length === 1 ? "" : "s"}</span>` : ""}</div></div>`;
      }).join("");
      return `<div style="grid-column:1/-1;display:flex;align-items:center;gap:8px;margin-top:6px">
        <span class="tdot" style="background:${PAL[k]}"></span>
        <span style="font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:${MUTED}">${RANK_LABEL[k]}</span>
        <span style="font-size:11px;color:${MUTED}">${groups[k].length}</span></div>${cards}`;
    }).join("");
    const metaCards = [
      ...(DATA.conventions || []).map(c => `<div class="card" data-meta="${c.id}" title="open the full text">
          <div class="top"><span class="id">${c.id}</span><span class="id">invariant</span></div>
          <p>${esc(c.rule)}</p>
          <div class="foot"><span>${c.refs.length} ref${c.refs.length === 1 ? "" : "s"}</span>${OPEN_CUE}</div></div>`),
      ...(DATA.context || []).map(c => `<div class="card" data-meta="${c.id}" title="open the full text">
          <div class="top"><span class="id">${c.id}</span><span class="id">context</span></div>
          <p>${esc(c.note)}</p>
          <div class="foot"><span>${c.refs.length} ref${c.refs.length === 1 ? "" : "s"}</span>${OPEN_CUE}</div></div>`),
    ].join("");
    const meta = metaCards
      ? `<div style="grid-column:1/-1;display:flex;align-items:center;gap:8px;margin:6px 0 2px">
           <span style="font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:${MUTED}">invariants &amp; context</span>
           <span style="font-size:11px;color:${MUTED}">${(DATA.conventions || []).length + (DATA.context || []).length}</span></div>${metaCards}`
      : "";
    const box = $("#body-beh");
    box.innerHTML = `<div class="cards">${meta}${html || '<div class="empty">no behaviours match</div>'}</div>`;
    $$("[data-beh]", box).forEach(card => card.addEventListener("click", () => showBehaviour(card.dataset.beh)));
    $$("[data-meta]", box).forEach(card => card.addEventListener("click", () => showMeta(card.dataset.meta)));
  }

  // ---- trace -------------------------------------------------------------
  function shortLabel(text, max, fromEnd = false) {
    const value = String(text).replace(/^tests\//, "");
    if (value.length <= max) return value;
    return fromEnd ? "…" + value.slice(-(max - 1)) : value.slice(0, max - 1) + "…";
  }

  function renderTrace() {
    const box = $("#body-trace");
    const tests = new Map();
    DATA.behaviours.forEach(b => {
      (b.tests || []).forEach(t => {
        if (!tests.has(t)) tests.set(t, { name: t, behs: [] });
        tests.get(t).behs.push(b.id);
      });
    });
    const files = new Map();
    DATA.behaviours.forEach(b => b.refs.forEach(r => {
      if (!files.has(r.path)) files.set(r.path, { path: r.path, behs: [], bad: false });
      files.get(r.path).behs.push(b.id);
      if (r.ok === false) files.get(r.path).bad = true;
    }));
    const W = box.clientWidth || 700, H = 560;
    // wider gutters than the old 0.36/0.70 columns: the connector lines need room
    const BX = 40, BW = W * 0.27;
    const TX = W * 0.45, TW = W * 0.27;
    const FX = W * 0.77, FW = W * 0.21;
    const bChars = Math.max(14, Math.floor((BW - 60) / 6.1));
    const tChars = Math.max(16, Math.floor((TW - 28) / 5.6));
    const fChars = Math.max(12, Math.floor((FW - 18) / 5.6));
    const svgT = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:${H}px;display:block">
      <defs><marker id="tarrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
        <path d="M0 0 L10 5 L0 10 z" fill="${MUTED}"/></marker></defs>`;
    const bH = 30, tH = 26, fH = 24;
    const bY = new Map(), tY = new Map(), fY = new Map();
    DATA.behaviours.forEach((b, i) => bY.set(b.id, 40 + i * 42));
    [...tests.keys()].forEach((t, i) => tY.set(t, 40 + i * 38));
    [...files.keys()].forEach((f, i) => fY.set(f, 40 + i * 38));
    let edges = "", nodes = "";
    DATA.behaviours.forEach(b => {
      const y = bY.get(b.id);
      nodes += `<g><rect x="${BX}" y="${y - bH / 2}" width="${BW}" height="${bH}" rx="7"
        fill="${PAL[effective(b)]}" fill-opacity=".10" stroke="${PAL[effective(b)]}" stroke-width="1.2"/>
        <text x="${BX + 8}" y="${y + 1}" dominant-baseline="middle" font-size="10.5"
          font-family="var(--mono)" fill="${FG}">${b.id}</text>
        <text x="${BX + 52}" y="${y + 1}" dominant-baseline="middle" font-size="10.5"
          fill="${MUTED}">${b.title.slice(0, bChars)}${b.title.length > bChars ? "…" : ""}</text></g>`;
      (b.tests || []).forEach(t => {
        const ty = tY.get(t); if (ty === undefined) return;
        edges += `<path d="M ${BX + BW} ${y} C ${BX + BW + (TX - BX - BW) * 0.4} ${y}, ${TX - 16} ${ty}, ${TX} ${ty}"
          fill="none" stroke="${PAL[effective(b)]}" stroke-opacity=".55" stroke-width="1"/>`;
      });
      b.refs.forEach(r => {
        const fy = fY.get(r.path); if (fy === undefined) return;
        edges += `<path d="M ${BX + BW} ${y} C ${BX + BW + (FX - BX - BW) * 0.35} ${y}, ${FX - 16} ${fy}, ${FX} ${fy}"
          fill="none" stroke="${BD}" stroke-width="1" stroke-dasharray="3 3"/>`;
      });
    });
    [...tests.entries()].forEach(([name, info]) => {
      const y = tY.get(name);
      const linked = info.behs.length > 0;
      const res = DATA.behaviours.flatMap(b => b.results || []).find(x => x.name === name);
      const dot = res ? (res.ok ? PAL.implemented : PAL.fail) : MUTED;
      nodes += `<g><rect x="${TX}" y="${y - tH / 2}" width="${TW}" height="${tH}" rx="6"
        fill="transparent" stroke="${linked ? BD : PAL.missing}" stroke-dasharray="${linked ? "" : "4 4"}" stroke-width="1.2"/>
        <circle cx="${TX + 10}" cy="${y}" r="3.2" fill="${dot}"/>
        <text x="${TX + 20}" y="${y + 1}" dominant-baseline="middle" font-size="9.5"
          font-family="var(--mono)" fill="${linked ? FG : MUTED}">${shortLabel(name, tChars)}</text></g>`;
    });
    [...files.entries()].forEach(([path, info]) => {
      const y = fY.get(path);
      nodes += `<g><rect x="${FX}" y="${y - fH / 2}" width="${FW}" height="${fH}" rx="5"
        fill="transparent" stroke="${info.bad ? PAL.fail : BD}" stroke-width="1"/>
        <text x="${FX + 8}" y="${y + 1}" dominant-baseline="middle" font-size="9.5"
          font-family="var(--mono)" fill="${info.bad ? PAL.fail : MUTED}">${shortLabel(path, fChars, true)}</text></g>`;
    });
    const orphans = DATA.behaviours.filter(b => !b.tests || !b.tests.length).length;
    box.innerHTML = `<div style="display:flex;gap:16px;align-items:baseline;margin-bottom:6px">
        <span class="tip">behaviours → tests → cited files</span>
        <span class="tip">${orphans} behaviour(s) without a test</span></div>
      <div style="overflow:auto;border:1px solid var(--bd);border-radius:12px">
        ${svgT}${edges}${nodes}</svg></div>`;
  }

  // ---- table -------------------------------------------------------------
  function renderTable() {
    const rows = DATA.behaviours.map(b => {
      const dim = !matches(b);
      return `<tr class="${dim ? "dim" : ""}" data-beh="${b.id}" style="cursor:pointer">
        <td class="mono">${b.id}</td><td>${b.title}</td>
        <td><span class="tdot" style="background:${PAL[effective(b)]}"></span> ${RANK_LABEL[effective(b)]}</td>
        <td class="mono">${b.transition || "—"}</td>
        <td class="mono">${b.tests.length || "—"}</td>
        <td class="mono">${b.refs.map(r => r.path).join("<br>") || "—"}</td></tr>`;
    }).join("");
    const box = $("#body-table");
    box.innerHTML = `<div style="overflow:auto;max-height:660px"><table>
      <thead><tr><th>id</th><th>behaviour</th><th>status</th><th>transition</th><th>tests</th><th>refs</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
    $$("[data-beh]", box).forEach(row => row.addEventListener("click", () => showBehaviour(row.dataset.beh)));
  }

  // ---- refactor: steps, checks, invariants --------------------------------
  function showStep(id) {
    const s = (DATA.steps || []).find(x => x.id === id);
    if (!s) return;
    state.sel = id;
    const st = s.status || "todo";
    const cr = s.checkResult;
    const chk = (DATA.checks || []).find(c => c.id === s.check);
    const touches = (s.touches || []).map(t =>
      `<div class="ref ${t.ok === false ? "bad" : ""}">${t.ok === false ? "✗" : "◦"}<span>${esc(t.path)}</span>
        <button data-hermes-send="Open ${esc(t.path)}">open</button></div>`).join("") ||
      `<div class="tip">no files listed</div>`;
    openInspector(`
      <h2>${esc(s.title)}</h2>
      <div class="sub">${s.id} · <span style="color:${PAL[st]}">${st}</span>${s.depends_on.length ? " · after " + s.depends_on.join(", ") : ""}</div>
      ${s.note ? `<p class="rule">${esc(s.note)}</p>` : ""}
      <div class="sec"><h3>Check</h3>
        ${chk ? `<div class="ref"><span class="tdot" style="background:${cr ? (cr.ok ? PAL.implemented : PAL.fail) : MUTED}"></span>
            <span>${chk.id} ${esc(chk.title || "")}</span></div>
          <div class="tip" style="font-family:var(--mono);font-size:10.5px;word-break:break-all">${esc(chk.run)}</div>
          ${cr ? `<div class="tip">exit ${cr.exit}${cr.expect !== 0 ? " (expected " + cr.expect + ")" : ""} · ${cr.duration}s</div>` : ""}`
          : `<div class="tip">no check attached</div>`}
      </div>
      <div class="sec"><h3>Touches</h3>${touches}</div>
      <div class="acts"><button class="btn" data-hermes-send="In ${esc(DATA.source)}, mark step ${s.id} as ${st === "done" ? "todo" : "done"} and re-run spec_checks.py.">Ask to update this step</button></div>
    `, id);
  }

  function renderStepCards() {
    const order = ["doing", "todo", "blocked", "done"];
    const groups = {};
    (DATA.steps || []).forEach(s => { const k = s.status || "todo"; (groups[k] = groups[k] || []).push(s); });
    const inv = (DATA.invariants || []).length
      ? `<div style="grid-column:1/-1;display:flex;align-items:center;gap:8px;margin:6px 0 2px">
           <span style="font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:${MUTED}">invariants</span>
           <span style="font-size:11px;color:${MUTED}">${DATA.invariants.length}</span></div>` +
        DATA.invariants.map(i => `<div class="card" data-meta="${i.id}" title="open the full text">
            <div class="top"><span class="id">${i.id}</span></div>
            <p>${esc(i.rule)}</p>
            <div class="foot"><span>${i.refs.length} ref${i.refs.length === 1 ? "" : "s"}</span>
              ${i.tests.length ? `<span>${i.tests.length} test${i.tests.length === 1 ? "" : "s"}</span>` : ""}${OPEN_CUE}</div></div>`).join("")
      : "";
    const steps = order.filter(k => groups[k]).map(k => {
      const cards = groups[k].map(s => {
        const dim = !stepMatches(s);
        const cr = s.checkResult;
        return `<div class="card ${dim ? "dim" : ""}" data-step="${s.id}">
          <div class="top"><span class="tdot" style="background:${PAL[k]}"></span><span class="id">${s.id}</span>
            ${s.depends_on.length ? `<span class="id">after ${s.depends_on.join(", ")}</span>` : ""}</div>
          <h3>${esc(s.title)}</h3>
          <div class="foot"><span>${s.touches.length} file${s.touches.length === 1 ? "" : "s"}</span>
            ${s.check ? `<span>${s.check}${cr ? (cr.ok ? " ✓" : " ✗") : ""}</span>` : ""}</div></div>`;
      }).join("");
      return `<div style="grid-column:1/-1;display:flex;align-items:center;gap:8px;margin-top:6px">
        <span class="tdot" style="background:${PAL[k]}"></span>
        <span style="font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:${MUTED}">${k}</span>
        <span style="font-size:11px;color:${MUTED}">${groups[k].length}</span></div>${cards}`;
    }).join("");
    const box = $("#body-beh");
    box.innerHTML = `<div class="cards">${inv}${steps || '<div class="empty">no steps match</div>'}</div>`;
    $$("[data-step]", box).forEach(card => card.addEventListener("click", () => showStep(card.dataset.step)));
    $$("[data-meta]", box).forEach(card => card.addEventListener("click", () => showMeta(card.dataset.meta)));
  }

  function renderChecks() {
    const rows = (DATA.checks || []).map(chk => {
      const r = chk.result;
      const label = r ? (r.ok ? "pass" : "FAIL") : "not run";
      const color = r ? (r.ok ? PAL.implemented : PAL.fail) : MUTED;
      const users = (DATA.steps || []).filter(s => s.check === chk.id).map(s => s.id);
      return `<tr data-step="${users[0] || ""}" style="cursor:${users[0] ? "pointer" : "default"}">
        <td class="mono">${chk.id}</td>
        <td>${esc(chk.title)}<div class="mono" style="color:var(--muted);margin-top:3px;word-break:break-all">${esc(chk.run)}</div></td>
        <td><span class="tdot" style="background:${color}"></span> ${label}${r ? ` (exit ${r.exit})` : ""}</td>
        <td class="mono">${users.join("<br>") || "—"}</td></tr>`;
    }).join("");
    const box = $("#body-trace");
    box.innerHTML = `<div style="overflow:auto;max-height:620px"><table>
        <thead><tr><th>id</th><th>check</th><th>result</th><th>steps</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4">no checks</td></tr>'}</tbody></table></div>
      <p class="tip" style="margin-top:8px">run with <span class="mono">python spec_checks.py ${esc(DATA.source)} --render</span></p>`;
    $$("tr[data-step]", box).forEach(row => row.addEventListener("click", () => { if (row.dataset.step) showStep(row.dataset.step); }));
  }

  function renderStepTable() {
    const rows = (DATA.steps || []).map(s => `<tr data-step="${s.id}" style="cursor:pointer">
      <td class="mono">${s.id}</td><td>${esc(s.title)}</td>
      <td><span class="tdot" style="background:${PAL[s.status]}"></span> ${s.status}</td>
      <td class="mono">${s.depends_on.join(", ") || "—"}</td>
      <td class="mono">${s.check || "—"}${s.checkResult ? (s.checkResult.ok ? " ✓" : " ✗") : ""}</td>
      <td class="mono">${s.touches.map(t => esc(t.path)).join("<br>") || "—"}</td></tr>`).join("");
    const box = $("#body-table");
    box.innerHTML = `<div style="overflow:auto;max-height:640px"><table>
      <thead><tr><th>id</th><th>step</th><th>status</th><th>after</th><th>check</th><th>files</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6">no steps</td></tr>'}</tbody></table></div>`;
    $$("tr[data-step]", box).forEach(row => row.addEventListener("click", () => showStep(row.dataset.step)));
  }

  // ---- footer ------------------------------------------------------------
  const rep = DATA.report || { errors: [], warnings: [] };
  const footBits = [DATA.source];
  if (rep.errors.length) footBits.push(`${rep.errors.length} lint error(s)`);
  if (rep.warnings.length) footBits.push(`${rep.warnings.length} warning${rep.warnings.length === 1 ? "" : "s"}`);
  footBits.push(DATA.rendered || DATA.generated || "");
  $("#foot").innerHTML = footBits.map((t, i) => i === 0 ? t : `<span>·</span><span>${t}</span>`).join("");
  const bannerFor = (list, cls, prefix) => {
    if (!list.length) return;
    const banner = document.createElement("div");
    banner.className = "banner" + (cls ? " " + cls : "");
    const head = `${prefix}${list.length > 1 ? ` (+${list.length - 1} more)` : ""}`;
    banner.textContent = `${head}: ${list[0].message}`;
    $("header").appendChild(banner);
  };
  bannerFor(rep.errors, "", `${rep.errors.length} lint error`);
  bannerFor(rep.warnings, "warn", `${rep.warnings.length} warning`);

  setTab(hasGraph ? "graph" : "behaviours");
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
