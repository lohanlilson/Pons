"""Janela do Pons: estado da conexão, pareamento por QR, enviar ao celular e o que chegou dele."""
from __future__ import annotations

import io
import os
import sys
import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from . import APP_NAME, COPYRIGHT, EMAIL, __version__, resource


def abrir(c):
    QDesktopServices.openUrl(QUrl.fromLocalFile(c))


def mostrar_na_pasta(c):
    if sys.platform == "win32":
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(c)])
    else:
        abrir(os.path.dirname(c))


def imagem_qr(texto: str, escala=8) -> QImage:
    import segno
    b = io.BytesIO()
    segno.make(texto, error="m").save(b, kind="png", scale=escala, border=3, dark="#1d1a2e", light="#ffffff")
    img = QImage()
    img.loadFromData(b.getvalue())
    return img


class DialogoPareamento(QDialog):
    def __init__(self, janela, ctl):
        super().__init__(janela)
        self.ctl = ctl
        self.setWindowTitle("Parear celular")
        v = QVBoxLayout(self)
        v.addWidget(QLabel("<h3 style='margin:0'>Parear um celular</h3>"))
        passos = QLabel("1. Instale o app Pons no celular (link na página dos programas).<br>"
                        "2. Abra o app e toque em <b>Parear com computador</b>.<br>"
                        "3. Aponte a câmera para este código.<br><br>"
                        "<span style='color:gray'>O celular e o computador precisam estar no mesmo Wi-Fi.</span>")
        passos.setWordWrap(True)
        v.addWidget(passos)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setMinimumSize(320, 320)
        v.addWidget(self.qr)
        self.lb = QLabel("", objectName="Muted")
        self.lb.setAlignment(Qt.AlignCenter)
        v.addWidget(self.lb)
        bt = QPushButton("Fechar")
        bt.clicked.connect(self.reject)
        v.addWidget(bt, 0, Qt.AlignRight)
        self._novo()
        self._t = QTimer(self, interval=9 * 60 * 1000, timeout=self._novo)       # o código vale 10 minutos
        self._t.start()
        ctl.servidor.sinais.pareado.connect(self._pareou)

    def _novo(self):
        texto = self.ctl.servidor.qr_pareamento()
        self.texto_qr = texto
        self.qr.setPixmap(QPixmap.fromImage(imagem_qr(texto)).scaled(320, 320, Qt.KeepAspectRatio, Qt.FastTransformation))
        from .servidor import ips_locais
        self.lb.setText(f"Este computador: {self.ctl.servidor.nome_pc} · {', '.join(ips_locais())}")

    def _pareou(self, nome):
        self._desligar()
        self.accept()
        self.ctl.tray.showMessage(APP_NAME, f"Pronto! {nome} está pareado com este computador.", self.ctl.icone, 5000)

    def _desligar(self):
        try:
            self.ctl.servidor.sinais.pareado.disconnect(self._pareou)
        except (RuntimeError, TypeError):
            pass

    def done(self, r):
        self._desligar()
        self._t.stop()
        super().done(r)


