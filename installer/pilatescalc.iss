; 필라테스 만료일·환불 계산기 - Inno Setup 스크립트
; 빌드: ISCC.exe installer\pilatescalc.iss
;   (PyInstaller가 만든 dist\PilatesCalc 폴더를 그대로 묶는다)

#define AppName "필라테스 계산기"
#define AppExe "PilatesCalc.exe"

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef SourceDir
  #define SourceDir "..\dist\PilatesCalc"
#endif

[Setup]
AppId={{7C4E2A0E-5B39-4E36-9C2B-2E1A6D6C8F41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Pilates Calc
DefaultDirName={autopf}\PilatesCalc
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=PilatesCalc-Setup
SetupIconFile=..\assets\pilates.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
DisableWelcomePage=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로가기 만들기"; GroupDescription: "추가 작업:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  Msg: String;
begin
  Result := True;
  if not (DirExists(ExpandConstant('{commonpf}\Microsoft\EdgeWebView\Application')) or
          DirExists(ExpandConstant('{commonpf32}\Microsoft\EdgeWebView\Application'))) then
  begin
    Msg := '이 프로그램은 Microsoft Edge WebView2 런타임을 사용합니다.' + #13#10 +
           '윈도우 11에는 기본으로 들어 있어 따로 설치할 것이 없습니다.' + #13#10 + #13#10 +
           '설치는 그대로 진행됩니다. 설치 후 앱 창이 비어 있으면 아래 주소에서' + #13#10 +
           'WebView2 런타임을 설치해 주세요.' + #13#10 +
           'https://developer.microsoft.com/microsoft-edge/webview2/';
    MsgBox(Msg, mbInformation, MB_OK);
  end;
end;
