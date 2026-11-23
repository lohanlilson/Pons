# Pons

Ponte entre o celular (Android) e o computador (Windows) pelo Wi-Fi da sua casa ou escritório.
Sem cabo, sem conta e sem nuvem: os dados vão direto de um aparelho para o outro, cifrados.

**Baixar:** <https://lohanlilson.github.io> · [Windows](https://github.com/lohanlilson/Pons/releases/latest/download/Pons-Setup.exe) · [Android (APK)](https://github.com/lohanlilson/Pons/releases/download/android/Pons.apk)

## O que faz
- **Fotos e arquivos** do celular para o PC e do PC para o celular (arrastar na janela ou *Enviar para → Celular (Pons)*).
- **Escanear documento** no celular → PDF no computador.
- **Boleto, conta, NF-e e PIX**: aponte a câmera; o código chega copiado no PC, com banco, valor e vencimento.
- **Texto copiado** de um lado vai para o outro.
- **Notificações** do celular no PC (opcional).
- **Tocar o celular** para encontrá-lo.

## Como usar
1. Instale nos dois. No PC, clique em **Parear celular**.
2. No celular, toque em **Parear com computador** e aponte para o QR.

Os dois precisam estar na mesma rede Wi-Fi.

## Pastas
- `desktop/` — programa do Windows (Python + PySide6). `executar.bat` roda; `build.bat` gera o instalador.
- `android/` — app Android (Kotlin + Compose).

© 2026 Lohan Lilson S. Lopes — lohanlilson@gmail.com
