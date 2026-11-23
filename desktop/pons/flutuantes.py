"""Aviso no canto da tela ("Copiado ✓") e print fixado na tela."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget

_abertos: list = []          # mantém vivos os avisos e prints fixados


class Aviso(QWidget):
    """Notificação discreta no canto inferior direito, com miniatura. Clique = ação (ex.: abrir a pasta)."""
    clicado = Signal()

    def __init__(self, titulo: str, texto: str = "", imagem: QImage | None = None, ms: int = 3500, acao=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.acao = acao
        fundo = QWidget(self)
        fundo.setObjectName("Fundo")
        fundo.setStyleSheet("QWidget#Fundo { background: rgba(28,26,38,0.97); border-radius: 14px;"
                            " border: 1px solid rgba(255,255,255,0.10); }"
                            "QLabel { color: #ffffff; background: transparent; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(fundo)
        h = QHBoxLayout(fundo)
        h.setContentsMargins(12, 10, 16, 10)
        h.setSpacing(12)
        if imagem is not None and not imagem.isNull():
            mini = QLabel()
            pm = QPixmap.fromImage(imagem.scaled(96, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            mini.setPixmap(pm)
            mini.setStyleSheet("border-radius: 6px;")
            h.addWidget(mini)
        v = QVBoxLayout()
        v.setSpacing(2)
        t = QLabel(titulo)
        t.setStyleSheet("font-size: 14px; font-weight: 700;")
        v.addWidget(t)
        if texto:
            s = QLabel(texto)
            s.setStyleSheet("color: rgba(255,255,255,0.72); font-size: 12px;")
            s.setWordWrap(True)
            s.setMaximumWidth(320)
            v.addWidget(s)
        h.addLayout(v)
        self.adjustSize()
        tela = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = tela.availableGeometry()
        self.move(g.right() - self.width() - 16, g.bottom() - self.height() - 16)
        if acao:
            self.setCursor(Qt.PointingHandCursor)
        QTimer.singleShot(ms, self.close)
        _abertos.append(self)
        self.destroyed.connect(lambda: _abertos.remove(self) if self in _abertos else None)

    def mousePressEvent(self, ev):
        if self.acao:
            try:
                self.acao()
            except Exception:  # noqa: BLE001
                pass
        self.close()


def avisar(titulo, texto="", imagem=None, ms=3500, acao=None):
    a = Aviso(titulo, texto, imagem, ms, acao)
    a.show()
    return a


class Fixada(QWidget):
    """O print fica por cima de tudo, para consultar enquanto trabalha. Arraste para mover, roda do mouse
    para ampliar, duplo clique ou Esc para fechar, botão direito para mais opções."""

    def __init__(self, imagem: QImage, pos: QPoint, escala: float = 1.0, ao_copiar=None, ao_salvar=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.img = imagem
        self.escala = escala
        self.zoom = 1.0
        self.ao_copiar, self.ao_salvar = ao_copiar, ao_salvar
        self._arraste = None
        self.setWindowOpacity(1.0)
        self._redimensionar()
        self.move(pos - QPoint(6, 6))
        self.setToolTip("Arraste para mover · roda do mouse amplia · duplo clique fecha")
        _abertos.append(self)
        self.destroyed.connect(lambda: _abertos.remove(self) if self in _abertos else None)

    def _tam(self):
        return QSize(max(40, int(self.img.width() / self.escala * self.zoom)),
                     max(30, int(self.img.height() / self.escala * self.zoom)))

    def _redimensionar(self):
        t = self._tam()
        self.resize(t.width() + 12, t.height() + 12)

    def paintEvent(self, ev):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        g.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRect(6, 6, self.width() - 12, self.height() - 12)
        for i in range(6, 0, -1):                 # sombra
            g.setPen(Qt.NoPen)
            g.setBrush(QColor(0, 0, 0, 10))
            g.drawRoundedRect(QRectF(r).adjusted(-i, -i + 2, i, i + 2), 6 + i, 6 + i)
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), 4, 4)
        g.setClipPath(path)
        g.drawImage(r, self.img)
        g.setClipping(False)
        g.setPen(QPen(QColor(139, 92, 255, 200), 1.5))
        g.setBrush(Qt.NoBrush)
        g.drawRoundedRect(QRectF(r), 4, 4)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._arraste = ev.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, ev):
        if self._arraste is not None:
            self.move(ev.globalPosition().toPoint() - self._arraste)

    def mouseReleaseEvent(self, ev):
        self._arraste = None

    def mouseDoubleClickEvent(self, ev):
        self.close()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.close()
        elif ev.key() == Qt.Key_C and ev.modifiers() & Qt.ControlModifier and self.ao_copiar:
            self.ao_copiar(self.img)

    def wheelEvent(self, ev):
        passo = 1.1 if ev.angleDelta().y() > 0 else 1 / 1.1
        if ev.modifiers() & Qt.ControlModifier:   # Ctrl + roda: transparência
            self.setWindowOpacity(max(0.2, min(1.0, self.windowOpacity() * passo)))
            return
        self.zoom = max(0.2, min(5.0, self.zoom * passo))
        self._redimensionar()
        self.update()

    def contextMenuEvent(self, ev):
        m = QMenu(self)
        if self.ao_copiar:
            m.addAction("Copiar", lambda: self.ao_copiar(self.img))
        if self.ao_salvar:
            m.addAction("Salvar…", lambda: self.ao_salvar(self.img))
        m.addAction("Tamanho original", lambda: (setattr(self, "zoom", 1.0), self._redimensionar(), self.update()))
        sub = m.addMenu("Transparência")
        for p in (100, 80, 60, 40):
            sub.addAction(f"{p}%", lambda v=p: self.setWindowOpacity(v / 100))
        m.addSeparator()
        m.addAction("Fechar", self.close)
        m.exec(ev.globalPos())


__all__ = ["Aviso", "avisar", "Fixada"]
