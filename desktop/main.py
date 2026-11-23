"""Pons — ponto de entrada.

  Pons.exe                      abre o programa (ou mostra a janela, se já estiver aberto)
  Pons.exe arquivo1 arquivo2    manda os arquivos para o celular (menu "Enviar para › Celular (Pons)")
  Pons.exe --bandeja            inicia só perto do relógio (usado ao iniciar com o Windows)
  Pons.exe --selftest saida.txt autoteste (usado na publicação)
"""
import os
import sys


def main():
    argv = sys.argv
    if "--run-update" in argv:
        from pons.atualizador import ajudante_atualizacao
        return ajudante_atualizacao(argv)
    if "--selftest" in argv:
        from pons.selftest import executar
        return executar(argv)
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Pons.App")
    from PySide6.QtWidgets import QApplication
    app = QApplication(argv)
    from pons import APP_NAME, resource
    from pons.app import Controle, instancia_aberta
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    arquivos = [os.path.abspath(a) for a in argv[1:] if not a.startswith("--") and os.path.isfile(a)]
    msg = ("enviar:" + "\n".join(arquivos)) if arquivos else ("nada" if "--bandeja" in argv else "mostrar")
    if instancia_aberta(msg):
        return 0
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.CreateMutexW(None, False, "Pons_Running")
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(resource("assets", "pons.png")))
    ctl = Controle(app, iniciar_na_bandeja="--bandeja" in argv or bool(arquivos))
    app._ctl = ctl
    for a in arquivos:
        ctl.enviar_arquivo(a)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
