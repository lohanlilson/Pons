"""Servidor do Pons no PC: recebe o celular, guarda os aparelhos pareados e entrega o que vai para o celular."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, Signal

from . import __version__, pasta_dados
from . import protocolo as P

LIMITE_CORPO = P.PEDACO + 4096


def ips_locais() -> list[str]:
    """Endereços IPv4 desta máquina na rede local (o principal primeiro)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


class Aparelho:
    def __init__(self, id_, nome, chave: bytes, modelo=""):
        self.id = id_
        self.nome = nome
        self.chave = chave
        self.modelo = modelo
        self.visto = 0.0

    @property
    def conectado(self):
        return time.time() - self.visto < 45

    def dados(self):
        return {"id": self.id, "nome": self.nome, "modelo": self.modelo, "chave": P.b64e(self.chave)}


class Sinais(QObject):
    pareado = Signal(str)                    # nome do aparelho
    texto = Signal(str, str)                 # aparelho, texto
    codigo = Signal(str, dict)               # aparelho, info (protocolo.ler_codigo)
    notificacao = Signal(str, dict)          # aparelho, {app, titulo, texto}
    arquivo = Signal(str, str, str)          # aparelho, caminho, tipo (arquivo | scan)
    progresso = Signal(str, float)           # nome do arquivo, 0–1
    estado = Signal()                        # conexão mudou


