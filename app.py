#!/data/data/com.termux/files/usr/bin/env python3
"""
Mobile-friendly YT extractor for Termux

- Auto-detects single video vs playlist (no mode dropdown)
- UI:
    Top: "Video Downloader" (app title)
    Under it: status (Idle / Fetching… / Success / Failed)
    Then: URL box + Fetch button
- Results:
    Single: show video title once + two buttons (Download, Preview)
    Playlist: each item shows its own title + two buttons (Download, Preview)
- Only uses real downloadable progressive files (audio+video, http/https)
- /download endpoint proxies the file with correct filename so browser downloads it
- Uses ignoreerrors=True so unavailable playlist items are skipped instead of crashing
"""

from flask import (
    Flask,
    request,
    jsonify,
    render_template_string,
    Response,
    stream_with_context,
)
from yt_dlp import YoutubeDL
import urllib.request
import re

app = Flask(__name__)

HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Video Downloader</title>
<style>
  :root{
    --bg:#050816; --card:#0b1220; --muted:#9aa6b2;
    --accent:#06b6d4; --accent2:#7c3aed; --purple:#a855f7; --bad:#ef4444;
  }
  html,body{
    margin:0;height:100%;
    font-family:system-ui,Roboto,Arial;
    background:linear-gradient(180deg,#050816,#020617);
    color:#eaf4ff;
  }
  .wrap{
    max-width:640px;
    margin:0 auto;
    padding:12px;
  }
  .card{
    background:rgba(15,23,42,0.98);
    border-radius:16px;
    padding:14px;
    box-shadow:0 10px 30px rgba(0,0,0,0.7);
    margin-bottom:12px;
  }
  .app-title{
    font-size:20px;
    font-weight:700;
    text-align:center;
    margin-bottom:6px;
  }
  .status{
    font-size:13px;
    text-align:center;
    min-height:1.2em;
    margin-bottom:8px;
  }
  .status.idle{color:var(--muted);}
  .status.fetching{color:#fbbf24;}
  .status.ok{color:#22c55e;}
  .status.error{color:var(--bad);}

  .field{margin-top:8px;}
  label{
    display:block;
    font-size:13px;
    color:var(--muted);
    margin-bottom:4px;
  }
  input,button{font-size:15px;}
  #url{
    width:100%;
    padding:10px;
    border-radius:10px;
    border:0;
    background:rgba(15,23,42,0.9);
    color:#eaf4ff;
    box-sizing:border-box;
  }
  #fetchBtn{
    width:100%;
    padding:11px 14px;
    margin-top:10px;
    border-radius:10px;
    border:0;
    background:linear-gradient(90deg,var(--accent),var(--accent2));
    color:white;
    font-weight:600;
  }
  #error{
    font-size:13px;
    color:var(--bad);
    min-height:1.2em;
    margin-top:6px;
    text-align:center;
  }

  /* Results */
  #title{
    font-size:16px;
    font-weight:600;
    text-align:center;
    margin-bottom:10px;
    min-height:1.4em;
  }
  .video-box{
    margin-top:10px;
    padding:12px;
    border-radius:12px;
    background:rgba(15,23,42,0.95);
    border:1px solid rgba(148,163,184,0.4);
  }
  .video-title{
    font-size:14px;
    font-weight:600;
    text-align:center;
    margin-bottom:8px;
  }
  .btn-row{
    display:flex;
    flex-direction:row;
    gap:10px;
    flex-wrap:wrap;
    justify-content:center;
  }
  .btn-main{
    flex:1;
    min-width:120px;
    padding:10px 12px;
    border-radius:10px;
    border:0;
    font-size:15px;
  }
  /* Download button PURPLE */
  .btn-download{
    background:var(--purple);
    color:#fdf4ff;
  }
  .btn-preview{
    background:transparent;
    border:1px solid rgba(148,163,184,0.7);
    color:#eaf4ff;
  }
  .btn-disabled{
    opacity:0.5;
    pointer-events:none;
  }
  .note{
    font-size:12px;
    color:var(--muted);
    text-align:center;
    margin-top:6px;
  }

  @media (max-width:400px){
    .btn-main{min-width:100%;}
  }
</style>
</head>
<body>
<div class="wrap">

  <!-- Controls -->
  <div class="card">
    <div class="app-title">Video Downloader</div>
    <div id="status" class="status idle">Idle</div>

    <div class="field">
      <label for="url">YouTube URL</label>
      <input id="url" placeholder="https://www.youtube.com/watch?v=..." />
    </div>

    <button id="fetchBtn">Fetch</button>

    <div id="error"></div>
  </div>

  <!-- Results -->
  <div class="card">
    <div id="title"></div>
    <div id="results"></div>
  </div>

</div>

<script>
function $(id){return document.getElementById(id);}

function setStatus(state, msg){
  const el = $('status');
  el.className = 'status ' + state;
  el.textContent = msg;
}
function setError(msg){
  $('error').textContent = msg || '';
}