class Janela(QMainWindow):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.settings = ctl.settings
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource("assets", "pons.png")))
        self.resize(860, 640)
        self.setAcceptDrops(True)
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(16, 14, 16, 10)
        v.setSpacing(12)

        hero = QFrame(objectName="Hero")
        hv = QVBoxLayout(hero)
        hv.setContentsMargins(22, 16, 22, 16)
        self.lb_titulo = QLabel("Pons", objectName="HeroTitle")
        self.lb_estado = QLabel("", objectName="HeroSub")
        hv.addWidget(self.lb_titulo)
        hv.addWidget(self.lb_estado)
        linha = QHBoxLayout()
        linha.setSpacing(8)
        self.bt_parear = QPushButton("Parear celular", objectName="HeroPrimary")
        self.bt_parear.clicked.connect(self.parear)
        linha.addWidget(self.bt_parear)
        for texto, fn, dica in (("Enviar arquivos…", self.escolher_arquivos, "Ou arraste os arquivos para esta janela"),
                                ("Enviar texto copiado", ctl.enviar_area_transferencia,
                                 "O texto copiado no PC vai para a área de transferência do celular"),
                                ("Tocar o celular", ctl.tocar_celular, "Faz o celular tocar, para achá-lo")):
            b = QPushButton(texto, objectName="HeroPrimary")
            b.setToolTip(dica)
            b.clicked.connect(fn)
            linha.addWidget(b)
        linha.addStretch()
        hv.addLayout(linha)
        v.addWidget(hero)

        self.soltar = QLabel("Arraste arquivos aqui para mandar ao celular")
        self.soltar.setAlignment(Qt.AlignCenter)
        self.soltar.setMinimumHeight(70)
        self.soltar.setObjectName("Card")
        self.soltar.setStyleSheet("QLabel#Card { border: 2px dashed palette(mid); border-radius: 14px; padding: 12px; }")
        v.addWidget(self.soltar)

        cab = QHBoxLayout()
        cab.addWidget(QLabel("<b>Recebidos e enviados</b>"))
        cab.addStretch()
        b = QPushButton("Abrir pasta")
        b.clicked.connect(lambda: abrir(ctl.servidor.pasta_recebidos) if os.path.isdir(ctl.servidor.pasta_recebidos)
                          else QMessageBox.information(self, APP_NAME, "Nada recebido ainda."))
        cab.addWidget(b)
        b = QPushButton("Configurações")
        b.clicked.connect(lambda: DialogoConfig(self, ctl).exec())
        cab.addWidget(b)
        v.addLayout(cab)
        self.lista = QListWidget()
        self.lista.setWordWrap(True)
        self.lista.setSpacing(2)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        self.lista.itemDoubleClicked.connect(self._abrir_item)
        v.addWidget(self.lista, 1)
        self.vazio = QLabel("Fotos, PDFs escaneados, textos e códigos que chegarem do celular aparecem aqui.",
                            objectName="Muted")
        self.vazio.setAlignment(Qt.AlignCenter)
        v.addWidget(self.vazio)
        self.statusBar().showMessage(f"{APP_NAME} {__version__} — continua funcionando perto do relógio quando a janela "
                                     "é fechada.")
        self.atualizar_estado()

    # ------------------------------------------------------------------ estado
    def atualizar_estado(self):
        srv = self.ctl.servidor
        con = srv.conectados()
        if con:
            self.lb_estado.setText("Conectado a " + ", ".join(a.nome for a in con))
        elif srv.aparelhos:
            self.lb_estado.setText("Pareado com " + ", ".join(a.nome for a in srv.aparelhos.values()) +
                                   " · abra o app no celular para conectar")
        else:
            self.lb_estado.setText("Nenhum celular pareado ainda. Clique em “Parear celular”.")
        self.bt_parear.setText("Parear outro celular" if srv.aparelhos else "Parear celular")

    def registrar(self, texto: str, dados: dict | None = None):
        it = QListWidgetItem(f"{time.strftime('%H:%M')}  ·  {texto}")
        it.setData(Qt.UserRole, dados or {})
        self.lista.insertItem(0, it)
        while self.lista.count() > 300:
            self.lista.takeItem(self.lista.count() - 1)
        self.vazio.hide()

    def _abrir_item(self, it):
        d = it.data(Qt.UserRole) or {}
        if d.get("caminho") and os.path.exists(d["caminho"]):
            abrir(d["caminho"])
        elif d.get("copiar"):
            QGuiApplication.clipboard().setText(d["copiar"])
            self.statusBar().showMessage("Copiado.", 2500)

    def _menu(self, pos):
        it = self.lista.itemAt(pos)
        if not it:
            return
        d = it.data(Qt.UserRole) or {}
        m = QMenu(self)
        if d.get("caminho") and os.path.exists(d["caminho"]):
            m.addAction("Abrir", lambda: abrir(d["caminho"]))
            m.addAction("Mostrar na pasta", lambda: mostrar_na_pasta(d["caminho"]))
        if d.get("copiar"):
            m.addAction("Copiar", lambda: QGuiApplication.clipboard().setText(d["copiar"]))
        if d.get("url"):
            m.addAction("Abrir no navegador", lambda: QDesktopServices.openUrl(QUrl(d["url"])))
        if not m.isEmpty():
            m.exec(self.lista.mapToGlobal(pos))

    # ------------------------------------------------------------------ ações
    def parear(self):
        DialogoPareamento(self, self.ctl).exec()
        self.atualizar_estado()

    def escolher_arquivos(self):
        arqs, _ = QFileDialog.getOpenFileNames(self, "Mandar para o celular")
        for a in arqs:
            self.ctl.enviar_arquivo(a)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            c = u.toLocalFile()
            if c and os.path.isfile(c):
                self.ctl.enviar_arquivo(c)
        ev.acceptProposedAction()

    def fechar_para_atualizar(self):
        self.ctl.encerrar(atualizando=True)

    def closeEvent(self, ev):
        ev.ignore()
        self.hide()
        if self.settings.value("avisou_bandeja", "false") != "true":
            self.settings.setValue("avisou_bandeja", "true")
            self.ctl.tray.showMessage(APP_NAME, "O Pons continua perto do relógio, recebendo o que vier do celular.",
                                      self.ctl.icone, 5000)


