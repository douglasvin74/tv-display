import base64, glob, hmac, json, os, queue, re, secrets, subprocess, threading, urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(BASE, "media")
def _meu_ip():
    """IP do notebook na rede atual (muda ao trocar de rede)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as k:
        k.connect(("10.255.255.255", 1))
        return k.getsockname()[0]


HOST_URL = os.environ.get("HOST_URL") or f"http://{_meu_ip()}:8000"
STATE_FILE = os.path.join(BASE, "state.json")
PW_FILE = os.path.join(BASE, "senha.txt")
PAGE, PLAYER, AUDIO = (".html",), (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mkv", ".mov"), (".mp3", ".ogg", ".wav", ".m4a", ".aac")
PUBLIC = {"/tv", "/tv.html", "/api/events", "/api/musicEnded", "/player"}  # usados pela TV, sem senha

if not os.path.exists(PW_FILE):
    open(PW_FILE, "w").write(secrets.token_urlsafe(9))
PASSWORD = open(PW_FILE).read().strip()

STATE = {"url": "", "music": "", "paused": False, "volume": 100, "playlist": [], "playing": False, "yt": "", "ytlist": ""}
try:
    STATE.update(json.load(open(STATE_FILE)))
except (OSError, ValueError):
    pass
STATE["music"] = urllib.parse.unquote(STATE["music"].rsplit("/", 1)[-1])  # estado antigo guardava a URL
STATE.update(_i=0, _cur=-1)  # posição da playlist (só em memória)
CLIENTS = []        # uma fila por tela conectada (/tv)
WAKE = threading.Event()


def save():
    json.dump({k: v for k, v in STATE.items() if not k.startswith("_")}, open(STATE_FILE, "w"))


def send(msg):
    for c in list(CLIENTS):
        c.put(msg)


def kind(f):
    f = f.lower()
    return "audio" if f.endswith(AUDIO) else "player" if f.endswith(PLAYER) else "page" if f.endswith(PAGE) else None


def files():
    return sorted(f for f in os.listdir(MEDIA) if not f.startswith(".") and kind(f))


def content_url(f):
    path = "/player?f=" if kind(f) == "player" else "/media/"
    return HOST_URL + path + urllib.parse.quote(f)


def show(url):
    STATE["url"] = url
    send({"cmd": "load", "url": url})


YT_ID = re.compile(r"(?:youtu\.be/|[?&]v=|/embed/|/shorts/)([\w-]{11})")
YT_LIST = re.compile(r"[?&]list=([\w-]+)")


def yt_parse(url):
    """(id do vídeo, id da lista) de um link do YouTube; listas 'RD...' (mix automático) não funcionam no embed."""
    v, l = YT_ID.search(url), YT_LIST.search(url)
    return (v.group(1) if v else "", l.group(1) if l and not l.group(1).startswith("RD") else "")


def play_music(f):
    STATE.update(music=f, paused=False, yt="", ytlist="")
    send({"cmd": "yt", "v": ""})
    send({"cmd": "music", "url": HOST_URL + "/media/" + urllib.parse.quote(f) if f else ""})


def step_music(d):
    if STATE["yt"]:
        return send({"cmd": "mctl", "action": "next" if d > 0 else "prev"})
    t = [f for f in files() if kind(f) == "audio"]
    if t:
        play_music(t[(t.index(STATE["music"]) + d) % len(t)] if STATE["music"] in t else t[0])


def playlist_loop():
    while True:
        items = STATE["playlist"]
        if not (STATE["playing"] and items):
            WAKE.wait()
            WAKE.clear()
            continue
        i = STATE["_i"] % len(items)
        STATE.update(_i=i + 1, _cur=i)
        show(content_url(items[i]["f"]))
        save()
        if WAKE.wait(items[i]["s"]):
            WAKE.clear()


def speak(text):
    """Gera a fala com a voz Maria (pt-BR) do Windows e manda a TV tocar."""
    win = lambda p: subprocess.check_output(["wslpath", "-w", p], text=True).strip()
    for old in glob.glob(os.path.join(MEDIA, ".voz*.wav")):
        os.remove(old)
    n = STATE["_voz"] = STATE.get("_voz", 0) + 1
    txt, wav = os.path.join(BASE, ".voz.txt"), os.path.join(MEDIA, f".voz{n}.wav")
    open(txt, "w", encoding="utf-8").write(text[:500])
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", win(os.path.join(BASE, "speak.ps1")),
                    win(txt), win(wav)], check=True, timeout=20, capture_output=True)
    send({"cmd": "sayurl", "url": f"{HOST_URL}/media/.voz{n}.wav"})


def command(q):
    """Executa um comando do painel. Retorna False se inválido."""
    c, f = q.get("cmd"), q.get("f", "")
    valid = f in files()
    if c == "showFile" and valid and kind(f) != "audio":
        STATE["playing"] = False
        show(content_url(f))
    elif c == "loadURL" and q.get("url"):
        STATE["playing"] = False
        show(q["url"])
    elif c == "clear":
        STATE["playing"] = False
        show("")
    elif c == "playMusic" and valid and kind(f) == "audio":
        play_music(f)
    elif c == "playYoutube":
        v, l = yt_parse(q.get("url", ""))
        if not v:
            return False
        play_music("")
        STATE.update(yt=v, ytlist=l)
        send({"cmd": "yt", "v": v, "list": l})
    elif c == "watchYoutube":
        v, l = yt_parse(q.get("url", ""))
        if not v:
            return False
        STATE["playing"] = False
        if STATE["yt"]:  # evita dois áudios ao mesmo tempo (e esconde o mini-player)
            play_music("")
        elif STATE["music"]:
            STATE["paused"] = True
            send({"cmd": "mctl", "action": "pause"})
        show(f"https://www.youtube.com/embed/{v}?autoplay=1&rel=0&" + (f"list={l}" if l else f"playlist={v}"))
    elif c == "stopMusic":
        play_music("")
    elif c == "musicNext":
        step_music(1)
    elif c == "musicPrev":
        step_music(-1)
    elif c in ("musicPause", "musicResume"):
        STATE["paused"] = c == "musicPause"
        send({"cmd": "mctl", "action": "pause" if STATE["paused"] else "play"})
    elif c == "setVolume":
        STATE["volume"] = max(0, min(100, int(q.get("level", 100))))
        send({"cmd": "vol", "level": STATE["volume"]})
    elif c == "playlistAdd" and valid and kind(f) != "audio":
        STATE["playlist"].append({"f": f, "s": max(3, int(q.get("s", 10)))})
        WAKE.set()
    elif c == "playlistRemove":
        i = int(q.get("i", -1))
        if 0 <= i < len(STATE["playlist"]):
            STATE["playlist"].pop(i)
            STATE["_i"] = 0
            WAKE.set()
    elif c == "playlistClear":
        STATE.update(playlist=[], playing=False)
    elif c in ("playlistStart", "playlistStop"):
        STATE.update(playing=c == "playlistStart", _i=0, _cur=-1)
        WAKE.set()
    elif c == "setOverlayMessage":
        send({"cmd": "msg", "text": q.get("text", "")})
    elif c == "textToSpeech":
        speak(q.get("text", ""))
    else:
        return False
    save()
    return True


def status():
    return {"tv": len(CLIENTS), "files": [{"f": f, "k": kind(f)} for f in files()],
            **{k: v for k, v in STATE.items() if k != "_i"}}


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=BASE, **k)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def reply(self, body, ctype="application/json", code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authed(self):
        h = self.headers.get("Authorization", "")
        try:
            pw = base64.b64decode(h[6:]).decode().partition(":")[2] if h.startswith("Basic ") else None
        except ValueError:
            pw = None
        return pw is not None and hmac.compare_digest(pw, PASSWORD)

    def events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        q = queue.Queue()
        CLIENTS.append(q)
        if STATE["url"]:
            q.put({"cmd": "load", "url": STATE["url"], "restore": True})
        music = HOST_URL + "/media/" + urllib.parse.quote(STATE["music"]) if STATE["music"] else ""
        q.put({"cmd": "music", "url": music, "restore": True})
        if music:
            q.put({"cmd": "mctl", "action": "pause" if STATE["paused"] else "play"})
        q.put({"cmd": "yt", "v": STATE["yt"], "list": STATE["ytlist"], "restore": True})  # v vazio = esconde o player
        q.put({"cmd": "vol", "level": STATE["volume"]})
        try:
            while True:
                try:
                    out = f"data: {json.dumps(q.get(timeout=15))}\n\n"
                except queue.Empty:
                    out = ": ka\n\n"
                self.wfile.write(out.encode())
                self.wfile.flush()
        except OSError:
            pass
        finally:
            CLIENTS.remove(q)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        public = u.path in PUBLIC or u.path.startswith("/media/")
        if not public and not self.authed():
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Controle TV"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if u.path == "/api/events":
            return self.events()
        if u.path == "/api/musicEnded":
            step_music(1)
            return self.reply("{}")
        if u.path == "/api/status":
            return self.reply(json.dumps(status()))
        if u.path == "/api/tv":
            try:
                ok = command(q)
            except (ValueError, OSError, subprocess.SubprocessError):
                ok = False
            return self.reply('{"status":"OK"}' if ok else '{"error":"comando invalido"}', code=200 if ok else 400)
        if u.path == "/player":
            f = os.path.basename(q.get("f", ""))
            src = "/media/" + urllib.parse.quote(f)
            if f.lower().endswith((".mp4", ".webm", ".mkv", ".mov")):
                tag = f'<video src="{src}" autoplay loop controls></video>'
            elif kind(f) == "player":
                tag = f'<img src="{src}">'
            else:
                return self.reply("tipo invalido", "text/plain", 400)
            return self.reply(
                "<body style='margin:0;background:#000;display:grid;place-items:center;height:100vh'>"
                f"{tag}<style>img,video{{max-width:100vw;max-height:100vh}}</style>", "text/html")
        if u.path in ("/", "/control.html", "/tv", "/tv.html") or u.path.startswith("/media/"):
            self.path = {"/": "/control.html", "/tv": "/tv.html"}.get(u.path, self.path)
            return super().do_GET()
        self.send_error(404)


threading.Thread(target=playlist_loop, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
