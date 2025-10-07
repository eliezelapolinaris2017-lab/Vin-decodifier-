#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json, os, re
from flask import Flask, request, jsonify, Response

APP_TITLE = "Doctor Car Pro — DTC Web"
DB_PATH = "dtc_db.json"
DTC_REGEX = re.compile(r"^[PBCU][0-9A-Fa-f]{4}$")

app = Flask(__name__)

def load_db():
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # normaliza keys en mayúsculas
    return {k.upper(): v for k, v in data.items()}

def save_db(data: dict):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

# ---------------- API ----------------
@app.get("/api/dtc/<code>")
def api_get_dtc(code):
    db = load_db()
    code = code.upper()
    if not DTC_REGEX.match(code):
        return jsonify({"ok": False, "error": "Formato inválido. Ej: P0420"}), 400
    desc = db.get(code)
    if not desc:
        return jsonify({"ok": False, "found": False})
    return jsonify({"ok": True, "found": True, "code": code, "desc": desc})

@app.get("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify({"ok": True, "results": []})
    db = load_db()
    results = [{"code": c, "desc": d} for c, d in db.items() if q in d.lower()]
    # limitar a 100 resultados
    return jsonify({"ok": True, "results": sorted(results, key=lambda x: x["code"])[:100]})

@app.get("/api/list/<prefix>")
def api_list_prefix(prefix):
    p = (prefix or "").upper()
    if p not in ("P","B","C","U"):
        return jsonify({"ok": False, "error": "Prefijo inválido (P/B/C/U)"}), 400
    db = load_db()
    items = [{"code": c, "desc": d} for c, d in db.items() if c.startswith(p)]
    return jsonify({"ok": True, "results": sorted(items, key=lambda x: x["code"])})

@app.post("/api/dtc")
def api_add_or_update():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").upper().strip()
    desc = (payload.get("desc") or "").strip()
    if not DTC_REGEX.match(code):
        return jsonify({"ok": False, "error": "Código inválido. Ej: P0ABC"}), 400
    if not desc:
        return jsonify({"ok": False, "error": "Descripción requerida"}), 400
    db = load_db()
    db[code] = desc
    save_db(db)
    return jsonify({"ok": True, "code": code, "desc": desc})

@app.delete("/api/dtc/<code>")
def api_delete(code):
    code = code.upper()
    db = load_db()
    if code in db:
        del db[code]
        save_db(db)
        return jsonify({"ok": True, "deleted": code})
    return jsonify({"ok": False, "error": "No existe"}), 404

@app.get("/api/export")
def api_export():
    db = load_db()
    return Response(
        json.dumps(db, ensure_ascii=False, indent=2, sort_keys=True),
        mimetype="application/json",
        headers={"Content-Disposition":"attachment; filename=dtc_export.json"}
    )

# ---------------- UI (SPA) ----------------
INDEX_HTML = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{APP_TITLE}</title>
<meta name="theme-color" content="#0d0f15">
<style>
:root {{
  --bg:#0d1117; --panel:#0f172a; --ink:#e6edf3; --muted:#93a0ad; --acc:#58a6ff;
  --ok:#22c55e; --warn:#f59e0b; --danger:#ef4444; --line:#1f2937; --radius:14px;
}}
*{{box-sizing:border-box}}
html,body{{height:100%}}
body{{
  margin:0; font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  background:linear-gradient(180deg,#0b1220 0%, #0d1117 40%, #0b0f16 100%);
  color:var(--ink);
}}
header{{
  position:sticky; top:0; z-index:10; background:#0b1220e0; backdrop-filter:blur(6px);
  border-bottom:1px solid var(--line); padding:14px 16px; display:flex; gap:10px; align-items:center;
}}
h1{{margin:0; font-size:18px; letter-spacing:.3px}}
.container{{max-width:980px; margin:20px auto; padding:0 16px}}
.card{{
  background:#0e1525a0; border:1px solid #1f2a3a; border-radius:var(--radius); padding:16px; margin:12px 0;
  box-shadow:0 8px 24px #00000040;
}}
.grid{{display:grid; grid-template-columns:1fr; gap:12px}}
.row{{display:flex; gap:8px; flex-wrap:wrap}}
input,button,select,textarea{{
  background:#0b1220; color:var(--ink); border:1px solid #1f2937; border-radius:10px; padding:10px 12px;
}}
button{{cursor:pointer}}
button.acc{{border-color:#2a3d5a}}
button.primary{{background:var(--acc); color:#0a0f16; border-color:#1e3a8a}}
kbd{{background:#0b1220; padding:.2em .4em; border-radius:6px; border:1px solid #1f2937}}
table{{width:100%; border-collapse:collapse; font-size:14px}}
th,td{{padding:8px 10px; border-bottom:1px solid #1f2937}}
th{{text-align:left; color:#b8c2cc; font-weight:600}}
.code{{font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace}}
footer{{color:var(--muted); text-align:center; padding:24px 0 40px}}
.badge{{display:inline-block; padding:2px 8px; border:1px solid #2b3b52; border-radius:999px; color:#9fb0c5}}
.small{{font-size:12px;color:var(--muted)}}
</style>
</head>
<body>
<header>
  <h1>🔧 {APP_TITLE}</h1>
  <span class="badge">Python + Flask</span>
</header>

<div class="container">
  <div class="card">
    <div class="row">
      <input id="code" class="code" placeholder="Ej: P0420" maxlength="5" />
      <button class="primary" onclick="buscarCodigo()">Buscar código</button>
      <input id="q" placeholder="Buscar por palabra: catalizador, EVAP, O2..." style="flex:1" />
      <button onclick="buscarTexto()">Buscar texto</button>
      <button onclick="listar('P')">P</button>
      <button onclick="listar('B')">B</button>
      <button onclick="listar('C')">C</button>
      <button onclick="listar('U')">U</button>
      <button onclick="exportar()">Exportar JSON</button>
    </div>
    <div id="result" style="margin-top:10px"></div>
  </div>

  <div class="card">
    <h3 style="margin-top:0">Añadir / Actualizar DTC</h3>
    <div class="grid">
      <input id="newCode" class="code" placeholder="Código (P0ABC)" maxlength="5" />
      <textarea id="newDesc" rows="3" placeholder="Descripción del DTC"></textarea>
      <div class="row">
        <button class="primary" onclick="guardar()">Guardar</button>
        <button class="acc" onclick="limpiar()">Limpiar</button>
      </div>
      <div id="saveMsg" class="small"></div>
    </div>
  </div>

  <div class="card small">
    <b>Tip:</b> El formato válido es <kbd>P|B|C|U</kbd> + 4 hex (ej: <span class="code">P0420</span>). 
    <br> P=Powertrain, B=Body, C=Chassis, U=Network.
  </div>
</div>

<footer>
  Hecho con ❤️ en Python &middot; Flask SPA
</footer>

<script>
const el = (id) => document.getElementById(id);

function showRows(rows) {{
  if (!rows || rows.length === 0) {{
    el('result').innerHTML = '<div class="small">Sin resultados.</div>'; return;
  }}
  let html = '<table><thead><tr><th>Código</th><th>Descripción</th></tr></thead><tbody>';
  for (const r of rows) {{
    html += `<tr><td class="code">\${r.code}</td><td>\${r.desc}</td></tr>`;
  }}
  html += '</tbody></table>';
  el('result').innerHTML = html;
}}

async function buscarCodigo() {{
  const code = el('code').value.trim().toUpperCase();
  if (!code) return;
  const res = await fetch(`/api/dtc/\${code}`);
  const data = await res.json();
  if (data.ok && data.found) {{
    showRows([{{code: data.code, desc: data.desc}}]);
  }} else {{
    el('result').innerHTML = '<div class="small">No encontrado.</div>';
  }}
}}

async function buscarTexto() {{
  const q = el('q').value.trim();
  const res = await fetch(`/api/search?q=\${encodeURIComponent(q)}`);
  const data = await res.json();
  if (data.ok) showRows(data.results);
}}

async function listar(prefix) {{
  const res = await fetch(`/api/list/\${prefix}`);
  const data = await res.json();
  if (data.ok) showRows(data.results);
}}

async function exportar() {{
  const res = await fetch('/api/export');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'dtc_export.json';
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}}

async function guardar() {{
  const code = el('newCode').value.trim().toUpperCase();
  const desc = el('newDesc').value.trim();
  const res = await fetch('/api/dtc', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ code, desc }})
  }});
  const data = await res.json();
  if (data.ok) {{
    el('saveMsg').textContent = `Guardado: ${'{'}${'{'}data.code{'}'}{'}'} ✓`;
    el('code').value = code;
    buscarCodigo();
  }} else {{
    el('saveMsg').textContent = 'Error: ' + (data.error || 'desconocido');
  }}
}}

function limpiar() {{
  el('newCode').value = '';
  el('newDesc').value = '';
  el('saveMsg').textContent = '';
}}
</script>
</body>
</html>
"""

@app.get("/")
def index():
    return INDEX_HTML

if __name__ == "__main__":
    # Ejecuta: python app.py
    app.run(host="0.0.0.0", port=5000, debug=True)
