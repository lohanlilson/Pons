"""Cliente do protocolo (o mesmo que o app Android faz). Usado nos testes e como referência."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import uuid

from . import protocolo as P


class Cliente:
    def __init__(self, qr: str | None = None, id_disp: str | None = None, nome="Celular de teste"):
        self.id = id_disp or uuid.uuid4().hex[:16]
        self.nome = nome
        self.base = None
        self.chave = None
        self.ultimo = 0
        if qr:
            self.info = P.ler_url_pareamento(qr)
            self.chave = self.info["chave"]
            self.base = f"http://{self.info['ips'][0]}:{self.info['porta']}"

    def _post(self, caminho, corpo: bytes, timeout=40) -> bytes:
        req = urllib.request.Request(self.base + caminho, data=corpo, method="POST",
                                     headers={"X-Pons-Disp": self.id, "Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def _get(self, caminho, timeout=40) -> bytes:
        req = urllib.request.Request(self.base + caminho, headers={"X-Pons-Disp": self.id})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def _msg(self, caminho, obj, timeout=40) -> dict:
        return P.abrir(self.chave, self._post(caminho, P.selar(self.chave, obj).encode(), timeout).decode())

    def parear(self) -> dict:
        return self._msg("/v1/parear", {"nome": self.nome, "modelo": "teste"})

    def texto(self, t):
        return self._msg("/v1/msg", {"tipo": "texto", "texto": t})

    def codigo(self, valor, formato=""):
        return self._msg("/v1/msg", {"tipo": "codigo", "valor": valor, "formato": formato})

    def notificacao(self, app, titulo, texto):
        return self._msg("/v1/msg", {"tipo": "notificacao", "app": app, "titulo": titulo, "texto": texto})

    def enviar_arquivo(self, caminho, tipo="arquivo", nome=None) -> dict:
        tam = os.path.getsize(caminho)
        r = self._msg("/v1/up/inicio", {"nome": nome or os.path.basename(caminho), "tamanho": tam, "tipo": tipo})
        up = r["id"]
        h = hashlib.sha256()
        with open(caminho, "rb") as f:
            i = 0
            while True:
                b = f.read(P.PEDACO)
                if not b and i:
                    break
                h.update(b)
                P.abrir(self.chave, self._post(f"/v1/up/parte?id={up}&i={i}",
                                               P.cifrar(self.chave, b, P.aad_parte(up, i))).decode())
                i += 1
                if len(b) < P.PEDACO:
                    break
        return self._msg("/v1/up/fim", {"id": up, "sha256": h.hexdigest()})

    def eventos(self, espera=1.0) -> list[dict]:
        r = self._msg("/v1/eventos", {"desde": self.ultimo, "espera": espera}, timeout=espera + 15)
        self.ultimo = r["ultimo"]
        return r["eventos"]

    def baixar(self, ev: dict, destino: str) -> str:
        h = hashlib.sha256()
        with open(destino, "wb") as f:
            for i in range(ev["partes"]):
                b = P.decifrar(self.chave, self._get(f"/v1/baixar?id={ev['id']}&i={i}"), P.aad_parte(ev["id"], i))
                h.update(b)
                f.write(b)
        if h.hexdigest() != ev["sha256"]:
            raise P.ErroProtocolo("arquivo corrompido")
        return destino

    def ola(self) -> dict:
        return json.loads(self._get("/v1/ola"))


__all__ = ["Cliente"]
