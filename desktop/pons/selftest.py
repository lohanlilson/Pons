"""Autoteste: Pons.exe --selftest saida.txt (simula um celular na própria máquina)."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import traceback


def executar(argv):
    i = argv.index("--selftest")
    saida = argv[i + 1] if len(argv) > i + 1 else None
    linhas = []

    def log(msg):
        linhas.append(msg)
        if sys.stdout:
            print(msg, flush=True)
        if saida:
            with open(saida, "w", encoding="utf-8") as f:
                f.write("\n".join(linhas) + "\n")

    os.environ.setdefault("LOCALAPPDATA", tempfile.mkdtemp(prefix="pons-teste-"))
    falhas = 0
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(argv[:1])
        from . import __version__
        log(f"Pons {__version__} — autoteste ({sys.platform}, Python {sys.version.split()[0]})")
        for t in (t_protocolo, t_codigos, t_ponta_a_ponta):
            try:
                falhas += t(log, app)
            except Exception:  # noqa: BLE001
                falhas += 1
                log(f"ERRO {t.__name__}:\n" + traceback.format_exc())
    except Exception:  # noqa: BLE001
        falhas += 1
        log("ERRO geral:\n" + traceback.format_exc())
    log(f"RESULTADO: {'tudo certo' if not falhas else f'{falhas} falha(s)'}")
    codigo = 1 if falhas else 0
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.TerminateProcess(ctypes.c_void_p(k.GetCurrentProcess()), codigo)
    os._exit(codigo)


def ok(log, cond, msg):
    log(("OK   " if cond else "ERRO ") + msg)
    return 0 if cond else 1


def t_protocolo(log, app):
    from . import protocolo as P
    k = P.nova_chave()
    falhas = ok(log, P.abrir(k, P.selar(k, {"a": "ç"}))["a"] == "ç", "mensagem cifrada vai e volta")
    try:
        P.abrir(P.nova_chave(), P.selar(k, {"a": 1}))
        falhas += ok(log, False, "chave errada é recusada")
    except P.ErroProtocolo:
        falhas += ok(log, True, "chave errada é recusada")
    pac = bytearray(P.cifrar(k, b"dados", P.aad_parte("x", 0)))
    pac[-1] ^= 1
    try:
        P.decifrar(k, bytes(pac), P.aad_parte("x", 0))
        falhas += ok(log, False, "dado alterado é recusado")
    except P.ErroProtocolo:
        falhas += ok(log, True, "dado alterado é recusado")
    u = P.url_pareamento(["192.168.0.5"], 47800, "abc", "PC da Sala", k)
    falhas += ok(log, P.ler_url_pareamento(u)["nome"] == "PC da Sala" and P.ler_url_pareamento(u)["chave"] == k,
                 "QR de pareamento")
    return falhas


def t_codigos(log, app):
    from datetime import date
    from . import protocolo as P
    base = "341" + "9" + "1000" + "0000150000" + "1091000000000000000000123"
    dv = P._mod11_boleto(base)
    barras = base[:4] + str(dv) + base[4:]
    r = P.ler_codigo(barras, hoje=date(2025, 3, 1))
    falhas = ok(log, r["tipo"] == "boleto" and r["valor"] == 1500.0 and r["vencimento"] == "2025-02-22"
                and r["banco"] == "Itaú", "boleto pelo código de barras (valor, vencimento, banco)")
    r2 = P.ler_codigo(r["linha_fmt"], hoje=date(2025, 3, 1))
    falhas += ok(log, r2["linha"] == r["linha"] and r2["valor"] == 1500.0, "boleto pela linha digitável")
    n = P.ler_codigo("52241112345678000190550010000012341000012345")
    falhas += ok(log, n["tipo"] == "nfe" and n["numero"] == "1234" and n["emitente"] == "12.345.678/0001-90", "chave de NF-e")
    p = P.ler_codigo("00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865406100.00"
                     "5802BR5913Fulano de Tal6008BRASILIA62070503***6304ABCD")
    falhas += ok(log, p["tipo"] == "pix" and p["valor"] == 100.0 and p["recebedor"] == "Fulano de Tal", "PIX copia e cola")
    return falhas


def t_ponta_a_ponta(log, app):
    from PySide6.QtGui import QGuiApplication
    from .app import Controle
    from .cliente import Cliente
    falhas = 0
    rec = tempfile.mkdtemp(prefix="pons-rec-")
    ctl = Controle(app, iniciar_na_bandeja=True, porta=47850)
    ctl.servidor.pasta_recebidos = rec
    ctl.settings.setValue("abrir_scan", "false")
    srv = ctl.servidor
    falhas += ok(log, srv.porta is not None, f"servidor escutando na porta {srv.porta}")
    qr = re.sub(r"h=[^&]+", "h=127.0.0.1", srv.qr_pareamento())
    cel = Cliente(qr, nome="Celular de teste")
    r = cel.parear()
    falhas += ok(log, r.get("ok") and cel.id in srv.aparelhos, "pareamento pelo QR")

    def esperar(cond, s=5):
        fim = time.time() + s
        while time.time() < fim and not cond():
            app.processEvents()
            time.sleep(0.03)
        return cond()

    cel.texto("Olá do celular")
    falhas += ok(log, esperar(lambda: QGuiApplication.clipboard().text() == "Olá do celular"),
                 "texto do celular vai para a área de transferência do PC")
    cel.codigo("52241112345678000190550010000012341000012345")
    falhas += ok(log, esperar(lambda: QGuiApplication.clipboard().text() == "52241112345678000190550010000012341000012345"),
                 "código lido pela câmera chega e é copiado")
    arq = os.path.join(tempfile.mkdtemp(), "documento.pdf")
    dados = os.urandom(3 * 1024 * 1024 + 99)
    open(arq, "wb").write(dados)
    cel.enviar_arquivo(arq, "scan")
    destino = os.path.join(rec, "documento.pdf")
    falhas += ok(log, esperar(lambda: os.path.exists(destino)) and open(destino, "rb").read() == dados,
                 "arquivo de 3 MB do celular chega íntegro")
    cel.notificacao("WhatsApp", "Maria", "Chegou o boleto")
    QGuiApplication.clipboard().setText("Texto do PC")
    ctl.enviar_area_transferencia()
    ctl.enviar_arquivo(arq)
    evs = cel.eventos()
    falhas += ok(log, [e["tipo"] for e in evs] == ["texto", "arquivo"] and evs[0]["texto"] == "Texto do PC",
                 "o celular recebe o texto e o arquivo enviados pelo PC")
    baixado = cel.baixar(evs[1], os.path.join(tempfile.mkdtemp(), "x.pdf"))
    falhas += ok(log, open(baixado, "rb").read() == dados, "arquivo do PC chega íntegro no celular")
    falhas += ok(log, ctl.janela.lista.count() >= 4, f"histórico na janela ({ctl.janela.lista.count()} itens)")
    intruso = Cliente(qr)
    intruso.id = "intruso"
    try:
        intruso.texto("x")
        falhas += ok(log, False, "aparelho não pareado é recusado")
    except Exception:  # noqa: BLE001
        falhas += ok(log, True, "aparelho não pareado é recusado")
    from .janela import DialogoConfig, DialogoPareamento
    d = DialogoPareamento(ctl.janela, ctl)
    d.show()
    app.processEvents()
    falhas += ok(log, d.texto_qr.startswith("pons://parear?") and not d.qr.pixmap().isNull(), "janela de pareamento com QR")
    d.close()
    c = DialogoConfig(ctl.janela, ctl)
    c.show()
    app.processEvents()
    c.accept()
    falhas += ok(log, True, "configurações abrem e salvam")
    ctl.encerrar(atualizando=True)
    return falhas


__all__ = ["executar"]
