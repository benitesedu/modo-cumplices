"""Servidor local do Modo Cúmplice. Execute com Python 3.8+."""
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import date
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_DATABASE = {
    "versao": 1,
    "jogo": "Modo Cúmplice",
    "tiposDeDia": {"briga": "Teve briga", "feliz": "Dia feliz", "quente": "Dia quente"},
    "participantes": {"eduardo": {"nome": "Eduardo"}, "jessica": {"nome": "Jéssica"}},
}


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


def supabase_request(path, method="GET", payload=None, prefer=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Accept": "application/json",
    }
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = prefer or "return=minimal"
        body = json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(SUPABASE_URL + "/rest/v1/" + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def supabase_database():
    days = supabase_request("dias?select=dia,marcacoes,envolvidos_na_briga,observacao&order=dia.asc")
    votes = supabase_request("votos?select=dia,participante,estrelas,comentario&order=dia.asc")
    database = dict(BASE_DATABASE)
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


def supabase_events():
    events = supabase_request("eventos_especiais?select=id,tipo,participante,data_inicio,data_fim,descricao&order=data_inicio.desc")
    items = supabase_request("eventos_itens?select=id,evento_id,data,observacao&order=data.asc")
    return [{
        "id": event["id"], "tipo": event["tipo"], "participante": event["participante"],
        "dataInicio": event["data_inicio"], "dataFim": event["data_fim"], "descricao": event["descricao"],
        "itens": [{"id": item["id"], "data": item["data"], "observacao": item["observacao"]}
                  for item in items if item["evento_id"] == event["id"]]
    } for event in events]


def save_event(event):
    start, end = event["dataInicio"], event["dataFim"]
    if event["tipo"] not in ("Viagem", "Passeio", "Acontecimento") or event["participante"] not in ("Eduardo", "Jéssica", "Ambos"):
        raise ValueError("Tipo ou participante inválido")
    if date.fromisoformat(start) > date.fromisoformat(end) or not event["descricao"].strip():
        raise ValueError("Período ou descrição inválida")
    for item in event["itens"]:
        if not item["observacao"].strip() or not date.fromisoformat(start) <= date.fromisoformat(item["data"]) <= date.fromisoformat(end):
            raise ValueError("Item fora do período ou sem observação")
    created = supabase_request("eventos_especiais", "POST", [{
        "tipo": event["tipo"], "participante": event["participante"], "data_inicio": start,
        "data_fim": end, "descricao": event["descricao"].strip()
    }], "return=representation")
    event_id = created[0]["id"]
    if event["itens"]:
        supabase_request("eventos_itens", "POST", [{"evento_id": event_id, "data": item["data"], "observacao": item["observacao"].strip()} for item in event["itens"]])
    return event_id


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
        if self.path == "/api/eventos":
            if not SUPABASE_URL or not SUPABASE_KEY:
                return self.reply(503, b'{"error":"Configure o arquivo .env com as credenciais do Supabase"}')
            try:
                body = json.dumps(supabase_events(), ensure_ascii=False).encode()
                return self.reply(200, body, source="supabase")
            except (OSError, ValueError, urllib.error.URLError) as error:
                return self.reply(502, json.dumps({"error": "Falha ao consultar eventos", "detail": str(error)}).encode())
        if self.path == "/api/dados":
            if not SUPABASE_URL or not SUPABASE_KEY:
                return self.reply(503, b'{"error":"Configure o arquivo .env com as credenciais do Supabase"}')
            try:
                data = supabase_database()
                raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
            except (OSError, ValueError, urllib.error.URLError) as error:
                return self.reply(502, json.dumps({"error": "Falha ao consultar Supabase", "detail": str(error)}).encode())
            self.reply(200, raw, revision(raw), "supabase")
        else:
            super().do_GET()

    def do_PUT(self):
        if self.path != "/api/dados":
            return self.reply(404)
        if not SUPABASE_URL or not SUPABASE_KEY:
            return self.reply(503, b'{"error":"Configure o arquivo .env com as credenciais do Supabase"}')
        try:
            current = supabase_database()
            current_raw = (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode()
            if self.headers.get("If-Match") != revision(current_raw):
                return self.reply(412)
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32000:
                return self.reply(400)
            change = json.loads(self.rfile.read(size))
            key, record = change["data"], change["registro"]
            if date.fromisoformat(key).isoformat() != key or not valid_record(record, current):
                return self.reply(400)
            save_supabase(key, record)
            updated = supabase_database()
            output = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode()
            return self.reply(200, b"{}", revision(output), "supabase")
        except (TypeError, ValueError, KeyError):
            return self.reply(400)
        except (OSError, urllib.error.URLError) as error:
            return self.reply(502, json.dumps({"error": "Falha ao salvar no Supabase", "detail": str(error)}).encode())

    def do_POST(self):
        if self.path != "/api/eventos":
            return self.reply(404)
        if not SUPABASE_URL or not SUPABASE_KEY:
            return self.reply(503, b'{"error":"Configure o arquivo .env com as credenciais do Supabase"}')
        try:
            size = int(self.headers.get("Content-Length", "0"))
            event = json.loads(self.rfile.read(size))
            event_id = save_event(event)
            return self.reply(201, json.dumps({"id": event_id}).encode(), source="supabase")
        except (TypeError, ValueError, KeyError) as error:
            return self.reply(400, json.dumps({"error": str(error)}).encode())
        except (OSError, urllib.error.URLError) as error:
            return self.reply(502, json.dumps({"error": "Falha ao salvar evento", "detail": str(error)}).encode())


if __name__ == "__main__":
    print("Modo Cúmplice em http://127.0.0.1:8000", flush=True)
    HTTPServer(("127.0.0.1", 8000), App).serve_forever()
