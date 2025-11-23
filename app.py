#!/data/data/com.termux/files/usr/bin/env python3
"""
Mobile-friendly YT extractor for Termux (and cloud)

Features:
- Auto-detect single vs playlist (no mode dropdown)
- Clean mobile UI:
    - Title "Video Downloader"
    - URL box + Fetch button
    - Status: Idle / Fetching… / Success / Failed
    - Results:
        Single: title once + Download (purple) + Preview
        Playlist: each item has title + Download + Preview
- Only uses real downloadable progressive files (audio+video, http/https)
- /download endpoint proxies file so browser downloads with correct filename
- /upload_cookies endpoint lets user upload cookies.txt from the browser
- yt-dlp automatically uses cookies.txt IF it exists (for cloud / sign-in)
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
import os

app = Flask(__name__)

# ------------------- FRONTEND (HTML + JS) -------------------

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

  /* Cookies area */
  .cookies-box{
    margin-top:12px;
    padding:10px;
    border-radius:12px;
    background:rgba(15,23,42,0.9);
    border:1px dashed rgba(148,163,184,0.5);
    font-size:12px;
  }
  .cookies-row{
    display:flex;
    gap:8px;
    margin-top:6px;
    flex-wrap:wrap;
  }
  #cookiesFile{
    flex:1;
    font-size:12px;
  }
  #uploadCookiesBtn{
    padding:7px 10px;
    border-radius:8px;
    border:0;
    background:rgba(124,58,237,0.9);
    color:#fdf4ff;
    font-size:13px;
  }
  #cookiesStatus{
    margin-top:4px;
    font-size:11px;
    color:var(--muted);
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

    <div class="cookies-box">
      <div><b>Optional:</b> Upload <code>cookies.txt</code> for cloud / sign-in videos.</div>
      <div class="cookies-row">
        <input type="file" id="cookiesFile" accept=".txt" />
        <button id="uploadCookiesBtn">Upload cookies</button>
      </div>
      <div id="cookiesStatus">No cookies uploaded yet.</div>
    </div>
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
  const title = data.title || 'Video';
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
    note.textContent = data.reason || 'No direct downloadable file found.';
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
    note.textContent = data.reason || 'No items in playlist (all unavailable / deleted / locked).';
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
      note.textContent = e.reason || 'No direct downloadable file for this item.';
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

async function uploadCookies(){
  const input = $('cookiesFile');
  const status = $('cookiesStatus');
  if(!input.files || !input.files[0]){
    status.textContent = 'Choose a cookies.txt file first.';
    return;
  }
  const file = input.files[0];
  status.textContent = 'Uploading cookies…';

  const fd = new FormData();
  fd.append('file', file);

  try{
    const resp = await fetch('/upload_cookies', {
      method: 'POST',
      body: fd
    });
    const data = await resp.json().catch(()=>null);
    if(!resp.ok){
      status.textContent = (data && data.error) ? data.error : 'Upload failed.';
      return;
    }
    status.textContent = data && data.message ? data.message : 'Cookies uploaded.';
  }catch(e){
    console.error(e);
    status.textContent = 'Upload error: ' + (e.message || String(e));
  }
}

$('fetchBtn').addEventListener('click', fetchData);
$('url').addEventListener('keydown', e=>{ if(e.key === 'Enter') fetchData(); });
$('uploadCookiesBtn').addEventListener('click', uploadCookies);

setStatus('idle','Idle');
</script>
</body>
</html>
"""

# ------------------- BACKEND HELPERS -------------------

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

# ------------------- ROUTES -------------------

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

    # yt-dlp options (add cookiefile if cookies.txt present)
    base_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    if os.path.exists("cookies.txt"):
        base_opts["cookiefile"] = "cookies.txt"

    # Try to extract info; ANY error will return 200 with a friendly reason
    try:
        with YoutubeDL(base_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        msg = str(e)
        reason = "Cannot extract info."
        if "Sign in to confirm you’re not a bot" in msg or "Sign in to confirm you're not a bot" in msg:
            reason = ("YouTube is asking you to sign in (bot check). "
                      "Upload cookies.txt from your browser and try again.")
        elif "Video unavailable" in msg:
            reason = "Video unavailable (deleted, private or blocked)."

        return jsonify({
            "mode": "single",
            "title": "Unavailable video",
            "file": None,
            "reason": reason,
        }), 200

    if not info:
        return jsonify({
            "mode": "single",
            "title": "Unavailable video",
            "file": None,
            "reason": "No info returned (maybe unavailable or blocked).",
        }), 200

    # PLAYLIST HANDLING
    if "entries" in info and info["entries"]:
        raw_entries = [e for e in info["entries"] if e]

        if len(raw_entries) > 1:
            out_entries = []
            for e in raw_entries:
                video_url = e.get("url") or e.get("webpage_url") or e.get("id")
                if not video_url:
                    continue
                if not video_url.startswith("http"):
                    video_url = f"https://www.youtube.com/watch?v={video_url}"

                try:
                    with YoutubeDL(base_opts) as vdl:
                        vinfo = vdl.extract_info(video_url, download=False)
                except Exception:
                    out_entries.append({
                        "id": e.get("id"),
                        "title": e.get("title"),
                        "file": None,
                        "reason": "Skipped (sign-in required / unavailable).",
                    })
                    continue

                fmts = vinfo.get("formats") or []
                best = choose_best_file(fmts)
                out_entries.append({
                    "id": vinfo.get("id") or e.get("id"),
                    "title": vinfo.get("title") or e.get("title"),
                    "file": fmt_to_file(best),
                })

            return jsonify({
                "mode": "playlist",
                "title": info.get("title") or "Playlist",
                "entries": out_entries,
                "reason": None if out_entries else "All items unavailable / locked.",
            }), 200

        elif len(raw_entries) == 1:
            entry = raw_entries[0]
        else:
            return jsonify({
                "mode": "playlist",
                "title": info.get("title") or "Playlist",
                "entries": [],
                "reason": "No playable items found in this playlist.",
            }), 200
    else:
        entry = info  # Not a playlist

    # SINGLE VIDEO
    fmts = entry.get("formats") or []
    best = choose_best_file(fmts)

    if not best:
        return jsonify({
            "mode": "single",
            "title": entry.get("title"),
            "file": None,
            "reason": "No direct downloadable file (maybe sign-in or streaming-only).",
        }), 200

    return jsonify({
        "mode": "single",
        "title": entry.get("title"),
        "file": fmt_to_file(best),
    }), 200

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

@app.route("/upload_cookies", methods=["POST"])
def upload_cookies():
    """
    Accepts a cookies.txt file uploaded from the frontend and saves it
    as cookies.txt in the current working directory.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files['file']
    if not f or f.filename == '':
        return jsonify({"error": "No selected file"}), 400

    save_path = os.path.join(os.getcwd(), "cookies.txt")
    try:
        f.save(save_path)
    except Exception as e:
        return jsonify({"error": "Failed to save cookies.txt", "details": str(e)}), 500

    return jsonify({"message": "cookies.txt uploaded successfully. yt-dlp will use it for the next fetch."}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Video Downloader on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)