class DialogoConfig(QDialog):
    def __init__(self, janela, ctl):
        super().__init__(janela)
        self.ctl = ctl
        s = ctl.settings
        self.setWindowTitle("Configurações")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        f = QFormLayout()
        b = lambda k, d="true": s.value(k, d) != "false"  # noqa: E731
        self.ed_nome = QLineEdit(ctl.servidor.nome_pc)
        f.addRow("Nome deste computador:", self.ed_nome)
        linha = QHBoxLayout()
        self.ed_pasta = QLineEdit(ctl.servidor.pasta_recebidos)
        bt = QPushButton("Escolher…")
        bt.clicked.connect(self._pasta)
        linha.addWidget(self.ed_pasta)
        linha.addWidget(bt)
        f.addRow("Salvar recebidos em:", linha)
        self.ck_copiar = QCheckBox("Texto que chega do celular já vai para a área de transferência")
        self.ck_copiar.setChecked(b("copiar_texto"))
        f.addRow(self.ck_copiar)
        self.ck_scan = QCheckBox("Abrir na hora os documentos escaneados no celular")
        self.ck_scan.setChecked(b("abrir_scan"))
        f.addRow(self.ck_scan)
        self.ck_notif = QCheckBox("Mostrar aqui as notificações do celular")
        self.ck_notif.setChecked(b("notificacoes"))
        f.addRow(self.ck_notif)
        self.ck_ini = QCheckBox("Iniciar com o Windows (fica perto do relógio)")
        self.ck_ini.setChecked(b("iniciar_windows"))
        f.addRow(self.ck_ini)
        self.cb_tema = QComboBox()
        for txt, val in (("Igual ao Windows", "auto"), ("Claro", "claro"), ("Escuro", "escuro")):
            self.cb_tema.addItem(txt, val)
        self.cb_tema.setCurrentIndex(max(0, self.cb_tema.findData(s.value("tema", "auto"))))
        f.addRow("Tema:", self.cb_tema)
        self.ck_upd = QCheckBox("Procurar atualizações automaticamente")
        self.ck_upd.setChecked(b("auto_atualizar"))
        f.addRow(self.ck_upd)
        v.addLayout(f)
        v.addWidget(QLabel("<b>Celulares pareados</b>"))
        self.aps = QListWidget()
        self.aps.setMaximumHeight(110)
        for a in ctl.servidor.aparelhos.values():
            it = QListWidgetItem(f"{a.nome}  {('· ' + a.modelo) if a.modelo else ''}")
            it.setData(Qt.UserRole, a.id)
            self.aps.addItem(it)
        v.addWidget(self.aps)
        esq = QPushButton("Esquecer o celular selecionado")
        esq.clicked.connect(self._esquecer)
        v.addWidget(esq, 0, Qt.AlignLeft)
        sobre = QLabel(f"<p><b>{APP_NAME} {__version__}</b> — ponte entre o celular e o computador. "
                       f"Tudo passa só pela sua rede, cifrado (AES-256).<br>{COPYRIGHT} · {EMAIL}</p>")
        sobre.setWordWrap(True)
        v.addWidget(sobre)
        linha = QHBoxLayout()
        upd = QPushButton("Procurar atualizações agora")
        upd.clicked.connect(lambda: ctl.atualizador.verificar(silencioso=False))
        linha.addWidget(upd)
        linha.addStretch()
        c = QPushButton("Cancelar")
        c.clicked.connect(self.reject)
        ok = QPushButton("Salvar", objectName="Primary")
        ok.clicked.connect(self.accept)
        linha.addWidget(c)
        linha.addWidget(ok)
        v.addLayout(linha)

    def _pasta(self):
        d = QFileDialog.getExistingDirectory(self, "Salvar recebidos em", self.ed_pasta.text())
        if d:
            self.ed_pasta.setText(d)

    def _esquecer(self):
        it = self.aps.currentItem()
        if it and QMessageBox.question(self, APP_NAME, f"Esquecer {it.text().strip()}? Ele precisará parear de novo.") \
                == QMessageBox.Yes:
            self.ctl.servidor.esquecer(it.data(Qt.UserRole))
            self.aps.takeItem(self.aps.row(it))

    def accept(self):
        s = self.ctl.settings
        b = lambda x: "true" if x else "false"  # noqa: E731
        s.setValue("nome_pc", self.ed_nome.text().strip())
        s.setValue("pasta_recebidos", self.ed_pasta.text().strip())
        s.setValue("copiar_texto", b(self.ck_copiar.isChecked()))
        s.setValue("abrir_scan", b(self.ck_scan.isChecked()))
        s.setValue("notificacoes", b(self.ck_notif.isChecked()))
        s.setValue("iniciar_windows", b(self.ck_ini.isChecked()))
        s.setValue("tema", self.cb_tema.currentData())
        s.setValue("auto_atualizar", b(self.ck_upd.isChecked()))
        self.ctl.aplicar_configuracoes()
        super().accept()


__all__ = ["Janela", "DialogoConfig", "DialogoPareamento", "imagem_qr", "abrir", "mostrar_na_pasta"]
