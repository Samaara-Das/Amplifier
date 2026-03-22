; Inno Setup Script for Amplifier
; Compile with Inno Setup 6.x

[Setup]
AppName=Amplifier
AppVersion=0.1.0
AppPublisher=Amplifier
DefaultDirName={autopf}\Amplifier
DefaultGroupName=Amplifier
OutputBaseFilename=Amplifier-Setup-0.1.0
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
Source: "dist\Amplifier\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Config files
Source: "config\platforms.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "config\.env.example"; DestDir: "{app}\config"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\Amplifier"; Filename: "{app}\Amplifier.exe"
Name: "{group}\Amplifier Dashboard"; Filename: "http://localhost:5222"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Amplifier"; Filename: "{app}\Amplifier.exe"; Tasks: desktopicon

[Run]
; Install Playwright Chromium browser on first run
Filename: "cmd.exe"; Parameters: "/c ""{app}\Amplifier.exe"" -m playwright install chromium"; Description: "Install browser components"; StatusMsg: "Installing browser components (Chromium)..."; Flags: runhidden
Filename: "{app}\Amplifier.exe"; Description: "Launch Amplifier"; Flags: nowait postinstall skipifsilent

[Registry]
; Auto-start with Windows (optional)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Amplifier"; ValueData: """{app}\Amplifier.exe"""; Flags: uninsdeletevalue; Tasks: startupicon

; User data (data/, logs/, profiles/) is NOT deleted on uninstall to preserve credentials and history
