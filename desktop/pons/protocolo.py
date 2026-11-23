"""Protocolo do Pons (igual no PC e no Android).

Rede: o PC escuta HTTP na porta 47800 (ou a próxima livre) e anuncia a cada 2 s, por UDP broadcast na porta 47801,
{"app":"pons","v":1,"id":…,"nome":…,"porta":…}. O celular sempre é quem conecta.

Pareamento: o PC mostra um QR  pons://parear?h=IP1,IP2&p=PORTA&id=ID_PC&n=NOME&k=CHAVE  (CHAVE = 32 bytes em
base64url). Quem leu o QR tem a chave; a partir daí tudo vai cifrado com AES-256-GCM e essa chave.

Mensagem cifrada: base64url( nonce(12) || cifrado+tag ), com o texto em JSON que sempre leva "ts" (ms) para
recusar repetição antiga. Pedaços de arquivo vão em binário: nonce(12) || cifrado+tag, com AAD = "id:indice".
Cabeçalho X-Pons-Disp: id do aparelho pareado (o PC escolhe a chave por ele).
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, quote, urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSAO = 1
PORTA = 47800
PORTA_UDP = 47801
PEDACO = 2 * 1024 * 1024          # tamanho de cada parte de arquivo (antes de cifrar)
JANELA_MS = 10 * 60 * 1000        # mensagens com relógio muito diferente são recusadas


class ErroProtocolo(Exception):
    pass


def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64d(s: str) -> bytes:
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def nova_chave() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def cifrar(chave: bytes, dados: bytes, aad: bytes | None = None) -> bytes:
    n = os.urandom(12)
    return n + AESGCM(chave).encrypt(n, dados, aad)


def decifrar(chave: bytes, pacote: bytes, aad: bytes | None = None) -> bytes:
    if len(pacote) < 28:
        raise ErroProtocolo("pacote curto")
    try:
        return AESGCM(chave).decrypt(pacote[:12], pacote[12:], aad)
    except Exception:  # noqa: BLE001
        raise ErroProtocolo("chave errada ou dados alterados")


def selar(chave: bytes, obj: dict) -> str:
    obj = dict(obj, ts=int(time.time() * 1000))
    return b64e(cifrar(chave, json.dumps(obj, ensure_ascii=False).encode()))


def abrir(chave: bytes, texto: str, verificar_tempo=True) -> dict:
    obj = json.loads(decifrar(chave, b64d(texto)).decode())
    if verificar_tempo and abs(int(time.time() * 1000) - int(obj.get("ts", 0))) > JANELA_MS:
        raise ErroProtocolo("relógio do aparelho muito diferente do PC")
    return obj


def aad_parte(upload_id: str, i: int) -> bytes:
    return f"{upload_id}:{i}".encode()


# ------------------------------------------------------------------ QR de pareamento
def url_pareamento(ips: list[str], porta: int, id_pc: str, nome: str, chave: bytes) -> str:
    return (f"pons://parear?h={','.join(ips)}&p={porta}&id={id_pc}&n={quote(nome)}&k={b64e(chave)}")


def ler_url_pareamento(url: str) -> dict:
    u = urlparse(url)
    if u.scheme != "pons" or u.netloc != "parear":
        raise ErroProtocolo("não é um QR do Pons")
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    return {"ips": q["h"].split(","), "porta": int(q["p"]), "id": q["id"], "nome": q.get("n", "PC"),
            "chave": b64d(q["k"])}


# ------------------------------------------------------------------ códigos lidos pela câmera
BASE_ANTIGA = date(1997, 10, 7)
BASE_NOVA = date(2025, 2, 22)       # fator 1000 = 22/02/2025 (o fator recomeçou depois de 9999)
BANCOS = {"001": "Banco do Brasil", "033": "Santander", "077": "Inter", "104": "Caixa", "136": "Unicred",
          "208": "BTG Pactual", "212": "Banco Original", "237": "Bradesco", "260": "Nubank", "290": "PagBank",
          "336": "C6 Bank", "341": "Itaú", "380": "PicPay", "422": "Safra", "623": "Pan", "655": "Votorantim",
          "748": "Sicredi", "756": "Sicoob", "323": "Mercado Pago", "403": "Cora", "197": "Stone", "746": "Modal"}


def _mod10(num: str) -> int:
    soma, peso = 0, 2
    for c in reversed(num):
        x = int(c) * peso
        soma += x // 10 + x % 10
        peso = 1 if peso == 2 else 2
    return (10 - soma % 10) % 10


def _mod11_boleto(num: str) -> int:
    soma, peso = 0, 2
    for c in reversed(num):
        soma += int(c) * peso
        peso = 2 if peso == 9 else peso + 1
    r = 11 - soma % 11
    return 1 if r in (0, 10, 11) else r


def vencimento_por_fator(fator: int, hoje: date | None = None) -> date | None:
    if fator == 0:
        return None
    hoje = hoje or date.today()
    a = BASE_ANTIGA + timedelta(days=fator)
    b = BASE_NOVA + timedelta(days=fator - 1000) if fator >= 1000 else None
    if b is None:
        return a
    return min((a, b), key=lambda d: abs((d - hoje).days))


def barras_para_linha(barras: str) -> str:
    """Código de barras de 44 dígitos (boleto bancário) → linha digitável de 47 dígitos."""
    b = barras
    c1 = b[0:4] + b[19:24]
    c2 = b[24:34]
    c3 = b[34:44]
    return (c1 + str(_mod10(c1)) + c2 + str(_mod10(c2)) + c3 + str(_mod10(c3)) + b[4] + b[5:19])


def linha_para_barras(linha: str) -> str:
    d = linha
    return d[0:4] + d[32] + d[33:47] + d[4:9] + d[10:20] + d[21:31]


def fmt_linha(linha: str) -> str:
    d = linha
    if len(d) == 47:
        return f"{d[0:5]}.{d[5:10]} {d[10:15]}.{d[15:21]} {d[21:26]}.{d[26:32]} {d[32]} {d[33:47]}"
    if len(d) == 48:
        return " ".join(d[i:i + 12] for i in range(0, 48, 12))
    return d


def ler_codigo(texto: str, formato: str = "", hoje: date | None = None) -> dict:
    """Interpreta o que a câmera leu: boleto (barras ou linha), conta de consumo, chave/QR de NF-e, PIX ou texto."""
    t = (texto or "").strip()
    dig = re.sub(r"\D", "", t)
    # boleto bancário
    if len(dig) in (44, 47) and not dig.startswith("8"):
        barras = dig if len(dig) == 44 else linha_para_barras(dig)
        if _mod11_boleto(barras[:4] + barras[5:]) == int(barras[4]):
            linha = barras_para_linha(barras)
            valor = int(barras[9:19]) / 100
            venc = vencimento_por_fator(int(barras[5:9]), hoje)
            return {"tipo": "boleto", "linha": linha, "linha_fmt": fmt_linha(linha), "valor": valor,
                    "vencimento": venc.isoformat() if venc else None, "banco": BANCOS.get(barras[:3], f"Banco {barras[:3]}"),
                    "copiar": linha}
    # conta de consumo / tributo (começa com 8): 44 dígitos no código de barras ou 48 na linha
    if dig.startswith("8") and len(dig) in (44, 48):
        barras = dig if len(dig) == 44 else "".join(dig[i:i + 11] for i in range(0, 48, 12))
        valor = int(barras[4:15]) / 100 if barras[2] in "68" else None
        if len(dig) == 44:
            mod = _mod10 if barras[2] in "67" else None
            blocos = [barras[i:i + 11] for i in range(0, 44, 11)]
            linha = "".join(b + str((mod or _mod10)(b)) for b in blocos)
        else:
            linha = dig
        return {"tipo": "conta", "linha": linha, "linha_fmt": fmt_linha(linha), "valor": valor, "copiar": linha}
    # chave de NF-e / CT-e (44 dígitos) ou QR da NFC-e com a chave
    m = re.search(r"(?<!\d)(\d{44})(?!\d)", t.replace(" ", ""))
    if m or ("nfce" in t.lower() or "sefaz" in t.lower()):
        chave = m.group(1) if m else None
        if chave and chave[20:22] in ("55", "57", "65", "67", "58"):
            modelo = {"55": "NF-e", "57": "CT-e", "65": "NFC-e", "67": "CT-e OS", "58": "MDF-e"}[chave[20:22]]
            cnpj = chave[6:20]
            return {"tipo": "nfe", "modelo": modelo, "chave": chave,
                    "chave_fmt": " ".join(chave[i:i + 4] for i in range(0, 44, 4)),
                    "emitente": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
                    "numero": str(int(chave[25:34])), "serie": str(int(chave[22:25])),
                    "emissao": f"{chave[4:6]}/20{chave[2:4]}", "url": t if t.lower().startswith("http") else None,
                    "copiar": chave}
    # PIX copia e cola (EMV: campos id(2) + tamanho(2) + valor)
    if t.startswith("000201") and "br.gov.bcb.pix" in t.lower():
        campos, i = {}, 0
        while i + 4 <= len(t):
            cid, n = t[i:i + 2], t[i + 2:i + 4]
            if not n.isdigit():
                break
            campos[cid] = t[i + 4:i + 4 + int(n)]
            i += 4 + int(n)
        try:
            valor = float(campos["54"]) if "54" in campos else None
        except ValueError:
            valor = None
        return {"tipo": "pix", "valor": valor, "recebedor": campos.get("59"), "cidade": campos.get("60"), "copiar": t}
    if t.lower().startswith(("http://", "https://")):
        return {"tipo": "link", "url": t, "copiar": t}
    return {"tipo": "texto", "texto": t, "copiar": t}


__all__ = ["VERSAO", "PORTA", "PORTA_UDP", "PEDACO", "ErroProtocolo", "b64e", "b64d", "nova_chave", "cifrar",
           "decifrar", "selar", "abrir", "aad_parte", "url_pareamento", "ler_url_pareamento", "ler_codigo",
           "barras_para_linha", "linha_para_barras", "fmt_linha", "vencimento_por_fator"]
