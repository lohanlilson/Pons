; Atualização pequena do Pons: contém só os arquivos que mudaram desde a versão BaseVersion.
; Gerado pelo build.py (python build.py --base-dir <pasta da versão anterior> --base-versao X.Y.Z).
#define AppName   "Pons"
#define AppExe    "Pons.exe"
#define AppGuid   "9D70FD3B-086F-4A02-831F-3CC3A4DE93EA"
#ifndef AppPublisher
  #define AppPublisher "Lohan Lilson S. Lopes"
#endif

[Setup]
AppId={{{#AppGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\assets\pons.ico
WizardSmallImageFile=..\assets\wizard_small.bmp
OutputDir=..\Saida
OutputBaseFilename=Pons-Atualizacao-{#BaseVersion}-para-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=force
RestartApplications=no
MinVersion=10.0
SetupLogging=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#include "..\build\patch_remover.iss"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o Pons agora"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#AppExe}"; Parameters: "--bandeja"; Flags: nowait runasoriginaluser; Check: WizardSilent

#include "codigo.iss"

[Code]
// só aplica sobre a versão exata para a qual foi gerada
function InitializeSetup(): Boolean;
var
  V: String;
begin
  Result := True;
  if not RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{' + '{#AppGuid}' + '}_is1',
                             'DisplayVersion', V) then
    V := '';
  if V <> '{#BaseVersion}' then
  begin
    Log('Atualização pequena recusada: versão instalada "' + V + '", esperada {#BaseVersion}');
    SuppressibleMsgBox('Esta atualização serve só para o Pons {#BaseVersion}. Baixe o instalador completo em github.com/lohanlilson/Pons.',
                       mbError, MB_OK, IDOK);
    Result := False;
  end;
end;