class Servidor:
    def __init__(self, nome_pc: str | None = None, pasta_recebidos: str | None = None):
        self.sinais = Sinais()
        self.nome_pc = nome_pc or socket.gethostname()
        self.pasta_recebidos = pasta_recebidos or os.path.join(os.path.expanduser("~"), "Downloads", "Pons")
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._arq_aparelhos = os.path.join(pasta_dados(), "aparelhos.json")
        self.id_pc, self.aparelhos = self._carregar()
        self._pendente: tuple[bytes, float] | None = None       # chave do QR mostrado agora, validade
        self._eventos: dict[str, list] = {}                      # aparelho → [evento]
        self._seq = 0
        self._uploads: dict[str, dict] = {}
        self._saidas: dict[str, dict] = {}                       # id → {caminho, tamanho, partes}
        self.httpd = None
        self.porta = None
        self._parar = threading.Event()

    # ------------------------------------------------------------------ aparelhos
    def _carregar(self):
        try:
            d = json.load(open(self._arq_aparelhos, encoding="utf-8"))
            aps = {a["id"]: Aparelho(a["id"], a["nome"], P.b64d(a["chave"]), a.get("modelo", "")) for a in d.get("aparelhos", [])}
            return d.get("id_pc") or uuid.uuid4().hex[:16], aps
        except Exception:  # noqa: BLE001
            return uuid.uuid4().hex[:16], {}

    def _salvar(self):
        with self._lock:
            d = {"id_pc": self.id_pc, "aparelhos": [a.dados() for a in self.aparelhos.values()]}
        tmp = self._arq_aparelhos + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, self._arq_aparelhos)

    def esquecer(self, id_):
        with self._lock:
            self.aparelhos.pop(id_, None)
        self._salvar()
        self.sinais.estado.emit()

    def qr_pareamento(self) -> str:
        """Gera uma chave nova (vale 10 minutos) e devolve o texto do QR."""
        chave = P.nova_chave()
        with self._lock:
            self._pendente = (chave, time.time() + 600)
        return P.url_pareamento(ips_locais(), self.porta or P.PORTA, self.id_pc, self.nome_pc, chave)

    def conectados(self) -> list[Aparelho]:
        with self._lock:
            return [a for a in self.aparelhos.values() if a.conectado]

    # ------------------------------------------------------------------ para o celular
    def _evento(self, ev: dict, para: str | None = None):
        with self._cond:
            self._seq += 1
            ev = dict(ev, n=self._seq)
            alvos = [para] if para else list(self.aparelhos)
            for a in alvos:
                fila = self._eventos.setdefault(a, [])
                fila.append(ev)
                del fila[:-200]
            self._cond.notify_all()
        return ev

    def enviar_texto(self, texto: str, para: str | None = None):
        return self._evento({"tipo": "texto", "texto": texto}, para)

    def enviar_arquivo(self, caminho: str, para: str | None = None):
        tam = os.path.getsize(caminho)
        h = hashlib.sha256()
        with open(caminho, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        id_ = uuid.uuid4().hex
        partes = max(1, -(-tam // P.PEDACO))
        with self._lock:
            self._saidas[id_] = {"caminho": caminho, "tamanho": tam, "partes": partes}
        return self._evento({"tipo": "arquivo", "id": id_, "nome": os.path.basename(caminho), "tamanho": tam,
                             "partes": partes, "sha256": h.hexdigest()}, para)

    def tocar(self, para: str | None = None):
        """Faz o celular tocar (para achar o celular)."""
        return self._evento({"tipo": "tocar"}, para)

    # ------------------------------------------------------------------ rede
    def iniciar(self, porta_inicial=P.PORTA) -> int:
        srv = self
        for porta in range(porta_inicial, porta_inicial + 15):
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", porta), _criar_handler(srv))
                self.porta = porta
                break
            except OSError:
                continue
        if not self.httpd:
            raise OSError("nenhuma porta livre para o Pons")
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._anunciar, daemon=True).start()
        threading.Thread(target=self._vigiar, daemon=True).start()
        return self.porta

    def parar(self):
        self._parar.set()
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        with self._cond:
            self._cond.notify_all()

    def _anunciar(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not self._parar.is_set():
            msg = json.dumps({"app": "pons", "v": P.VERSAO, "id": self.id_pc, "nome": self.nome_pc,
                              "porta": self.porta}).encode()
            for destino in ("255.255.255.255",) + tuple(ip.rsplit(".", 1)[0] + ".255" for ip in ips_locais()):
                try:
                    s.sendto(msg, (destino, P.PORTA_UDP))
                except OSError:
                    pass
            self._parar.wait(2)

    def _vigiar(self):
        antes = set()
        while not self._parar.wait(5):
            agora = {a.id for a in self.conectados()}
            if agora != antes:
                antes = agora
                self.sinais.estado.emit()

    # ------------------------------------------------------------------ tratamento (chamado pelo handler)
    def aparelho(self, id_) -> Aparelho:
        with self._lock:
            a = self.aparelhos.get(id_ or "")
        if not a:
            raise P.ErroProtocolo("aparelho não pareado")
        mudou = not a.conectado
        a.visto = time.time()
        if mudou:
            self.sinais.estado.emit()
        return a

    def parear(self, id_disp: str, corpo: str) -> str:
        with self._lock:
            pend = self._pendente
        if not pend or pend[1] < time.time():
            raise P.ErroProtocolo("o QR expirou: mostre um novo no computador")
        info = P.abrir(pend[0], corpo)
        ap = Aparelho(id_disp, info.get("nome") or "Celular", pend[0], info.get("modelo", ""))
        ap.visto = time.time()
        with self._lock:
            self.aparelhos[id_disp] = ap
            self._pendente = None
            self._eventos.setdefault(id_disp, [])
        self._salvar()
        self.sinais.pareado.emit(ap.nome)
        self.sinais.estado.emit()
        return P.selar(ap.chave, {"ok": True, "id_pc": self.id_pc, "nome_pc": self.nome_pc, "versao": __version__})

    def mensagem(self, ap: Aparelho, corpo: str) -> str:
        m = P.abrir(ap.chave, corpo)
        t = m.get("tipo")
        if t == "texto":
            self.sinais.texto.emit(ap.nome, m.get("texto", ""))
        elif t == "codigo":
            info = P.ler_codigo(m.get("valor", ""), m.get("formato", ""))
            self.sinais.codigo.emit(ap.nome, info)
        elif t == "notificacao":
            self.sinais.notificacao.emit(ap.nome, {k: m.get(k, "") for k in ("app", "titulo", "texto")})
        elif t == "sair":
            self.esquecer(ap.id)
        elif t == "nome":
            ap.nome = m.get("nome") or ap.nome
            self._salvar()
            self.sinais.estado.emit()
        return P.selar(ap.chave, {"ok": True})

    def eventos(self, ap: Aparelho, corpo: str) -> str:
        m = P.abrir(ap.chave, corpo)
        desde = int(m.get("desde", 0))
        espera = min(float(m.get("espera", 25)), 30)
        fim = time.time() + espera
        with self._cond:
            while True:
                fila = [e for e in self._eventos.get(ap.id, []) if e["n"] > desde]
                if fila or self._parar.is_set() or time.time() >= fim:
                    break
                self._cond.wait(min(1.0, fim - time.time()))
            # o que já foi entregue sai da fila
            self._eventos[ap.id] = [e for e in self._eventos.get(ap.id, []) if e["n"] > desde]
        ap.visto = time.time()
        return P.selar(ap.chave, {"eventos": fila, "ultimo": max([desde] + [e["n"] for e in fila])})

    def upload_inicio(self, ap: Aparelho, corpo: str) -> str:
        m = P.abrir(ap.chave, corpo)
        nome = os.path.basename(m.get("nome") or "arquivo").replace("\\", "_").strip(". ") or "arquivo"
        os.makedirs(self.pasta_recebidos, exist_ok=True)
        destino = _nome_livre(os.path.join(self.pasta_recebidos, nome))
        id_ = uuid.uuid4().hex
        with self._lock:
            self._uploads[id_] = {"ap": ap.id, "destino": destino, "parcial": destino + ".pons-parte",
                                  "tamanho": int(m.get("tamanho", 0)), "recebido": 0, "proxima": 0,
                                  "tipo": m.get("tipo", "arquivo"), "nome": nome}
        open(destino + ".pons-parte", "wb").close()
        return P.selar(ap.chave, {"id": id_})

    def upload_parte(self, ap: Aparelho, id_: str, i: int, dados: bytes) -> str:
        with self._lock:
            up = self._uploads.get(id_)
        if not up or up["ap"] != ap.id:
            raise P.ErroProtocolo("envio desconhecido")
        if i != up["proxima"]:
            if i < up["proxima"]:                      # repetição (o celular reenviou): ignora
                return P.selar(ap.chave, {"ok": True})
            raise P.ErroProtocolo(f"parte fora de ordem (esperada {up['proxima']})")
        claro = P.decifrar(ap.chave, dados, P.aad_parte(id_, i))
        with open(up["parcial"], "ab") as f:
            f.write(claro)
        up["recebido"] += len(claro)
        up["proxima"] += 1
        if up["tamanho"]:
            self.sinais.progresso.emit(up["nome"], up["recebido"] / up["tamanho"])
        return P.selar(ap.chave, {"ok": True})

    def upload_fim(self, ap: Aparelho, corpo: str) -> str:
        m = P.abrir(ap.chave, corpo)
        with self._lock:
            up = self._uploads.pop(m.get("id", ""), None)
        if not up or up["ap"] != ap.id:
            raise P.ErroProtocolo("envio desconhecido")
        h = hashlib.sha256()
        with open(up["parcial"], "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        if m.get("sha256") and h.hexdigest() != m["sha256"]:
            os.remove(up["parcial"])
            raise P.ErroProtocolo("o arquivo chegou diferente (tente de novo)")
        os.replace(up["parcial"], up["destino"])
        self.sinais.arquivo.emit(ap.nome, up["destino"], up["tipo"])
        return P.selar(ap.chave, {"ok": True, "nome": os.path.basename(up["destino"])})

    def baixar(self, ap: Aparelho, id_: str, i: int) -> bytes:
        with self._lock:
            s = self._saidas.get(id_)
        if not s:
            raise P.ErroProtocolo("arquivo não disponível")
        with open(s["caminho"], "rb") as f:
            f.seek(i * P.PEDACO)
            dados = f.read(P.PEDACO)
        if i == s["partes"] - 1:
            nome = os.path.basename(s["caminho"])
            self.sinais.progresso.emit(nome, 1.0)
        return P.cifrar(ap.chave, dados, P.aad_parte(id_, i))


def _nome_livre(c):
    if not os.path.exists(c):
        return c
    base, ext = os.path.splitext(c)
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def _criar_handler(srv: Servidor):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Pons"

        def log_message(self, *a):
            pass

        def _responder(self, codigo, corpo: bytes, tipo="text/plain"):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _corpo(self) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n > LIMITE_CORPO:
                raise P.ErroProtocolo("corpo grande demais")
            return self.rfile.read(n)

        def _tratar(self, metodo):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            disp = self.headers.get("X-Pons-Disp", "")
            try:
                if u.path == "/v1/ola":
                    self._responder(200, json.dumps({"app": "pons", "v": P.VERSAO, "id": srv.id_pc,
                                                     "nome": srv.nome_pc}).encode(), "application/json")
                    return
                if u.path == "/v1/parear" and metodo == "POST":
                    self._responder(200, srv.parear(disp, self._corpo().decode()).encode())
                    return
                ap = srv.aparelho(disp)
                if metodo == "POST" and u.path == "/v1/msg":
                    r = srv.mensagem(ap, self._corpo().decode())
                elif metodo == "POST" and u.path == "/v1/eventos":
                    r = srv.eventos(ap, self._corpo().decode())
                elif metodo == "POST" and u.path == "/v1/up/inicio":
                    r = srv.upload_inicio(ap, self._corpo().decode())
                elif metodo == "POST" and u.path == "/v1/up/parte":
                    r = srv.upload_parte(ap, q.get("id", ""), int(q.get("i", -1)), self._corpo())
                elif metodo == "POST" and u.path == "/v1/up/fim":
                    r = srv.upload_fim(ap, self._corpo().decode())
                elif metodo == "GET" and u.path == "/v1/baixar":
                    self._responder(200, srv.baixar(ap, q.get("id", ""), int(q.get("i", 0))), "application/octet-stream")
                    return
                else:
                    self._responder(404, b"nao encontrado")
                    return
                self._responder(200, r.encode())
            except P.ErroProtocolo as e:
                self._responder(403, str(e).encode("utf-8"))
            except (ValueError, KeyError) as e:
                self._responder(400, f"pedido inválido: {e}".encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            self._tratar("GET")

        def do_POST(self):
            self._tratar("POST")
    return H


__all__ = ["Servidor", "Aparelho", "ips_locais"]
