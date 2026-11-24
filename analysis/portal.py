"""A local window onto the analysis while it runs. Never leaves this machine.

    python analysis/portal.py <session_dir> [port]

Shows each step (waiting / running / done, with elapsed time and results as they land)
and a live frame from the class camera every few seconds, with boxes for what the face
model sees: green = confidently named (with name and score), amber = a face it can't name. Binds 127.0.0.1 only
so it never leaves this machine.
"""
import json
import random
import subprocess
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from classroom.backends.face_opencv import OpenCVFaces  # noqa: E402

SESS = Path(sys.argv[1]).resolve()
PILOT = ROOT
# The berkeleyhaas.me site repo holds the seating-chart photos (photos/2028). Set HAAS_SITE if it moves.
REPO = Path(os.environ.get("HAAS_SITE", ROOT.parent if (ROOT.parent / "photos").exists() else Path.home() / "Downloads" / "haas-2028-vercel"))
MEDIA = PILOT / "data" / "media"
REBUILD = {"proc": None, "finished": None}


def session_dir(date):
    if not date or "/" in date or ".." in date:
        return None
    hits = sorted(MEDIA.glob(f"{date}-*"))
    return hits[0] if hits and hits[0].is_dir() else None


def start_rebuild():
    """Rebuild portal.json in the background after a label is saved (about 20 s)."""
    if REBUILD["proc"] is not None and REBUILD["proc"].poll() is None:
        REBUILD["pending"] = True
        return
    dirs = sorted(p for p in MEDIA.glob("*-core-section-a") if (p / "turns_v2.json").exists())
    first = [p for p in dirs if p.name.startswith("2026-10-08")] or dirs[:1]
    order = first + [p for p in dirs if p not in first]
    cmd = [sys.executable, str(PILOT / "analysis" / "build_portal_data.py"), str(REPO), "SectionA"] + [str(p) for p in order]
    REBUILD["proc"] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def watch(proc=REBUILD["proc"]):
        proc.wait()
        REBUILD["finished"] = time.strftime("%H:%M:%S")
        if REBUILD.pop("pending", False):
            start_rebuild()
    __import__("threading").Thread(target=watch, daemon=True).start()
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8790
STAGES = SESS / "portal_stages.json"  # written by the person running the analysis
backend = OpenCVFaces(Path.home() / ".cache" / "classroom-pilot", min_face_px=24)
G = None


_N = None


def gallery():
    global G, _N
    if G is None and (SESS / "gallery.npz").exists():
        d = np.load(SESS / "gallery.npz")
        G, _N = d["emb"], d["names"]
    return G


def NAMES():
    gallery()
    return _N


def running(script):
    try:
        out = subprocess.run(["ps", "-axo", "etime=,command="], capture_output=True, text=True).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if script in line and "portal.py" not in line and "grep" not in line:
            et = line.split()[0]  # macOS: [[dd-]hh:]mm:ss
            days, _, rest = et.rpartition("-")
            secs = 0
            for part in rest.split(":"):
                secs = secs * 60 + int(part)
            return secs + (int(days) * 86400 if days else 0)
    return None


JOBS = [
    ("Transcribe the class and make voiceprints", "transcribe_session.py", "turns.json"),
    ("Find and match every face, once a second", "index_faces.py", "faces.npz"),
    ("Count who was seen", "presence.py", "presence.json"),
    ("Read desk name cards and check them against faces", "name_cards.py", "name_cards.json"),
    ("Name student speech from the camera, score voices", "speaker_labels.py", "speaker_labels.json"),
]


def status():
    jobs = []
    for title, script, out in JOBS:
        el = running(script)
        done = (SESS / out).exists()
        jobs.append({"title": title, "state": "running" if el is not None else "done" if done else "waiting",
                     "elapsed_s": el})
    results = {}
    for f in ("presence.json", "name_cards.json", "speaker_labels.json"):
        p = SESS / f
        if p.exists():
            results[f] = json.loads(p.read_text())
    extra = json.loads(STAGES.read_text()) if STAGES.exists() else []
    return {"jobs": jobs, "stages": extra, "results": results, "now": time.strftime("%H:%M:%S")}


