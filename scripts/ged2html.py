"""Просмотрщик дерева: из файла GEDCOM пишет один HTML, работает офлайн.

Запуск: python3 ged2html.py дерево.ged [дерево.html] [--root I1] [--include-private]
По умолчанию HTML пишется рядом с .ged, корень — первый человек в файле.
Люди с RESN privacy по умолчанию обезличены: «живой родственник», без дат,
мест, заметок и источников. --include-private — полный вид, только для себя.
Слева — предки выбранного человека (клик по любому — сделать его центром),
справа — карточка: даты, места, заметки, источники с уровнем доверия, родители,
супруги, дети, братья и сёстры.
"""
import json
import re
import sys
from pathlib import Path


EVENTS = {"BIRT": "Рождение", "DEAT": "Смерть", "BURI": "Похоронен(а)", "MARR": "Брак",
          "RESI": "Жил(а)", "OCCU": "Занятие", "EVEN": "Событие"}
MONTHS = {m: i for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


def ru_date(d):
    if not d:
        return ""
    def one(s):
        p = s.split()
        if len(p) == 3 and p[1] in MONTHS:
            return f"{int(p[0]):02d}.{MONTHS[p[1]]:02d}.{p[2]}"
        if len(p) == 2 and p[0] in MONTHS:
            return f"{MONTHS[p[0]]:02d}.{p[1]}"
        return s
    m = re.match(r"BET (.+) AND (.+)", d)
    if m:
        return f"{one(m[1])}–{one(m[2])}"
    for k, v in {"ABT ": "около ", "BEF ": "до ", "AFT ": "после "}.items():
        if d.startswith(k):
            return v + one(d[len(k):])
    return one(d)


def parse(text):
    recs, cur, l1, l2 = {}, None, None, None
    for no, line in enumerate(text.splitlines(), 1):
        m = re.match(r"(\d+) (@[^@\s]+@ )?(\w+) ?(.*)", line.lstrip("\ufeff"))
        if not m:
            if line.strip():
                print(f"пропущена строка {no}: не по формату GEDCOM", file=sys.stderr)
            continue
        lvl, xref, tag, val = int(m[1]), (m[2] or "").strip().strip("@"), m[3], m[4]
        if lvl == 0:
            cur = {"type": tag, "id": xref, "names": [], "events": [], "notes": [], "sources": [],
                   "famc": [], "fams": [], "husb": "", "wife": "", "chil": [], "sex": "", "resn": ""}
            if xref:
                recs[xref] = cur
            l1 = l2 = None
            continue
        if cur is None:
            continue
        if lvl == 1:
            l2 = None
            if tag == "NAME":
                l1 = {"kind": "name", "val": val.replace("/", "").strip(), "type": ""}
                cur["names"].append(l1)
            elif tag in EVENTS:
                l1 = {"kind": "event", "tag": tag, "val": val, "date": "", "plac": "", "note": "",
                      "type": "", "src": []}
                cur["events"].append(l1)
            elif tag == "NOTE":
                l1 = {"kind": "note"}
                cur["notes"].append(val)
            elif tag == "SOUR":
                l1 = {"kind": "src", "id": val.strip("@"), "quay": ""}
                cur["sources"].append(l1)
            elif tag in ("FAMC", "FAMS"):
                cur[tag.lower()].append(val.strip("@")); l1 = None
            elif tag in ("HUSB", "WIFE"):
                cur[tag.lower()] = val.strip("@"); l1 = None
            elif tag == "CHIL":
                cur["chil"].append(val.strip("@")); l1 = None
            elif tag == "SEX":
                cur["sex"] = val; l1 = None
            elif tag == "RESN":
                cur["resn"] = val; l1 = None
            elif tag in ("TITL", "PUBL"):
                cur[tag.lower()] = val; l1 = {"kind": tag.lower()}
            else:
                l1 = None
        elif lvl == 2 and l1 is not None:
            if tag in ("CONC", "CONT") and l1["kind"] == "note":
                cur["notes"][-1] += ("\n" if tag == "CONT" else "") + val
            elif tag in ("CONC", "CONT") and l1["kind"] in ("titl", "publ"):
                cur[l1["kind"]] += ("\n" if tag == "CONT" else "") + val
            elif tag == "NOTE" and l1["kind"] == "notesrc":
                pass
            elif l1["kind"] == "name" and tag == "TYPE":
                l1["type"] = val
            elif l1["kind"] == "name" and tag == "NOTE":
                cur["notes"].append(val)
            elif l1["kind"] == "event":
                if tag == "DATE":
                    l1["date"] = ru_date(val)
                elif tag == "PLAC":
                    l1["plac"] = val
                elif tag == "NOTE":
                    l1["note"] = val
                elif tag == "TYPE":
                    l1["type"] = val
                elif tag == "SOUR":
                    l2 = {"id": val.strip("@"), "page": "", "quay": ""}
                    l1["src"].append(l2)
            elif l1["kind"] == "src" and tag == "QUAY":
                l1["quay"] = val
            elif l1["kind"] == "src" and tag == "PAGE":
                l1["page"] = val
        elif lvl == 3 and l2 is not None:
            if tag == "PAGE":
                l2["page"] = val
            elif tag == "QUAY":
                l2["quay"] = val
    return recs


def main():
    args = sys.argv[1:]
    root = None
    include_private = "--include-private" in args
    args = [a for a in args if a != "--include-private"]
    if "--root" in args:
        i = args.index("--root")
        root = args[i + 1].strip("@")
        del args[i:i + 2]
    ged = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else ged.with_suffix(".html")
    if out.suffix.lower() not in (".html", ".htm"):
        sys.exit(f"выход должен быть .html: {out}")
    if out.is_symlink() or out.resolve() == ged.resolve():
        sys.exit(f"не пишу в {out}: это симлинк или сам GEDCOM")
    recs = parse(ged.read_text(encoding="utf-8"))
    people, fams, srcs = {}, {}, {}
    for x, r in recs.items():
        if r["type"] == "INDI":
            main_name = next((n["val"] for n in r["names"] if not n["type"]), r["names"][0]["val"] if r["names"] else "?")
            other = [n["val"] for n in r["names"] if n["type"]]
            if r["resn"] == "privacy" and not include_private:
                people[x] = {"name": "живой родственник", "aka": [], "sex": r["sex"], "living": True,
                             "events": [], "notes": [], "sources": [], "famc": r["famc"], "fams": r["fams"]}
                continue
            people[x] = {"name": main_name or "?", "aka": other, "sex": r["sex"], "living": r["resn"] == "privacy",
                         "events": [{k: e[k] for k in ("tag", "date", "plac", "note", "type", "val", "src")}
                                    for e in r["events"]],
                         "notes": r["notes"], "sources": r["sources"], "famc": r["famc"], "fams": r["fams"]}
        elif r["type"] == "FAM":
            members = [m for m in [r["husb"], r["wife"], *r["chil"]] if m]
            if not include_private and any(recs.get(m, {}).get("resn") == "privacy" for m in members):
                fams[x] = {"husb": r["husb"], "wife": r["wife"], "chil": r["chil"], "notes": [], "sources": [],
                           "events": []}
                continue
            fams[x] = {"husb": r["husb"], "wife": r["wife"], "chil": r["chil"], "notes": r["notes"],
                       "sources": r["sources"],
                       "events": [{k: e[k] for k in ("tag", "date", "plac", "note", "type", "val", "src")}
                                  for e in r["events"]]}
        elif r["type"] == "SOUR":
            srcs[x] = {"title": r.get("titl", ""), "publ": r.get("publ", ""),
                       "url": next((n for n in r["notes"] if n.startswith("http")), "")}
    data = json.dumps({"people": people, "fams": fams, "srcs": srcs, "events": EVENTS,
                       "root": root or next(iter(people), "")}, ensure_ascii=False)
    for ch, code in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        data = data.replace(ch, code)
    out.write_text(TEMPLATE.replace("/*DATA*/", data), encoding="utf-8")
    print(f"ok: {out} — {len(people)} человек, {len(fams)} семей")


TEMPLATE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Семейное дерево</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f7f5f0;--card:#fff;--ink:#1f2328;--mute:#6b6f76;--line:#c9c3b6;--m:#2f6f9f;--f:#a34d6d;--acc:#8a6d1f}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink);display:flex;height:100vh}
#left{flex:1;overflow:auto;padding:16px 20px}#right{width:420px;border-left:1px solid var(--line);background:var(--card);overflow:auto;padding:18px 20px}
h1{font-size:18px;margin:0 0 4px}.hint{color:var(--mute);font-size:12px;margin-bottom:12px}
#search{width:100%;padding:7px 10px;border:1px solid var(--line);border-radius:6px;margin-bottom:6px;font:inherit}
#results{max-height:180px;overflow:auto;margin-bottom:10px}#results div{padding:3px 6px;cursor:pointer;border-radius:4px}#results div:hover{background:#efe9dc}
.tree{display:flex;align-items:center}.gen{display:flex;flex-direction:column;justify-content:space-around}
.node{display:flex;align-items:center}.pbox{width:210px;padding:6px 9px;margin:4px 10px 4px 0;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--mute);border-radius:6px;cursor:pointer}
.pbox:hover{box-shadow:0 1px 4px rgba(0,0,0,.15)}.pbox.M{border-left-color:var(--m)}.pbox.F{border-left-color:var(--f)}
.pbox.sel{outline:2px solid var(--acc)}.pbox .n{font-weight:600}.pbox .d{color:var(--mute);font-size:12px}
.pbox.empty{border-style:dashed;color:var(--mute);cursor:default;background:transparent}
.parents{display:flex;flex-direction:column;border-left:1px solid var(--line);padding-left:10px}
.weak{opacity:.75}.weak .n::after{content:" · родители — гипотеза";font-weight:400;color:var(--acc);font-size:11px}
h2{font-size:17px;margin:0 0 2px}h3{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--mute);margin:16px 0 6px}
.ev{margin:0 0 8px}.ev b{font-weight:600}.pl{color:var(--mute)}.q{display:inline-block;font-size:11px;padding:0 5px;border-radius:8px;margin-left:4px;background:#eee}
.q3{background:#d7ecd9}.q2{background:#e6efd2}.q1{background:#f5ead0}.q0{background:#f3d9d4}
.link{color:var(--m);cursor:pointer;text-decoration:underline dotted}.note{background:#faf8f3;border-left:3px solid var(--line);padding:6px 9px;margin:6px 0;white-space:pre-wrap}
.src{font-size:12px;color:var(--mute);margin:3px 0}.src a{color:var(--m)}.living{font-size:11px;background:#e8eef6;padding:1px 6px;border-radius:8px;margin-left:6px}
.legend span{margin-right:8px}
</style></head><body>
<div id="left">
  <h1>Семейное дерево</h1>
  <div class="hint">Слева направо — предки выбранного человека. Клик по карточке — сделать её центром. Справа — всё, что о человеке известно, с источниками.
  <span class="legend">Доверие: <span class="q q3">3 документ</span><span class="q q2">2 косвенно</span><span class="q q1">1 устно</span><span class="q q0">0 гипотеза</span></span></div>
  <input id="search" placeholder="Найти человека по имени…"><div id="results"></div>
  <div id="tree"></div>
</div>
<div id="right"></div>
<script>
const D=/*DATA*/;
const P=D.people,F=D.fams,S=D.srcs;
const yr=s=>{const m=(s||"").match(/\d{4}/g);return m?m[0]:""};
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const safeUrl=u=>/^https?:\/\//i.test(u||"")?esc(u):"";
function life(p){const b=p.events.find(e=>e.tag==="BIRT"),d=p.events.find(e=>e.tag==="DEAT");
  const by=b?b.date:"",dy=d?d.date:"";if(!by&&!dy)return"";return esc((by||"?")+(dy?" – "+dy:""))}
function famQuay(fid){const f=F[fid];if(!f)return 3;const q=f.sources.map(s=>+s.quay).filter(x=>!isNaN(x));return q.length?Math.min(...q):3}
function box(id,sel){if(!id)return '<div class="pbox empty">неизвестно</div>';const p=P[id];
  const weak=p.famc.length&&famQuay(p.famc[0])<=0;
  return `<div class="pbox ${p.sex} ${sel?'sel':''} ${weak?'weak':''}" data-go="${esc(id)}"><div class="n">${esc(p.name)}</div><div class="d">${life(p)}</div></div>`}
function node(id,depth,sel){const p=id?P[id]:null;let par="";
  if(p&&depth<7&&p.famc.length){const f=F[p.famc[0]];
    if(f&&(f.husb||f.wife))par=`<div class="parents">${node(f.husb,depth+1)}${node(f.wife,depth+1)}</div>`}
  return `<div class="node">${box(id,sel)}${par}</div>`}
function srcLine(s){const r=S[s.id]||{};const qv=/^[0-3]$/.test(String(s.quay))?String(s.quay):"";const q=qv?`<span class="q q${qv}">${qv}</span>`:"";
  const u=safeUrl(r.url),title=esc(r.title||s.id);const t=u?`<a href="${u}" target="_blank" rel="noopener noreferrer">${title}</a>`:title;
  return `<div class="src">— ${t}${s.page?", "+esc(s.page):""}${q}</div>`}
function person(id){if(!P[id])return "";return `<span class="link" data-go="${esc(id)}">${esc(P[id].name)}</span> <span class="pl">${life(P[id])}</span>`}
function card(id){const p=P[id];let h=`<h2>${esc(p.name)}${p.living?'<span class="living">жив(а), только локально</span>':''}</h2>`;
  if(p.aka.length)h+=`<div class="pl">также: ${esc(p.aka.join(", "))}</div>`;
  if(p.events.length){h+="<h3>События</h3>";for(const e of p.events){
    h+=`<div class="ev"><b>${esc(e.type||D.events[e.tag]||e.tag)}</b>${e.val?": "+esc(e.val):""} ${esc(e.date)}${e.plac?`<div class="pl">${esc(e.plac)}</div>`:""}${e.note?`<div class="note">${esc(e.note)}</div>`:""}${e.src.map(srcLine).join("")}</div>`}}
  const par=p.famc.map(f=>F[f]).filter(Boolean);
  if(par.length){h+="<h3>Родители</h3>";for(const f of par){for(const x of [f.husb,f.wife])if(x)h+=`<div>${person(x)}</div>`;
    const sib=f.chil.filter(c=>c!==id);if(sib.length)h+=`<h3>Братья и сёстры</h3>`+sib.map(c=>`<div>${person(c)}</div>`).join("");
    if(famQuay(p.famc[0])<=0)h+=`<div class="note">Связь с родителями — гипотеза (уровень доверия ${famQuay(p.famc[0])}).${f.notes.length?"\n"+esc(f.notes.join("\n")):""}</div>`}}
  for(const fid of p.fams){const f=F[fid];if(!f)continue;const sp=f.husb===id?f.wife:f.husb;
    h+=`<h3>Семья${sp?"":" (супруг(а) неизвестен)"}</h3>`;if(sp)h+=`<div>${person(sp)}</div>`;
    for(const e of f.events)h+=`<div class="ev pl">${esc(D.events[e.tag]||e.tag)} ${esc(e.date)} ${esc(e.plac)}${e.src.map(srcLine).join("")}</div>`;
    if(f.chil.length)h+='<div class="pl" style="margin-top:4px">Дети:</div>'+f.chil.map(c=>`<div>${person(c)}</div>`).join("")}
  if(p.notes.length)h+="<h3>Заметки</h3>"+p.notes.map(n=>`<div class="note">${esc(n)}</div>`).join("");
  if(p.sources.length)h+="<h3>Источники</h3>"+p.sources.map(srcLine).join("");
  return h}
function go(id){if(!P[id])return;document.getElementById("tree").innerHTML=`<div class="tree">${node(id,0,true)}</div>`;
  document.getElementById("right").innerHTML=card(id);location.hash=id}
const inp=document.getElementById("search"),res=document.getElementById("results");
inp.oninput=()=>{const q=inp.value.trim().toLowerCase();if(q.length<2){res.innerHTML="";return}
  res.innerHTML=Object.entries(P).filter(([k,p])=>(p.name+" "+p.aka.join(" ")).toLowerCase().includes(q)).slice(0,40)
   .map(([k,p])=>`<div data-go="${esc(k)}">${esc(p.name)} <span class="pl">${life(p)}</span></div>`).join("")};
document.addEventListener("click",ev=>{const t=ev.target.closest("[data-go]");if(!t)return;
  if(res.contains(t)){res.innerHTML="";inp.value=""}go(t.dataset.go)});
go((location.hash.slice(1) in P)?location.hash.slice(1):D.root);
</script></body></html>
"""

if __name__ == "__main__":
    main()
