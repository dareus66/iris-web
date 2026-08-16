"""
iris-web - a local web gallery for iris.c

Starts a small server that queues image generations, runs iris, and keeps
every image next to the prompt and seed that produced it, so any picture
can be made again exactly.

Standard library only. Start it with:

    python iris_web.py

then open the address it prints. Options:

    --iris PATH       path to the iris binary (default: look around)
    --model PATH      path to the model directory (default: look around)
    --threads N       BLAS threads (default: half the logical CPUs)
    --port N          preferred port (default: 8770)
    --no-browser      do not open a browser window

Requires iris.c: https://github.com/antirez/iris.c
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
IMMAGINI = BASE / "images"
INPUT_DIR = IMMAGINI / "input"
CATALOGO = IMMAGINI / "catalog.jsonl"
WEB = BASE / "web"

PORTA_PREFERITA = 8770
PORTE_DA_PROVARE = 10
DIM_MIN = 64
DIM_MAX = 1024

WINDOWS = os.name == "nt"

# Filled in by configura(), so nothing about one machine is baked into
# the code. Every entry can be overridden from the command line.
CFG = {
    "iris": None,
    "model": None,
    "threads": None,
    "port": PORTA_PREFERITA,
    "browser": True,
}

# Ready-made style prompts. They describe a result rather than giving an
# instruction, which is the form these models handle best.
STILI = {
    "none": "",
    "watercolour": "a watercolor painting, loose wet brushstrokes, soft washes of colour, visible paper texture",
    "oil paint": "an oil painting, thick impasto brushstrokes, rich pigment, canvas weave visible",
    "pencil": "a graphite pencil drawing, fine hatching and soft shading, white sketchbook paper",
    "ink": "an ink drawing, bold confident black linework, high contrast, minimal flat colour",
    "35mm film": "a 35mm film photograph, natural grain, warm analogue colour, shallow depth of field",
    "art nouveau": "an Art Nouveau poster, flowing organic outlines, flat decorative colour, ornamental border",
    "storybook": "a children's book illustration, gouache texture, warm friendly palette, gentle outlines",
    "woodcut": "a woodcut print, carved bold lines, limited ink colours, visible grain of the block",
}


# ---------------------------------------------------------------------------
# Pure helpers (no side effects, easy to test)
# ---------------------------------------------------------------------------

def valida_dimensione(valore):
    """Clamp a requested size to a multiple of 16 inside the allowed range.

    Raises ValueError on anything non-numeric: the value ends up on the
    iris command line.
    """
    try:
        n = int(str(valore).strip())
    except (TypeError, ValueError):
        raise ValueError(f"size is not a number: {valore!r}")
    if n < DIM_MIN or n > DIM_MAX:
        raise ValueError(f"size outside the allowed range {DIM_MIN}-{DIM_MAX}: {n}")
    return max(DIM_MIN, (n // 16) * 16)


def analizza_progresso(testo, passi_totali):
    """Turn whatever iris has written to stderr so far into 0.0-1.0.

    iris prints "  Step 1/4 " and then one letter per computed block
    (d, s, F), so counting the letters gives fine progress inside a step.
    """
    if not testo or passi_totali <= 0:
        return 0.0
    # there is a space between "Step 4/4" and the letters; [ \t]* rather
    # than \s* so it cannot run over into the next line
    passi = re.findall(r"Step (\d+)/(\d+)[ \t]*([dsF]*)", testo)
    if not passi:
        return 0.0
    ultimo, totale, blocchi = passi[-1]
    totale = int(totale) or passi_totali
    completati = int(ultimo) - 1
    # 10 blocks per step on the 4B: 5 double + 4 single + 1 final
    dentro = min(len(blocchi) / 10.0, 1.0)
    return min((completati + dentro) / totale, 1.0)


def nome_immagine_valido(nome):
    """True only for a plain file name with an image extension.

    Keeps GET /images/<name> from reaching outside the images folder.
    """
    if not nome or len(nome) > 200:
        return False
    if "/" in nome or "\\" in nome or ".." in nome or ":" in nome:
        return False
    return nome.lower().endswith((".png", ".jpg", ".jpeg"))


def leggi_catalogo(percorso=None):
    """Catalog rows, newest first. Broken lines are skipped.

    Reads as utf-8-sig: the .bat scripts write through PowerShell, which
    puts a BOM at the start of a new file and would otherwise make the
    first row unreadable.
    """
    percorso = Path(percorso) if percorso else CATALOGO
    if not percorso.exists():
        return []
    righe = []
    for riga in percorso.read_text(encoding="utf-8-sig").splitlines():
        riga = riga.strip()
        if not riga:
            continue
        try:
            righe.append(json.loads(riga))
        except json.JSONDecodeError:
            continue
    righe.reverse()
    return righe


def costruisci_prompt(soggetto, stile):
    """Join subject and style as "subject, style"."""
    parti = [p.strip() for p in (soggetto, stile) if p and p.strip()]
    return ", ".join(parti)


# ---------------------------------------------------------------------------
# Finding things instead of hardcoding them
# ---------------------------------------------------------------------------

def trova_iris(indicato=None):
    """Locate the iris binary, or return None.

    Looks next to this script, in an iris.c subdirectory, one level up,
    in the current directory, and finally on PATH.
    """
    if indicato:
        p = Path(indicato).expanduser().resolve()
        return p if p.exists() else None

    nomi = ["iris.exe", "iris"] if WINDOWS else ["iris"]
    cartelle = [BASE, BASE / "iris.c", BASE.parent / "iris.c",
                BASE.parent, Path.cwd(), Path.cwd() / "iris.c"]
    for cartella in cartelle:
        for nome in nomi:
            candidato = cartella / nome
            if candidato.is_file():
                return candidato.resolve()

    for nome in nomi:
        trovato = shutil.which(nome)
        if trovato:
            return Path(trovato)
    return None


def trova_modello(indicato=None, accanto_a=None):
    """Locate a model directory, or return None.

    A model directory is one containing model_index.json, so this works
    for flux-klein-* and zimage-* alike without naming them.
    """
    if indicato:
        p = Path(indicato).expanduser().resolve()
        return p if (p / "model_index.json").is_file() else None

    cartelle = [accanto_a, BASE, BASE / "iris.c", BASE.parent,
                BASE.parent / "iris.c", Path.cwd()]
    for cartella in cartelle:
        if not cartella or not cartella.is_dir():
            continue
        if (cartella / "model_index.json").is_file():
            return cartella.resolve()
        for figlio in sorted(cartella.iterdir()):
            if figlio.is_dir() and (figlio / "model_index.json").is_file():
                return figlio.resolve()
    return None


def thread_consigliati():
    """Half the logical CPUs, as a stand-in for the physical core count.

    On a 4-core/8-thread machine, 4 BLAS threads measured 19% faster than
    8: the cores already saturate the vector units, so hyperthreading
    only adds contention. Override with --threads if that is wrong for
    your CPU.
    """
    logici = os.cpu_count() or 2
    return max(1, logici // 2)


def cartella_dll_windows():
    """Directory holding the UCRT64 runtime DLLs on Windows, or None.

    A binary built under MSYS2 needs them on PATH. If none of the usual
    places exist we return None and change nothing: whoever built iris
    themselves probably has a working PATH already.
    """
    if not WINDOWS:
        return None
    for percorso in (r"C:\msys64\ucrt64\bin", r"C:\msys2\ucrt64\bin",
                     r"C:\msys64\mingw64\bin"):
        if Path(percorso).is_dir():
            return percorso
    return None


def configura(argomenti=None):
    """Read the command line, then fill in whatever was not given."""
    argomenti = list(sys.argv[1:] if argomenti is None else argomenti)

    def valore(flag):
        if flag in argomenti:
            i = argomenti.index(flag)
            if i + 1 < len(argomenti):
                return argomenti[i + 1]
        return None

    if "--help" in argomenti or "-h" in argomenti:
        print(__doc__)
        raise SystemExit(0)

    CFG["browser"] = "--no-browser" not in argomenti

    porta = valore("--port")
    if porta:
        try:
            CFG["port"] = int(porta)
        except ValueError:
            raise SystemExit(f"--port wants a number, got {porta!r}")

    thread = valore("--threads")
    if thread:
        try:
            CFG["threads"] = max(1, int(thread))
        except ValueError:
            raise SystemExit(f"--threads wants a number, got {thread!r}")
    else:
        CFG["threads"] = thread_consigliati()

    CFG["iris"] = trova_iris(valore("--iris"))
    if not CFG["iris"]:
        raise SystemExit(
            "Cannot find the iris binary.\n"
            "Build it from https://github.com/antirez/iris.c, put it next to\n"
            "this script (or in an iris.c subdirectory), or pass --iris PATH."
        )

    CFG["model"] = trova_modello(valore("--model"), accanto_a=CFG["iris"].parent)
    if not CFG["model"]:
        raise SystemExit(
            "Cannot find a model directory (one containing model_index.json).\n"
            "Download one with iris's download_model.py, or pass --model PATH."
        )


# ---------------------------------------------------------------------------
# Queue and worker
# ---------------------------------------------------------------------------
import http.server
import queue
import socketserver
import subprocess
import threading
import uuid
import webbrowser
from datetime import datetime


def _ambiente():
    env = os.environ.copy()
    dll = cartella_dll_windows()
    if dll and dll not in env.get("PATH", ""):
        env["PATH"] = dll + os.pathsep + env.get("PATH", "")
    env["OMP_NUM_THREADS"] = str(CFG["threads"])
    return env


class Coda:
    """A queue of generations served by a single worker thread.

    One at a time because iris already saturates the CPU: two in
    parallel would not finish sooner, they would fight each other.
    """

    def __init__(self):
        self._coda = queue.Queue()
        self._lock = threading.Lock()
        self._in_corso = None
        self._attesa = []
        self._errore = None
        self._worker = threading.Thread(target=self._cicla, daemon=True)
        self._worker.start()

    def aggiungi(self, richiesta):
        richiesta["id"] = uuid.uuid4().hex[:8]
        richiesta["stato"] = "in attesa"
        with self._lock:
            self._attesa.append(richiesta)
        self._coda.put(richiesta)
        return richiesta["id"]

    def in_corso(self):
        with self._lock:
            return dict(self._in_corso) if self._in_corso else None

    def in_attesa(self):
        with self._lock:
            return [dict(r) for r in self._attesa]

    def ultimo_errore(self):
        with self._lock:
            return self._errore

    def _cicla(self):
        while True:
            richiesta = self._coda.get()
            with self._lock:
                self._attesa = [r for r in self._attesa if r["id"] != richiesta["id"]]
                richiesta["stato"] = "in corso"
                richiesta["progresso"] = 0.0
                self._in_corso = richiesta
                self._errore = None
            try:
                self._esegui(richiesta)
            except Exception as e:  # the worker must never die
                with self._lock:
                    self._in_corso = None
                    self._errore = str(e)
                print(f"generation {richiesta['id']} failed: {e}")
            finally:
                self._coda.task_done()

    def _esegui(self, richiesta):
        avvio = datetime.now()
        nome = f"web_{avvio:%Y%m%d_%H%M%S}_s{richiesta['seed']}.png"
        destinazione = IMMAGINI / nome

        comando = [
            str(CFG["iris"]), "-d", str(CFG["model"]),
            "--blas-threads", str(CFG["threads"]),
            "--seed", str(richiesta["seed"]),
            "-p", richiesta["prompt"],
            "-W", str(richiesta["width"]), "-H", str(richiesta["height"]),
            "-o", str(destinazione),
        ]
        if richiesta.get("input"):
            comando[1:1] = ["-i", str(INPUT_DIR / richiesta["input"])]

        processo = subprocess.Popen(
            comando, cwd=str(CFG["iris"].parent), env=_ambiente(),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, errors="replace", bufsize=1,
        )

        raccolto = ""
        # One character at a time: iris prints blocks without a newline,
        # and read(n) in text mode would wait for n of them before
        # returning, making the progress bar jump. It is about forty
        # characters per image, so the cost is nil.
        while True:
            pezzo = processo.stderr.read(1)
            if not pezzo:
                break
            raccolto += pezzo
            with self._lock:
                richiesta["progresso"] = analizza_progresso(raccolto, 4)
        processo.wait()

        with self._lock:
            self._in_corso = None

        if processo.returncode != 0 or not destinazione.exists():
            coda_errore = raccolto.strip().splitlines()[-3:]
            raise RuntimeError("iris failed: " + " | ".join(coda_errore))

        riga = {
            "file": nome,
            "prompt": richiesta["prompt"],
            "seed": richiesta["seed"],
            "width": richiesta["width"],
            "height": richiesta["height"],
            "input": richiesta.get("input"),
            "date": avvio.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with CATALOGO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(riga, ensure_ascii=False) + "\n")


LAVORI = None  # created in avvia_server(), once configuration is known


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _stato_corrente():
    return {
        "in_corso": LAVORI.in_corso(),
        "in_attesa": LAVORI.in_attesa(),
        "ultimo_errore": LAVORI.ultimo_errore(),
        "immagini": leggi_catalogo(),
        "stili": list(STILI.keys()),
    }


class Handler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.1 so the connection is reused: the page polls once a second
    # and with 1.0 every reply closed the socket, dropping requests.
    # Safe because _invia always sends Content-Length.
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def _invia(self, codice, corpo, tipo="application/json; charset=utf-8"):
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        elif isinstance(corpo, str):
            corpo = corpo.encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        percorso = self.path.split("?")[0]

        if percorso in ("/", "/index.html"):
            pagina = WEB / "index.html"
            if not pagina.exists():
                return self._invia(500, "web/index.html not found",
                                   "text/plain; charset=utf-8")
            return self._invia(200, pagina.read_text(encoding="utf-8"),
                               "text/html; charset=utf-8")

        if percorso == "/api/stato":
            return self._invia(200, _stato_corrente())

        if percorso.startswith("/images/"):
            nome = percorso[len("/images/"):]
            if not nome_immagine_valido(nome):
                return self._invia(400, {"error": "bad file name"})
            for cartella in (IMMAGINI, INPUT_DIR):
                f = cartella / nome
                if f.exists():
                    tipo = "image/png" if nome.lower().endswith(".png") else "image/jpeg"
                    return self._invia(200, f.read_bytes(), tipo)
            return self._invia(404, {"error": "image not found"})

        self._invia(404, {"error": "not found"})

    def do_POST(self):
        percorso = self.path.split("?")[0]
        lunghezza = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(lunghezza) if lunghezza else b""

        if percorso == "/api/genera":
            try:
                dati = json.loads(corpo.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return self._invia(400, {"error": "invalid JSON"})

            soggetto = (dati.get("soggetto") or "").strip()
            stile = STILI.get(dati.get("stile", "nessuno"), "")
            if dati.get("stile") == "libero":
                stile = (dati.get("stile_libero") or "").strip()
            prompt = costruisci_prompt(soggetto, stile)
            if not prompt:
                return self._invia(400, {"error": "give at least a subject or a style"})

            try:
                larghezza = valida_dimensione(dati.get("width", 512))
                altezza = valida_dimensione(dati.get("height", 512))
            except ValueError as e:
                return self._invia(400, {"error": str(e)})

            seed = dati.get("seed")
            if seed in (None, ""):
                seed = uuid.uuid4().int % 2147483000
            else:
                try:
                    seed = int(seed)
                except (TypeError, ValueError):
                    return self._invia(400, {"error": "seed must be a number"})

            immagine_input = dati.get("input")
            if immagine_input and not nome_immagine_valido(immagine_input):
                return self._invia(400, {"error": "bad reference image"})

            id_lavoro = LAVORI.aggiungi({
                "prompt": prompt, "seed": seed,
                "width": larghezza, "height": altezza,
                "input": immagine_input,
            })
            return self._invia(200, {"id": id_lavoro})

        if percorso == "/api/carica":
            if not corpo:
                return self._invia(400, {"error": "no data"})
            if len(corpo) > 25 * 1024 * 1024:
                return self._invia(400, {"error": "image too large (over 25 MB)"})
            # sniffed from content, not from the extension: iris reads
            # only these two formats
            if corpo[:8] == b"\x89PNG\r\n\x1a\n":
                estensione = ".png"
            elif corpo[:2] == b"\xff\xd8":
                estensione = ".jpg"
            else:
                return self._invia(400, {"error": "PNG or JPEG only"})

            nome = f"in_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}{estensione}"
            (INPUT_DIR / nome).write_bytes(corpo)
            return self._invia(200, {"nome": nome})

        self._invia(404, {"error": "not found"})


class ServerLocale(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def apri_porta(preferita):
    """Bind the preferred port, or the next free one after it.

    Failing outright would be unhelpful: another program may already own
    that number, which is exactly what happened during development.
    """
    ultimo_errore = None
    for porta in range(preferita, preferita + PORTE_DA_PROVARE):
        try:
            return ServerLocale(("127.0.0.1", porta), Handler), porta
        except OSError as e:
            ultimo_errore = e
    raise SystemExit(
        f"No free port between {preferita} and {preferita + PORTE_DA_PROVARE - 1} "
        f"({ultimo_errore}). Try --port N."
    )


def avvia_server():
    global LAVORI
    configura()
    IMMAGINI.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    LAVORI = Coda()

    server, porta = apri_porta(CFG["port"])
    url = f"http://127.0.0.1:{porta}"

    # flush: Python buffers stdout when it is not a terminal, and these
    # lines are the only way to know which port was taken.
    print(f"iris-web on {url}", flush=True)
    print(f"  iris:    {CFG['iris']}", flush=True)
    print(f"  model:   {CFG['model'].name}", flush=True)
    print(f"  threads: {CFG['threads']}", flush=True)
    if porta != CFG["port"]:
        print(f"  (port {CFG['port']} was busy)", flush=True)
    print("Leave this window open. Ctrl-C to stop.", flush=True)

    if CFG["browser"]:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    avvia_server()
