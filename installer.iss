; Inno Setup Script for Campaign Auto-Poster
; Compile with Inno Setup 6.x

[Setup]
AppName=Campaign Auto-Poster
AppVersion=0.1.0
AppPublisher=Campaign Platform
DefaultDirName={autopf}\CampaignPoster
DefaultGroupName=Campaign Auto-Poster
OutputBaseFilename=CampaignPoster-Setup-0.1.0
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startupicon"; Description: "Start automatically with Windows"; GroupDescription: "Startup:"

[Files]
; PyInstaller output directory
Source: "dist\CampaignPoster\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Config files
Source: "config\platforms.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "config\.env.example"; DestDir: "{app}\config"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\Campaign Auto-Poster"; Filename: "{app}\CampaignPoster.exe"
Name: "{group}\Campaign Dashboard"; Filename: "http://localhost:5222"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Campaign Auto-Poster"; Filename: "{app}\CampaignPoster.exe"; Tasks: desktopicon

[Run]
; Install Playwright browsers on first run
Filename: "{app}\CampaignPoster.exe"; Parameters: "--install-browsers"; Description: "Install browser components"; StatusMsg: "Installing browser components..."
Filename: "{app}\CampaignPoster.exe"; Description: "Launch Campaign Auto-Poster"; Flags: nowait postinstall skipifsilent

[Registry]
; Auto-start with Windows (optional)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CampaignPoster"; ValueData: """{app}\CampaignPoster.exe"""; Flags: uninsdeletevalue; Tasks: startupicon

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\profiles"
