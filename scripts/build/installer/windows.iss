; Amplifier Windows Installer — Inno Setup 6
; Version is injected by build_windows_installer.ps1 via /DMyAppVersion=<ver>
; Default fallback for manual ISCC invocations:
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "Amplifier"
#define MyAppPublisher "Point Capitalis"
#define MyAppURL "https://api.pointcapitalis.com"
#define MyAppExeName "Amplifier.exe"

[Setup]
AppId={{B3F6E8A2-9D4E-4C7F-A8B1-3E5C7D9F0A1B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\..\..\dist\installers
OutputBaseFilename=AmplifierSetup-v{#MyAppVersion}
LicenseFile=eula.rtf
Compression=lzma2
SolidCompression=yes
; Per-user install — avoids UAC prompts on unprivileged accounts
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart"; Description: "Start Amplifier automatically when I log in (recommended)"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
; Main executable (produced by Nuitka --onefile)
Source: "..\..\..\dist\windows\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Post-install: download Patchright Chromium browser (one-time, ~150 MB)
; This runs silently; the app will prompt again on first launch if it fails here.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-browser"; Description: "Download browser (required, ~150 MB)"; Flags: runhidden waituntilterminated

; Post-install: register Task Scheduler entry for auto-start at login
Filename: "schtasks.exe"; Parameters: "/Create /SC ONLOGON /TN ""{#MyAppName}"" /TR ""\""{app}\{#MyAppExeName}\"""" /F"; Flags: runhidden; Tasks: autostart

; Post-install: offer to launch the app now
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove Task Scheduler entry on uninstall (ignore errors if not present)
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""{#MyAppName}"" /F"; Flags: runhidden; RunOnceId: "RemoveSchedTask"
