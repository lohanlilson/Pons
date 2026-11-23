; Instalador do Pons (Inno Setup 6)
#define AppName   "Pons"
#define AppExe    "Pons.exe"
#define AppGuid   "9D70FD3B-086F-4A02-831F-3CC3A4DE93EA"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Lohan Lilson S. Lopes"
#endif
#ifndef AppEmail
  #define AppEmail ""
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Pons"
#endif

[Setup]
AppId={{{#AppGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppContact={#AppEmail}
AppSupportURL=https://github.com/lohanlilson/Pons
AppPublisherURL=https://github.com/lohanlilson/Pons
AppCopyright=© 2026 {#AppPublisher}
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright=© 2026 {#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\assets\pons.ico
WizardImageFile=..\assets\wizard.bmp
WizardSmallImageFile=..\assets\wizard_small.bmp
OutputDir=..\Saida
OutputBaseFilename=Pons-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=force
RestartApplications=no
MinVersion=10.0.17763
SetupLogging=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; arquivos de versões anteriores (o PyInstaller pode mudar nomes de bibliotecas entre versões)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Pons.App"
; botão direito num arquivo → Enviar para → Celular (Pons)
Name: "{usersendto}\Celular (Pons)"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "Pons.App"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey
; o programa grava "iniciar com o Windows" nesta chave; a desinstalação remove
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Pons"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

[Run]
; libera o Pons no firewall só em redes privadas (casa/escritório) para o celular conseguir conectar
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Pons"""; Flags: runhidden; StatusMsg: "Configurando o firewall..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Pons"" dir=in action=allow program=""{app}\{#AppExe}"" enable=yes profile=private,domain"; Flags: runhidden
Filename: "{app}\{#AppExe}"; Description: "Abrir o Pons agora"; Flags: nowait postinstall skipifsilent runasoriginaluser
; atualização automática (instalação silenciosa): volta a rodar perto do relógio (o celular reconecta sozinho)
Filename: "{app}\{#AppExe}"; Parameters: "--bandeja"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Pons"""; Flags: runhidden; RunOnceId: "FirewallPons"
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "EncerrarPons"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\*.antigo"

#include "codigo.iss"
