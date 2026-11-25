"""Servidor local do Modo Cúmplice. Execute com Python 3.8+."""
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from datetime import date
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "dados.json"


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def supabase_request(path, method="GET", payload=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Accept": "application/json",
    }
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal"
        body = json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(SUPABASE_URL + "/rest/v1/" + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def supabase_database():
    days = supabase_request("dias?select=dia,marcacoes,envolvidos_na_briga,observacao&order=dia.asc")
    votes = supabase_request("votos?select=dia,participante,estrelas,comentario&order=dia.asc")
    database = json.loads(DATABASE.read_text(encoding="utf-8"))
    database["registros"] = {
        row["dia"]: {
            "marcacoes": row["marcacoes"],
            "envolvidosNaBriga": row["envolvidos_na_briga"],
            "observacao": row["observacao"],
            "votos": {"eduardo": None, "jessica": None},
        }
        for row in days
    }
    for vote in votes:
        if vote["dia"] in database["registros"]:
            database["registros"][vote["dia"]]["votos"][vote["participante"]] = {
                "estrelas": vote["estrelas"], "comentario": vote["comentario"]
            }
    return database


def save_supabase(key, record):
    supabase_request("dias?on_conflict=dia", "POST", [{
        "dia": key,
        "marcacoes": record["marcacoes"],
        "envolvidos_na_briga": record["envolvidosNaBriga"],
        "observacao": record["observacao"],
    }])
    supabase_request("votos?dia=eq." + key, "DELETE")
    votes = [
        {"dia": key, "participante": participant, "estrelas": vote["estrelas"], "comentario": vote["comentario"]}
        for participant, vote in record["votos"].items() if vote
    ]
    if votes:
        supabase_request("votos", "POST", votes)


def revision(raw):
    return '"' + hashlib.sha256(raw).hexdigest() + '"'


def valid_record(record, db):
    marks = record["marcacoes"]
    votes = record["votos"]
    return (
        isinstance(marks, list) and bool(marks)
        and all(mark in db["tiposDeDia"] for mark in marks)
        and isinstance(record["observacao"], str)
        and record["envolvidosNaBriga"] in (None, "Os dois", "Eduardo", "Jéssica")
        and set(votes) == set(db["participantes"])
        and all(v is None or (type(v["estrelas"]) is int and 1 <= v["estrelas"] <= 5
                              and isinstance(v["comentario"], str)) for v in votes.values())
    )


class App(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "dist"), **kwargs)

    def reply(self, code, body=b"", etag=None, source=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if etag:
            self.send_header("ETag", etag)
        if source:
            self.send_header("X-Data-Source", source)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/dados.json":
            try:
                data = supabase_database() if SUPABASE_URL and SUPABASE_KEY else json.loads(DATABASE.read_text(encoding="utf-8"))
                raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
            except (OSError, ValueError, urllib.error.URLError) as error:
                return self.reply(502, json.dumps({"error": "Falha ao consultar Supabase", "detail": str(error)}).encode())
            self.reply(200, raw, revision(raw), "supabase" if SUPABASE_URL and SUPABASE_KEY else "local-json")
        else:
            super().do_GET()

    def do_PUT(self):
        if self.path != "/dados.json":
            return self.reply(404)
        try:
            raw = DATABASE.read_bytes()
        except OSError:
            return self.reply(500)
        if self.headers.get("If-Match") != revision(raw):
            if SUPABASE_URL and SUPABASE_KEY:
                try:
                    current = supabase_database()
                    current_raw = (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode()
                    if self.headers.get("If-Match") != revision(current_raw):
                        return self.reply(412)
                    raw = current_raw
                except (OSError, ValueError, urllib.error.URLError) as error:
                    return self.reply(502, json.dumps({"error": "Falha ao consultar Supabase", "detail": str(error)}).encode())
            else:
                return self.reply(412)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32000:
                return self.reply(400)
            change = json.loads(self.rfile.read(size))
            key, record = change["data"], change["registro"]
            db = json.loads(raw)
            if date.fromisoformat(key).isoformat() != key or not valid_record(record, db):
                return self.reply(400)
            if SUPABASE_URL and SUPABASE_KEY:
                save_supabase(key, record)
                current = supabase_database()
                output = (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode()
                return self.reply(200, b"{}", revision(output))
            db["registros"][key] = record
            output = (json.dumps(db, ensure_ascii=False, indent=2) + "\n").encode()
        except (TypeError, ValueError, KeyError):
            return self.reply(400)
        except (OSError, urllib.error.URLError) as error:
            return self.reply(502, json.dumps({"error": "Falha ao salvar no Supabase", "detail": str(error)}).encode())
        with tempfile.NamedTemporaryFile(dir=ROOT, delete=False) as temp:
            temp.write(output)
            temp.flush()
            os.fsync(temp.fileno())
        try:
            os.replace(temp.name, DATABASE)
        finally:
            Path(temp.name).unlink(missing_ok=True)
        self.reply(200, b"{}", revision(output))


if __name__ == "__main__":
    print("Modo Cúmplice em http://127.0.0.1:8000", flush=True)
    HTTPServer(("127.0.0.1", 8000), App).serve_forever()