def frame_jpeg():
    cap = cv2.VideoCapture(str(SESS / "camera.mp4"))
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1) / (cap.get(cv2.CAP_PROP_FPS) or 30)
    # Favour moments with students on screen once the face index exists.
    t = None
    fp = SESS / "faces.npz"
    if fp.exists() and random.random() < 0.8:
        ts = np.load(fp)["t"]
        vals, counts = np.unique(ts, return_counts=True)
        crowd = vals[counts >= 3]
        if len(crowd):
            t = float(random.choice(crowd))
    if t is None:
        t = random.uniform(0, dur)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    cap.release()
    if not ok:
        img = np.zeros((540, 960, 3), np.uint8)
    faces = backend.faces(img)
    Gm = gallery()
    gnames = NAMES()
    named = 0
    for f in faces:
        x, y, w, h = f.box
        x, y = max(0, x), max(0, y)
        who, score = None, 0.0
        if Gm is not None:
            sims = Gm @ (f.embedding / np.linalg.norm(f.embedding))
            o = np.argsort(-sims)[:2]
            score = float(sims[o[0]])
            if sims[o[0]] >= 0.50 and sims[o[0]] - sims[o[1]] >= 0.05:
                who = str(gnames[o[0]])
        named += who is not None
        col = (80, 200, 90) if who else (30, 170, 245)
        cv2.rectangle(img, (x, y), (x + w, y + h), col, 3)
        tag = f"{who} {score:.2f}" if who else f"? {score:.2f}"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x, y + h), (x + tw + 8, y + h + th + 10), col, -1)
        cv2.putText(img, tag, (x + 4, y + h + th + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2, cv2.LINE_AA)
    label = f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}   {len(faces)} faces   {named} named"
    cv2.rectangle(img, (0, 0), (img.shape[1], 56), (20, 20, 20), -1)
    cv2.putText(img, label, (18, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
    img = cv2.resize(img, (960, int(img.shape[0] * 960 / img.shape[1])))
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()


PAGE = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Pilot analysis</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#16202c;--mut:#5d6878;--line:#dfe3e8;--blue:#003262;--gold:#fdb515;--ok:#1f7a4d;--run:#b26b00}
@media (prefers-color-scheme:dark){:root{--bg:#0f141a;--card:#161d26;--ink:#e6ebf1;--mut:#97a3b2;--line:#283341;--blue:#8db8f0;--ok:#5cc994;--run:#f0b25a}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px;display:grid;gap:18px;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr)}
@media (max-width:820px){main{grid-template-columns:1fr}}
h1{grid-column:1/-1;margin:0;font-size:22px;color:var(--blue)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;min-width:0}
img{width:100%;border-radius:6px;display:block;transition:opacity .4s}
.legend{display:flex;gap:16px;color:var(--mut);font-size:13px;margin-top:8px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.job{display:grid;grid-template-columns:22px 1fr auto;gap:8px;padding:8px 0;border-bottom:1px solid var(--line);align-items:center}
.job:last-child{border:0}
.dot{width:12px;height:12px;border-radius:50%;background:var(--line)}
.running .dot{background:var(--run);animation:p 1.2s infinite}
.done .dot{background:var(--ok)}
@keyframes p{50%{opacity:.3}}
.el{color:var(--mut);font-variant-numeric:tabular-nums;font-size:13px}
pre{white-space:pre-wrap;font-size:12px;margin:0;color:var(--mut)}
h2{font-size:14px;margin:0 0 6px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}
</style>
<main>
<h1>Classroom pilot: live analysis of the core course SectionA, Oct 8 · <a href="/class" style="font-size:16px">Whole class view →</a></h1>
<div class="card"><h2>What the camera model sees</h2><img id=f src="/frame"><div class=legend>
<span><i class=sw style="background:#5ac850"></i>named confidently</span><span><i class=sw style="background:#f5aa1e"></i>face, not named</span><span>score = face match similarity, named at 0.50+; new frame every 4 s</span></div></div>
<div class="card"><h2>Steps</h2><div id=jobs></div><h2 style="margin-top:14px">Results so far</h2><pre id=res>waiting…</pre></div>
</main>
<script>
const fmt=s=>s==null?'':(s>=3600?Math.floor(s/3600)+'h ':'')+Math.floor(s%3600/60)+'m '+(s%60)+'s';
async function tick(){try{const s=await (await fetch('/status')).json();
 const all=[...s.jobs,...s.stages.map(x=>({title:x.title,state:x.state,elapsed_s:null,note:x.note}))];
 document.getElementById('jobs').innerHTML=all.map(j=>`<div class="job ${j.state}"><i class=dot></i><div>${j.title}${j.note?`<div class=el>${j.note}</div>`:''}</div><span class=el>${j.state==='running'?fmt(j.elapsed_s):j.state}</span></div>`).join('');
 const r=s.results;document.getElementById('res').textContent=Object.keys(r).length?JSON.stringify(r,null,1):'nothing finished yet';}catch(e){}}
function next(){const i=document.getElementById('f');const n=new Image();n.onload=()=>{i.src=n.src};n.src='/frame?'+Date.now()}
tick();setInterval(tick,3000);setInterval(next,4000);
</script>"""


CLASS_PAGE = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Whole class</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#16202c;--mut:#5d6878;--line:#dfe3e8;--blue:#003262;--gold:#fdb515}
@media (prefers-color-scheme:dark){:root{--bg:#0f141a;--card:#161d26;--ink:#e6ebf1;--mut:#97a3b2;--line:#283341;--blue:#8db8f0}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1280px;margin:0 auto;padding:24px 16px;display:grid;gap:22px}
h1{margin:0;font-size:22px;color:var(--blue)} h2{margin:0;font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}
.sum{display:flex;gap:18px;flex-wrap:wrap;color:var(--mut)} .sum b{color:var(--ink);font-size:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.tile img{width:100%;aspect-ratio:1/1;object-fit:cover;display:block}
.tile.no img{filter:grayscale(1) opacity(.45)}
.tile div{padding:8px 10px;font-size:13px;line-height:1.35}
.tile b{display:block;font-size:14px}
.no .st{color:#b4531a} .st{color:var(--mut)}
.rooms{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.rooms figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.rooms img,.pano{width:100%;display:block} figcaption{padding:6px 10px;font-size:13px;color:var(--mut)}
.pano{border-radius:8px}
.tabs button{font:inherit;padding:6px 12px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:6px;cursor:pointer}
.tabs button[aria-pressed=true]{background:var(--blue);color:#fff;border-color:var(--blue)}
</style>
<main>
<h1>Whole class view · the core course SectionA, Oct 8 · <a href="/" style="font-size:15px">← live analysis</a></h1>
<div class=sum id=sum></div>
<h2>The room</h2><p class=st style="margin:0">The camera shoots each position at a different pan and zoom, so only the views that overlap cleanly are joined below. Every view of the class is in the grid further down.</p><img class=pano id=pano alt="Panorama of part of the classroom stitched from overlapping camera views">
<h2>Students</h2>
<div class=tabs><button data-f=all aria-pressed=true>Everyone</button> <button data-f=seen aria-pressed=false>On camera</button> <button data-f=no aria-pressed=false>Not seen</button></div>
<div class=grid id=grid></div>
<h2>Every camera view of the class</h2><div class=rooms id=rooms></div>
</main>
<script>
let D;const fmt=s=>s>=60?Math.floor(s/60)+' min '+(s%60)+' s':s+' s';
function render(f){document.getElementById('grid').innerHTML=D.students.filter(s=>f=='all'||(f=='seen'?s.seen:!s.seen)).map(s=>`<div class="tile ${s.seen?'':'no'}"><img src="/cv/${s.tile}" alt="${s.name}"><div><b>${s.name}</b><span class=st>${s.seen?`on camera ${fmt(s.seen_seconds)}<br>${s.first_seen} – ${s.last_seen} · match ${s.best_score}`:'not seen on camera (roster photo)'}</span></div></div>`).join('')}
fetch('/cv/class.json').then(r=>r.json()).then(d=>{D=d;
document.getElementById('sum').innerHTML=`<span><b>${d.enrolled}</b> enrolled</span><span><b>${d.seen}</b> recognised on camera</span><span><b>${d.enrolled-d.seen}</b> not seen</span><span><b>${d.rooms.length}</b> camera views of the class</span>`;
if(d.panorama)document.getElementById('pano').src='/cv/'+d.panorama;else document.getElementById('pano').remove();
document.getElementById('rooms').innerHTML=d.rooms.map(r=>`<figure><img src="/cv/${r.image}" alt="Camera view ${r.preset}"><figcaption>View ${r.preset} · ${r.faces} faces · at ${r.time}${r.in_panorama?' · in the panorama':''}</figcaption></figure>`).join('');
render('all');
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.setAttribute('aria-pressed',x===b));render(b.dataset.f)});});
</script>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _file(self, base, rel):
        fp = (base / rel).resolve()
        if not str(fp).startswith(str(base.resolve())) or not fp.is_file():
            self.send_response(404); self.end_headers(); return None
        return fp

    def do_POST(self):
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        if path == "/api/label":
            # One span ({date,start,end}) or many ("spans": [...]) with one kind/student.
            spans = body.get("spans") or [{k: body.get(k) for k in ("date", "start", "end")}]
            kind, student = body.get("kind"), body.get("student")
            if kind not in ("student", "not_student", "professor") or any(not s.get("date") or s.get("start") is None for s in spans):
                self.send_response(400); self.end_headers(); return
            lp = PILOT / "data" / "portal" / "labels.json"
            labels = json.loads(lp.read_text()) if lp.exists() else []
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            for sp in spans:
                labels = [l for l in labels if not (l["date"] == sp["date"] and abs(l["start"] - sp["start"]) < 0.5)]
                labels.append({"date": sp["date"], "start": sp["start"], "end": sp.get("end"), "kind": kind, "student": student, "at": now})
            lp.write_text(json.dumps(labels, indent=1))
            start_rebuild()
            return self._send(json.dumps({"ok": True, "labels": len(labels)}).encode(), "application/json")
        self.send_response(404); self.end_headers()

    def _range(self, fp, ctype):
        size = fp.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b))
            end = int(b) if (a and b) else size - 1
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(fp, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_GET(self):
        path = self.path.split("?")[0]
        query = dict(q.split("=", 1) for q in self.path.partition("?")[2].split("&") if "=" in q)
        if path.startswith("/api/audio/"):
            sd = session_dir(path[len("/api/audio/"):])
            if not sd or not (sd / "audio.m4a").exists():
                self.send_response(404); self.end_headers(); return
            return self._range(sd / "audio.m4a", "audio/mp4")
        if path.startswith("/api/clip/"):
            sd = session_dir(path[len("/api/clip/"):])
            try:
                a, b = float(query.get("start", 0)), float(query.get("end", 0))
            except ValueError:
                a, b = 0, 0
            if not sd or b <= a:
                self.send_response(404); self.end_headers(); return
            a = max(0.0, a - 1.0); dur = min(90.0, b - a + 1.0)
            cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{a:.2f}", "-i", str(sd / "camera.mp4"),
                   "-ss", f"{a:.2f}", "-i", str(sd / "audio.m4a"), "-t", f"{dur:.2f}", "-map", "0:v:0", "-map", "1:a:0",
                   "-vf", "scale=960:-2", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-c:a", "aac", "-b:a", "96k",
                   "-movflags", "frag_keyframe+empty_moov", "-f", "mp4", "-"]
            out = subprocess.run(cmd, capture_output=True).stdout
            return self._send(out, "video/mp4")
        if path == "/api/rebuild":
            return self._send(json.dumps({"running": REBUILD["proc"] is not None and REBUILD["proc"].poll() is None,
                                          "finished": REBUILD["finished"]}).encode(), "application/json")
        # The shadcn app (built into data/portal/app), its data, and the images it shows.
        if path == "/api/portal":
            fp = PILOT / "data" / "portal" / "portal.json"
            return self._send(fp.read_bytes(), "application/json")
        if path.startswith("/media/"):
            fp = self._file(PILOT / "data" / "media", path[len("/media/"):])
            return fp and self._send(fp.read_bytes(), "image/jpeg")
        if path.startswith("/photos/2028/"):
            fp = self._file(REPO / "photos" / "2028", path[len("/photos/2028/"):])
            return fp and self._send(fp.read_bytes(), "image/jpeg")
        if path == "/" or path.startswith("/assets/"):
            app = PILOT / "data" / "portal" / "app"
            fp = self._file(app, "index.html" if path == "/" else path.lstrip("/"))
            if fp:
                ct = {".js": "text/javascript", ".css": "text/css", ".html": "text/html; charset=utf-8",
                      ".woff2": "font/woff2", ".svg": "image/svg+xml"}.get(fp.suffix, "application/octet-stream")
                self._send(fp.read_bytes(), ct)
            return
        if path == "/legacy":
            return self._send(PAGE.encode(), "text/html; charset=utf-8")
        if self.path.startswith("/frame"):
            body, ctype = frame_jpeg(), "image/jpeg"
        elif self.path.startswith("/status"):
            body, ctype = json.dumps(status()).encode(), "application/json"
        elif self.path.startswith("/class"):
            body, ctype = CLASS_PAGE.encode(), "text/html; charset=utf-8"
        elif self.path.startswith("/cv/"):
            rel = self.path[4:].split("?")[0]
            fp = (SESS / "class_view" / rel).resolve()
            if not str(fp).startswith(str((SESS / "class_view").resolve())) or not fp.is_file():
                self.send_response(404); self.end_headers(); return
            body = fp.read_bytes()
            ctype = "application/json" if fp.suffix == ".json" else "image/jpeg"
        else:
            self.send_response(404); self.end_headers(); return
        self._send(body, ctype)

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
