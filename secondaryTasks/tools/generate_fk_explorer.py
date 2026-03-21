import re
from collections import defaultdict


def extract_fk_constraints(sql_file):
    with open(sql_file, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    pattern = re.compile(
        r"ALTER TABLE SGOAM\.(\w+).*?"
        r"FOREIGN KEY\s*\((.*?)\).*?"
        r"REFERENCES SGOAM\.(\w+)\s*\((.*?)\)",
        re.DOTALL,
    )
    fks = pattern.findall(content)
    cleaned = []
    for from_table, from_cols, to_table, to_cols in fks:
        from_cols = ", ".join(c.strip() for c in from_cols.split(","))
        to_cols = ", ".join(c.strip() for c in to_cols.split(","))
        cleaned.append((from_table, from_cols, to_table, to_cols))
    return cleaned


def get_all_tables(fks):
    tables = set()
    for r in fks:
        tables.add(r[0])
        tables.add(r[2])
    return sorted(tables)


def fk_to_js(fks):
    lines = []
    for from_t, from_c, to_t, to_c in fks:
        from_c_esc = from_c.replace('"', '\\"')
        to_c_esc = to_c.replace('"', '\\"')
        lines.append(f'  ["{from_t}","{from_c_esc}","{to_t}","{to_c_esc}"]')
    return "[\n" + ",\n".join(lines) + "\n]"


def tables_to_js(tables):
    return "[" + ",".join(f'"{t}"' for t in tables) + "]"


def generate_html(fks, all_tables, output_file):
    fk_js = fk_to_js(fks)
    tables_js = tables_to_js(all_tables)

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SGOAM — FK Explorer</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#f8f8f8;color:#1a1a1a;font-size:14px}}
header{{background:#1F4E79;color:#fff;padding:12px 20px;display:flex;align-items:center;gap:16px}}
header h1{{font-size:16px;font-weight:500}}
header span{{font-size:12px;opacity:.7}}
.layout{{display:grid;grid-template-columns:260px 1fr;height:calc(100vh - 46px)}}
.left{{background:#fff;border-right:1px solid #e0e0e0;display:flex;flex-direction:column;overflow:hidden}}
.controls{{padding:8px;border-bottom:1px solid #e0e0e0;display:flex;flex-direction:column;gap:6px}}
.controls input[type=text]{{width:100%;padding:6px 8px;font-size:13px;border:1px solid #ccc;border-radius:6px;outline:none}}
.controls input[type=text]:focus{{border-color:#2E75B6}}
.mm-row{{display:flex;align-items:center;gap:6px;font-size:12px;color:#555;cursor:pointer;user-select:none;padding:2px 0}}
.tlist{{overflow-y:auto;flex:1}}
.trow{{padding:7px 10px;font-size:12px;cursor:pointer;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;justify-content:space-between}}
.trow:hover{{background:#f0f6ff}}
.trow.active{{background:#ddeeff;font-weight:500;color:#0C447C}}
.trow.mm{{color:#888}}
.trow.mm.active{{color:#0C447C}}
.badge{{font-size:10px;padding:1px 6px;border-radius:10px;background:#eee;color:#666;white-space:nowrap}}
.badge.has{{background:#ddeeff;color:#185FA5;font-weight:500}}
.right{{overflow-y:auto;padding:20px;background:#f8f8f8}}
.placeholder{{color:#aaa;text-align:center;padding:80px 20px;font-size:14px}}
.tname{{font-size:20px;font-weight:600;font-family:monospace;margin-bottom:4px}}
.tsub{{font-size:12px;color:#888;margin-bottom:20px}}
.section-hdr{{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#888;margin:20px 0 8px}}
.section-hdr:first-of-type{{margin-top:0}}
.card{{background:#fff;border:1px solid #e0e0e0;border-radius:8px;margin-bottom:8px;overflow:hidden}}
.card-header{{display:flex;align-items:center;gap:10px;padding:9px 12px;background:#fafafa;border-bottom:1px solid #f0f0f0}}
.dir-badge{{font-size:10px;padding:2px 7px;border-radius:4px;font-weight:600}}
.dir-out{{background:#e2f0d9;color:#375623}}
.dir-in{{background:#ddeeff;color:#0C447C}}
.card-tname{{font-size:13px;font-weight:500;font-family:monospace;color:#185FA5;cursor:pointer;text-decoration:underline;text-underline-offset:2px}}
.card-tname:hover{{color:#0C447C}}
.card-cols{{padding:8px 12px;font-size:12px;font-family:monospace;color:#555;line-height:1.8}}
.arrow{{color:#bbb;margin:0 6px}}
.col-from{{color:#1a1a1a}}
.col-to{{color:#1a1a1a}}
.stats{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
.stat{{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:8px 14px;text-align:center}}
.stat-n{{font-size:20px;font-weight:600;color:#1F4E79}}
.stat-l{{font-size:11px;color:#888;margin-top:2px}}
</style>
</head>
<body>
<header>
  <h1>SGOAM — FK Explorer</h1>
  <span id="hdr-info"></span>
</header>
<div class="layout">
  <div class="left">
    <div class="controls">
      <input type="text" id="srch" placeholder="Filtrer tables..." oninput="renderList()">
      <label class="mm-row">
        <input type="checkbox" id="mm-cb" checked onchange="toggleMM()">
        Afficher tables _MM
      </label>
    </div>
    <div class="tlist" id="tlist"></div>
  </div>
  <div class="right" id="detail">
    <div class="placeholder">Sélectionnez une table dans la liste pour explorer ses relations FK</div>
  </div>
</div>

<script>
const FK = {fk_js};
const ALL_TABLES = {tables_js};

let showMM = true;
let selected = null;

document.getElementById('hdr-info').textContent =
  ALL_TABLES.length + ' tables · ' + FK.length + ' contraintes FK';

function countRels(t){{
  return FK.filter(r => r[0]===t || r[2]===t).length;
}}

function toggleMM(){{
  showMM = document.getElementById('mm-cb').checked;
  renderList();
  if(selected) showTable(selected);
}}

function visibleTables(){{
  const q = document.getElementById('srch').value.toLowerCase();
  return ALL_TABLES.filter(t => {{
    if(!showMM && t.endsWith('_MM')) return false;
    if(q && !t.toLowerCase().includes(q)) return false;
    return true;
  }});
}}

function renderList(){{
  const tables = visibleTables();
  document.getElementById('tlist').innerHTML = tables.map(t => {{
    const n = countRels(t);
    const mm = t.endsWith('_MM');
    const act = selected===t ? 'active' : '';
    return `<div class="trow ${{mm?'mm':''}} ${{act}}" onclick="showTable('${{t}}')">
      <span>${{t}}</span>
      <span class="badge ${{n>0?'has':''}}">${{n}}</span>
    </div>`;
  }}).join('');
}}

function relCard(fromT, fromC, toT, toC, dir){{
  const otherTable = dir==='out' ? toT : fromT;
  const myC  = dir==='out' ? fromC : toC;
  const refC = dir==='out' ? toC   : fromC;
  return `<div class="card">
    <div class="card-header">
      <span class="dir-badge ${{dir==='out'?'dir-out':'dir-in'}}">${{dir==='out'?'FK sortante':'FK entrante'}}</span>
      <span class="card-tname" onclick="showTable('${{otherTable}}')">${{otherTable}}</span>
    </div>
    <div class="card-cols">
      <span class="col-from">${{myC}}</span>
      <span class="arrow">→</span>
      <span class="col-to">${{refC}}</span>
    </div>
  </div>`;
}}

function showTable(t){{
  selected = t;
  renderList();

  const out = FK.filter(r => r[0]===t);
  const inn = FK.filter(r => r[2]===t);
  const total = out.length + inn.length;

  let html = `<div class="tname">${{t}}</div>
    <div class="tsub">Source : SGOAM2.sql — contraintes ALTER TABLE ... FOREIGN KEY</div>
    <div class="stats">
      <div class="stat"><div class="stat-n">${{total}}</div><div class="stat-l">relations totales</div></div>
      <div class="stat"><div class="stat-n">${{out.length}}</div><div class="stat-l">FK sortantes</div></div>
      <div class="stat"><div class="stat-n">${{inn.length}}</div><div class="stat-l">FK entrantes</div></div>
    </div>`;

  if(out.length){{
    html += `<div class="section-hdr">FK sortantes — ${{t}} référence ces tables</div>`;
    html += out.map(r => relCard(r[0],r[1],r[2],r[3],'out')).join('');
  }}
  if(inn.length){{
    html += `<div class="section-hdr">FK entrantes — ces tables référencent ${{t}}</div>`;
    html += inn.map(r => relCard(r[0],r[1],r[2],r[3],'in')).join('');
  }}
  if(!total){{
    html += `<div class="placeholder">Aucune contrainte FK déclarée pour cette table.</div>`;
  }}

  document.getElementById('detail').innerHTML = html;
}}

renderList();
</script>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated: {output_file}")
    print(f"  Tables   : {len(all_tables)}")
    print(f"  FK total : {len(fks)}")


if __name__ == "__main__":
    import sys

    sql_path = sys.argv[1] if len(sys.argv) > 1 else "SGOAM2_sql.txt"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "fk_explorer.html"
    fks = extract_fk_constraints(sql_path)
    tables = get_all_tables(fks)
    generate_html(fks, tables, out_path)
