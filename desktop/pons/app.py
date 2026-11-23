"""O Pons rodando: servidor, ícone perto do relógio, avisos e ações."""
from __future__ import annotations

import os
import socket
import sys

from PySide6.QtCore import QObject, QSettings, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_ID, APP_NAME, resource, tema
from .flutuantes import avisar
from .servidor import Servidor

SERVIDOR_LOCAL = "Pons-" + (os.environ.get("USERNAME") or os.environ.get("USER") or "u")


def instancia_aberta(msg="mostrar") -> bool:
    s = QLocalSocket()
    s.connectToServer(SERVIDOR_LOCAL)
    if not s.waitForConnected(400):
        return False
    s.write(msg.encode())
    s.flush()
    s.waitForBytesWritten(1000)
    s.disconnectFromServer()
    return True


def iniciar_com_windows(ligar: bool):
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    import winreg
    chave = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave, 0, winreg.KEY_SET_VALUE) as k:
        if ligar:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --bandeja')
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


def _fmt_valor(v):
    if v is None:
        return ""
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


class Controle(QObject):
    def __init__(self, app: QApplication, iniciar_na_bandeja=False, porta=None):
        super().__init__()
        self.app = app
        self.settings = QSettings(APP_ID, APP_ID)
        self.icone = QIcon(resource("assets", "pons.png"))
        s = self.settings
        self.servidor = Servidor(s.value("nome_pc", "") or socket.gethostname(), s.value("pasta_recebidos", "") or None)
        self.servidor.iniciar(porta or 47800)
        sig = self.servidor.sinais
        sig.texto.connect(self._texto)
        sig.codigo.connect(self._codigo)
        sig.notificacao.connect(self._notificacao)
        sig.arquivo.connect(self._arquivo)
        sig.pareado.connect(lambda n: (self.janela.registrar(f"{n} pareado"), self.janela.atualizar_estado()))
        sig.estado.connect(lambda: (self.janela.atualizar_estado(), self._tooltip()))

        self.local = QLocalServer(self)
        QLocalServer.removeServer(SERVIDOR_LOCAL)
        self.local.listen(SERVIDOR_LOCAL)
        self.local.newConnection.connect(self._mensagem_local)

        from .janela import Janela
        self.janela = Janela(self)
        from .atualizador import Atualizador
        self.atualizador = Atualizador(self.janela)

        self.tray = QSystemTrayIcon(self.icone, self)
        m = QMenu()
        m.addAction("Abrir o Pons", self.mostrar_janela)
        m.addAction("Mandar arquivos para o celular…", lambda: (self.mostrar_janela(), self.janela.escolher_arquivos()))
        m.addAction("Mandar o texto copiado para o celular", self.enviar_area_transferencia)
        m.addAction("Tocar o celular", self.tocar_celular)
        m.addSeparator()
        m.addAction("Sair", self.encerrar)
        self._menu = m
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.mostrar_janela() if r in (QSystemTrayIcon.Trigger,
                                                                              QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        self._tooltip()
        self.aplicar_configuracoes()
        if not iniciar_na_bandeja:
            self.mostrar_janela()
            if not self.servidor.aparelhos:
                QTimer.singleShot(600, self.janela.parear)
        QTimer.singleShot(5000, self.atualizador.verificar_auto)

    def _tooltip(self):
        con = self.servidor.conectados()
        self.tray.setToolTip(f"{APP_NAME} — " + (f"conectado a {con[0].nome}" if con else "nenhum celular conectado"))

    def aplicar_configuracoes(self):
        s = self.settings
        escolha = s.value("tema", "auto")
        tema.aplicar(self.app, tema.sistema_escuro() if escolha == "auto" else escolha == "escuro")
        self.servidor.nome_pc = s.value("nome_pc", "") or socket.gethostname()
        self.servidor.pasta_recebidos = s.value("pasta_recebidos", "") or self.servidor.pasta_recebidos
        try:
            iniciar_com_windows(s.value("iniciar_windows", "true") != "false")
        except OSError:
            pass

    def mostrar_janela(self):
        self.janela.show()
        if self.janela.isMinimized():
            self.janela.showNormal()
        self.janela.raise_()
        self.janela.activateWindow()

    def _mensagem_local(self):
        while self.local.hasPendingConnections():
            c = self.local.nextPendingConnection()
            c.waitForReadyRead(500)
            msg = bytes(c.readAll()).decode("utf-8", "replace").strip()
            c.disconnectFromServer()
            if msg.startswith("enviar:"):
                for arq in msg[7:].split("\n"):
                    if os.path.isfile(arq):
                        self.enviar_arquivo(arq)
            elif msg != "nada":
                self.mostrar_janela()

    # ------------------------------------------------------------------ chegou do celular
    def _texto(self, ap, texto):
        if self.settings.value("copiar_texto", "true") != "false":
            QGuiApplication.clipboard().setText(texto)
        prev = texto if len(texto) < 160 else texto[:157] + "…"
        avisar(f"Texto do {ap} " + ("copiado ✓" if self.settings.value("copiar_texto", "true") != "false" else ""),
               prev, ms=5000, acao=lambda: QGuiApplication.clipboard().setText(texto))
        self.janela.registrar(f"Texto de {ap}: {prev}", {"copiar": texto})

    def _codigo(self, ap, info):
        QGuiApplication.clipboard().setText(info.get("copiar", ""))
        t = info.get("tipo")
        if t == "boleto":
            venc = info.get("vencimento")
            venc = f"{venc[8:10]}/{venc[5:7]}/{venc[:4]}" if venc else "sem vencimento"
            titulo = f"Boleto {info.get('banco', '')}: {_fmt_valor(info['valor'])}"
            texto = f"Vence {venc} · linha digitável copiada ✓"
        elif t == "conta":
            titulo = "Conta de consumo / tributo" + (f": {_fmt_valor(info['valor'])}" if info.get("valor") else "")
            texto = "Linha digitável copiada ✓"
        elif t == "nfe":
            titulo = f"{info['modelo']} nº {info['numero']} (série {info['serie']})"
            texto = f"Emitente {info['emitente']} · {info['emissao']} · chave copiada ✓"
        elif t == "pix":
            titulo = "PIX copia e cola" + (f": {_fmt_valor(info['valor'])}" if info.get("valor") else "")
            texto = (info.get("recebedor") or "") + " · código copiado ✓"
        elif t == "link":
            titulo, texto = "Link do celular copiado ✓", info["url"]
        else:
            titulo, texto = "Código lido copiado ✓", info.get("texto", "")[:160]
        acao = None
        if info.get("url"):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            acao = lambda u=info["url"]: QDesktopServices.openUrl(QUrl(u))  # noqa: E731
        avisar(titulo, texto, ms=7000, acao=acao)
        self.janela.registrar(f"{titulo} — {texto}", info)

    def _notificacao(self, ap, n):
        if self.settings.value("notificacoes", "true") == "false":
            return
        titulo = (n.get("app") + ": " if n.get("app") else "") + (n.get("titulo") or "")
        avisar(titulo or f"Notificação do {ap}", (n.get("texto") or "")[:200], ms=6000)

    def _arquivo(self, ap, caminho, tipo):
        from .janela import abrir, mostrar_na_pasta
        nome = os.path.basename(caminho)
        if tipo == "scan" and self.settings.value("abrir_scan", "true") != "false":
            abrir(caminho)
            avisar("Documento escaneado recebido ✓", nome, ms=4000, acao=lambda: mostrar_na_pasta(caminho))
        else:
            from PySide6.QtGui import QImage
            img = QImage(caminho) if nome.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")) else None
            avisar(f"Recebido do {ap} ✓", nome + " — clique para abrir", img, ms=5000, acao=lambda: abrir(caminho))
        self.janela.registrar(f"{'Escaneado' if tipo == 'scan' else 'Arquivo'} de {ap}: {nome}", {"caminho": caminho})

    # ------------------------------------------------------------------ para o celular
    def _tem_celular(self) -> bool:
        if not self.servidor.aparelhos:
            QMessageBox.information(self.janela, APP_NAME, "Primeiro pareie um celular.")
            self.janela.parear()
            return bool(self.servidor.aparelhos)
        return True

    def enviar_arquivo(self, caminho):
        if not self._tem_celular():
            return
        self.servidor.enviar_arquivo(caminho)
        nome = os.path.basename(caminho)
        con = self.servidor.conectados()
        aviso = "" if con else " (vai quando o app do celular abrir)"
        avisar("Mandando para o celular", nome + aviso, ms=3000)
        self.janela.registrar(f"Enviado ao celular: {nome}{aviso}", {"caminho": caminho})

    def enviar_area_transferencia(self):
        if not self._tem_celular():
            return
        t = QGuiApplication.clipboard().text()
        if not t.strip():
            QMessageBox.information(self.janela, APP_NAME, "Não há texto copiado no computador.")
            return
        self.servidor.enviar_texto(t)
        avisar("Texto mandado ao celular ✓", t[:120], ms=3000)
        self.janela.registrar(f"Texto enviado ao celular: {t[:120]}", {"copiar": t})

    def tocar_celular(self):
        if not self._tem_celular():
            return
        self.servidor.tocar()
        avisar("Tocando o celular…", "Ele toca mesmo no silencioso, até você abrir o aviso.", ms=3000)

    def encerrar(self, atualizando=False):
        self.servidor.parar()
        self.tray.hide()
        self.local.close()
        if not atualizando:
            self.app.quit()


__all__ = ["Controle", "instancia_aberta", "iniciar_com_windows"]