async function fetchData(){
  const url = $('url').value.trim();
  setError('');
  $('title').textContent = '';
  $('results').innerHTML = '';

  if(!url){
    setStatus('error','Failed');
    setError('Enter URL');
    return;
  }

  setStatus('fetching','Fetching…');

  try{
    const resp = await fetch('/extract', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url})
    });

    const txt = await resp.text();
    let data = null;
    try{ data = JSON.parse(txt); }catch(e){}

    if(!resp.ok){
      const msg = (data && data.error) ? data.error : (txt || ('HTTP '+resp.status));
      setStatus('error','Failed');
      setError(msg);
      return;
    }
    if(!data){
      setStatus('error','Failed');
      setError('Empty response');
      return;
    }

    if(data.mode === 'playlist'){
      renderPlaylist(data);
    }else{
      renderSingle(data);
    }
    setStatus('ok','Success');
  }catch(e){
    console.error(e);
    setStatus('error','Failed');
    setError(e.message || String(e));
  }
}

function buildDownloadUrl(file, title){
  const params = new URLSearchParams();
  params.set('url', file.url);
  params.set('title', title || 'video');
  params.set('ext', file.ext || 'mp4');
  return '/download?' + params.toString();
}

function renderSingle(data){
  const results = $('results');
  results.innerHTML = '';
  const title = data.title || 'Untitled';
  $('title').textContent = title;

  const file = data.file;

  const box = document.createElement('div');
  box.className = 'video-box';

  const row = document.createElement('div');
  row.className = 'btn-row';

  const btnDl = document.createElement('button');
  btnDl.className = 'btn-main btn-download';
  btnDl.textContent = 'Download';

  const btnPrev = document.createElement('button');
  btnPrev.className = 'btn-main btn-preview';
  btnPrev.textContent = 'Preview';

  if(!file || !file.url){
    btnDl.classList.add('btn-disabled');
    btnPrev.classList.add('btn-disabled');
    row.appendChild(btnDl);
    row.appendChild(btnPrev);
    box.appendChild(row);
    const note = document.createElement('div');
    note.className = 'note';
    note.textContent = 'No direct downloadable file found.';
    box.appendChild(note);
  }else{
    btnDl.addEventListener('click', ()=>{
      const proxyUrl = buildDownloadUrl(file, title);
      const a = document.createElement('a');
      a.href = proxyUrl;
      a.target = '_blank';
      document.body.appendChild(a);
      a.click();
      a.remove();
    });

    btnPrev.addEventListener('click', ()=>{
      const w = window.open('', '_blank');
      const esc = (file.url || '').replace(/"/g,'&quot;');
      w.document.write(
        '<title>Preview</title>' +
        '<body style="margin:0;background:#000;display:flex;align-items:center;justify-content:center;height:100vh">' +
        '<video controls autoplay style="max-width:100%;max-height:100%">' +
        '<source src="'+esc+'">' +
        '</video></body>'
      );
    });

    row.appendChild(btnDl);
    row.appendChild(btnPrev);
    box.appendChild(row);
  }

  results.appendChild(box);
}

function renderPlaylist(data){
  const results = $('results');
  results.innerHTML = '';
  const title = data.title || 'Playlist';
  const entries = data.entries || [];
  $('title').textContent = title + (entries.length ? ' ('+entries.length+' items)' : '');

  if(!entries.length){
    const note = document.createElement('div');
    note.className = 'note';
    note.textContent = 'No items in playlist (all unavailable or deleted).';
    results.appendChild(note);
    return;
  }

  entries.forEach((e, idx)=>{
    const box = document.createElement('div');
    box.className = 'video-box';

    const t = document.createElement('div');
    t.className = 'video-title';
    t.textContent = (idx+1) + '. ' + (e.title || e.id || 'Item');
    box.appendChild(t);

    const row = document.createElement('div');
    row.className = 'btn-row';

    const btnDl = document.createElement('button');
    btnDl.className = 'btn-main btn-download';
    btnDl.textContent = 'Download';

    const btnPrev = document.createElement('button');
    btnPrev.className = 'btn-main btn-preview';
    btnPrev.textContent = 'Preview';

    const file = e.file;

    if(!file || !file.url){
      btnDl.classList.add('btn-disabled');
      btnPrev.classList.add('btn-disabled');
      row.appendChild(btnDl);
      row.appendChild(btnPrev);
      box.appendChild(row);
      const note = document.createElement('div');
      note.className = 'note';
      note.textContent = 'No direct downloadable file for this item.';
      box.appendChild(note);
    }else{
      btnDl.addEventListener('click', ()=>{
        const proxyUrl = buildDownloadUrl(file, e.title || 'item');
        const a = document.createElement('a');
        a.href = proxyUrl;
        a.target = '_blank';
        document.body.appendChild(a);
        a.click();
        a.remove();
      });
      btnPrev.addEventListener('click', ()=>{
        const w = window.open('', '_blank');
        const esc = (file.url || '').replace(/"/g,'&quot;');
        w.document.write(
          '<title>Preview</title>' +
          '<body style="margin:0;background:#000;display:flex;align-items:center;justify-content:center;height:100vh">' +
          '<video controls autoplay style="max-width:100%;max-height:100%">' +
          '<source src="'+esc+'">' +
          '</video></body>'
        );
      });
      row.appendChild(btnDl);
      row.appendChild(btnPrev);
      box.appendChild(row);
    }

    results.appendChild(box);
  });
}

$('fetchBtn').addEventListener('click', fetchData);
$('url').addEventListener('keydown', e=>{ if(e.key === 'Enter') fetchData(); });

setStatus('idle','Idle');
</script>
</body>
</html>
"""

# ------------ Backend helpers ------------

def human_size(n):
    if not n:
        return ''
    try:
        n = int(n)
    except:
        return ''
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"

def is_downloadable_file(fmt: dict) -> bool:
    """
    Only keep real downloadable progressive files:
    - has url
    - has audio+video
    - protocol is http/https (no m3u8/dash/mpd)
    """
    url = fmt.get("url")
    if not url:
        return False
    proto = (fmt.get("protocol") or "").lower()
    if "m3u8" in proto or "dash" in proto or "mpd" in proto:
        return False
    ac = fmt.get("acodec")
    vc = fmt.get("vcodec")
    if not ac or ac == "none":
        return False
    if not vc or vc == "none":
        return False
    if proto and not proto.startswith("http"):
        return False
    return True

def choose_best_file(formats):
    """Pick best downloadable file by height + bitrate."""
    best = None
    best_score = -1
    for f in formats:
        if not is_downloadable_file(f):
            continue
        h = int(f.get("height") or 0)
        tbr = int(float(f.get("tbr") or 0))
        score = h * 1000 + tbr
        if score > best_score:
            best_score = score
            best = f
    return best

def fmt_to_file(f):
    if not f:
        return None
    return {
        "url": f.get("url"),
        "ext": f.get("ext") or "mp4",
        "filesize": human_size(f.get("filesize") or f.get("filesize_approx")),
    }

def sanitize_title(title: str) -> str:
    """
    Sanitize title to an ASCII-safe filename for HTTP headers.
    Keep only A-Z, a-z, 0-9, space, dot, dash, underscore.
    """
    title = title or "video"
    title = re.sub(r'[^A-Za-z0-9 ._-]+', '', title)
    title = title.strip()
    if not title:
        title = "video"
    if len(title) > 100:
        title = title[:100]
    return title

# ------------ Routes ------------

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/extract", methods=["POST"])
def extract():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "URL is required"}), 400
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    # ignoreerrors=True => skip unavailable videos in playlist instead of raising
    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        # single or playlist completely failing (deleted/private)
        return jsonify({"error": "Cannot extract info (maybe deleted/private)", "details": str(e)}), 400

    if not info:
        return jsonify({"error": "No info returned (maybe all items unavailable)"}), 400

    # Auto-detect playlist vs single
    if "entries" in info and info["entries"]:
        # entries may contain None for errors (because ignoreerrors=True) -> filter
        entries_info = [e for e in info["entries"] if e]
        if len(entries_info) > 1:
            # Playlist mode
            out_entries = []
            for e in entries_info:
                fmts = e.get("formats") or []
                best = choose_best_file(fmts)
                out_entries.append({
                    "id": e.get("id"),
                    "title": e.get("title"),
                    "file": fmt_to_file(best),
                })
            return jsonify({
                "mode": "playlist",
                "title": info.get("title") or "Playlist",
                "entries": out_entries,
            })
        elif len(entries_info) == 1:
            entry = entries_info[0]
        else:
            # all items failed / unavailable
            return jsonify({
                "mode": "playlist",
                "title": info.get("title") or "Playlist",
                "entries": [],
            })
    else:
        entry = info

    # Single video
    fmts = entry.get("formats") or []
    best = choose_best_file(fmts)

    return jsonify({
        "mode": "single",
        "title": entry.get("title"),
        "file": fmt_to_file(best),
    })

@app.route("/download")
def download_proxy():
    """
    Proxy download:
    - Takes ?url=...&title=...&ext=...
    - Streams the file and sets Content-Disposition so browser downloads it
    """
    url = request.args.get("url", "").strip()
    title = request.args.get("title", "").strip()
    ext = request.args.get("ext", "mp4").strip().lower() or "mp4"

    if not url:
        return "Missing url", 400

    safe_title = sanitize_title(title)
    filename = f"{safe_title}.{ext}"

    def generate():
        with urllib.request.urlopen(url) as resp:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                yield chunk

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "application/octet-stream",
    }
    return Response(stream_with_context(generate()), headers=headers)

if __name__ == "__main__":
    print("Starting Video Downloader at http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)