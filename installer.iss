; Inno Setup 脚本 —— 由 GitHub Actions 调用： iscc /DAppVersion=1.0.1 installer.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6F1B3C52-4E0A-4B8E-9C71-0F1A2B3C4D5E}
AppName=Noodle Fun Finance
AppVersion={#AppVersion}
AppPublisher=Noodle Fun
DefaultDirName={autopf}\NoodleFunFinance
DefaultGroupName=Noodle Fun Finance
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=NoodleFunFinance-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\NoodleFunFinance.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\NoodleFunFinance\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Noodle Fun Finance"; Filename: "{app}\NoodleFunFinance.exe"
Name: "{autodesktop}\Noodle Fun Finance"; Filename: "{app}\NoodleFunFinance.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NoodleFunFinance.exe"; Description: "{cm:LaunchProgram,Noodle Fun Finance}"; Flags: nowait postinstall skipifsilent
