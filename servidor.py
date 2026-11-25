"""Servidor local do Modo Cúmplice. Execute com Python 3.8+."""
import hashlib
import json
import os
import tempfile
from datetime import date
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "dados.json"


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

    def reply(self, code, body=b"", etag=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/dados.json":
            raw = DATABASE.read_bytes()
            self.reply(200, raw, revision(raw))
        else:
            super().do_GET()

    def do_PUT(self):
        if self.path != "/dados.json":
            return self.reply(404)
        raw = DATABASE.read_bytes()
        if self.headers.get("If-Match") != revision(raw):
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
            db["registros"][key] = record
            output = (json.dumps(db, ensure_ascii=False, indent=2) + "\n").encode()
        except (TypeError, ValueError, KeyError):
            return self.reply(400)
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
