; Inno Setup 6 script for Transcribe. Built by .github/workflows/windows-installer.yml:
;   iscc /DAppVersion=1.2.3 installer\transcribe.iss
; Expects build\uv.exe, build\transcribe.ico, build\VERSION and build\python\ (a standalone CPython 3.12) next to the repo root
; (the workflow makes them).

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{6C2F3E0B-8B7A-4C55-9E7B-2D4F1A9C7E31}
AppName=Transcribe
AppVersion={#AppVersion}
AppPublisher=Transcribe
DefaultDirName={localappdata}\Programs\Transcribe
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; The libraries (~1 GB unpacked) and the Whisper model (~3 GB) are downloaded during install.
ExtraDiskSpaceRequired=4500000000
OutputDir=..\dist
OutputBaseFilename=Transcribe-Setup-{#AppVersion}
SetupIconFile=..\build\transcribe.ico
UninstallDisplayIcon={app}\transcribe.ico
UninstallDisplayName=Transcribe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The speech model choice is stored in HKCU\Environment; tell Explorer so new processes see it.
ChangesEnvironment=yes

[Messages]
WelcomeLabel2=This installs Transcribe, which records your meetings and transcribes them on this computer.%n%nDuring setup it downloads 2-3.5 GB (speech libraries and the Whisper speech model you choose), so keep the computer connected to the internet. On a slow connection this takes a while.

[Tasks]
Name: startup; Description: "Start Transcribe when I sign in"

[InstallDelete]
; Old source files and the bundled Python from a previous version; the venv is refreshed by uv sync.
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\runtime"
; Left by 0.0.0-dev.1, which let uv download Python (and failed on its junction).
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "..\build\uv.exe"; DestDir: "{app}"
Source: "..\build\python\*"; DestDir: "{app}\runtime"; Flags: recursesubdirs createallsubdirs
Source: "..\build\transcribe.ico"; DestDir: "{app}"
Source: "setup.cmd"; DestDir: "{app}"
Source: "download-models.cmd"; DestDir: "{app}"
Source: "..\pyproject.toml"; DestDir: "{app}\app"
Source: "..\uv.lock"; DestDir: "{app}\app"
Source: "..\.python-version"; DestDir: "{app}\app"
Source: "..\README.md"; DestDir: "{app}\app"
Source: "..\LICENSE"; DestDir: "{app}\app"
Source: "..\src\*"; DestDir: "{app}\app\src"; Excludes: "__pycache__,*.pyc"; Flags: recursesubdirs
; The installed version, packaged with the app (transcribe/VERSION); the workflow writes it.
Source: "..\build\VERSION"; DestDir: "{app}\app\src\transcribe"

[Icons]
Name: "{autoprograms}\Transcribe"; Filename: "{app}\venv\Scripts\transcribe-tray.exe"; IconFilename: "{app}\transcribe.ico"

[Registry]
; The tray app's "Start at login" item reads and writes this same value.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Transcribe"; ValueData: """{app}\venv\Scripts\transcribe-tray.exe"" --background"; Tasks: startup

[Run]
Filename: "{app}\venv\Scripts\transcribe-tray.exe"; Description: "Open Transcribe now"; Flags: postinstall nowait skipifsilent; Check: ComponentsReady

[UninstallDelete]
; uv-created folders (venv, python, cache) and logs are not in [Files], so remove them explicitly.
Type: filesandordirs; Name: "{app}"

[Code]
var
  Ready: Boolean;
  ModelPage: TInputOptionWizardPage;

const
  EnvKey = 'Environment';

function SetEnvironmentVariable(Name, Value: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

procedure InitializeWizard;
begin
  ModelPage := CreateInputOptionPage(wpSelectTasks,
    'Speech model', 'Which Whisper model should Transcribe use?',
    'large-v3 is the most accurate and handles Thai best. It is a 3 GB download and needs about 4 GB of free ' +
    'memory while transcribing. On a computer without an NVIDIA graphics card it takes about 1-2 times the ' +
    'meeting length to transcribe.' + #13#10#13#10 +
    'large-v3-turbo is half the download, needs about 2 GB of free memory and is several times faster, so a ' +
    'one-hour meeting is ready much sooner. It makes a few more mistakes, and noticeably more in Thai than ' +
    'in English. Choose it on a computer with 8 GB of memory, or 16 GB that is usually busy.' + #13#10#13#10 +
    'You can switch later on the Transcribe page, for each meeting, or by running this installer again.',
    True, False);
  ModelPage.Add('large-v3: most accurate, best for Thai (3 GB download, about 4 GB of memory, slower)');
  ModelPage.Add('large-v3-turbo: several times faster, a little less accurate (1.6 GB download, about 2 GB of memory)');
  if GetPreviousData('Model', 'large-v3') = 'large-v3-turbo' then
    ModelPage.SelectedValueIndex := 1
  else
    ModelPage.SelectedValueIndex := 0;
end;

function ChosenModel: String;
begin
  if ModelPage.SelectedValueIndex = 1 then
    Result := 'large-v3-turbo'
  else
    Result := 'large-v3';
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'Model', ChosenModel);
end;

function ComponentsReady: Boolean;
begin
  Result := Ready;
end;

function RunScript(const Script, Status: String; ShowWindow: Integer): Integer;
var
  Code: Integer;
begin
  WizardForm.StatusLabel.Caption := Status;
  WizardForm.FilenameLabel.Caption := '';
  if Exec(ExpandConstant('{app}\' + Script), '', ExpandConstant('{app}'), ShowWindow, ewWaitUntilTerminated, Code) then
    Result := Code
  else
    Result := -1;
end;

// Stops everything running from the install dir: the tray app, and the MCP shim Claude Desktop keeps open.
// Files they hold open could not be replaced on upgrade or removed on uninstall.
procedure StopRunningApp;
var
  Dir: String;
  Code: Integer;
begin
  Dir := ExpandConstant('{app}');
  StringChangeEx(Dir, '''', '''''', True);  // PowerShell single-quote escaping
  Exec('powershell.exe', '-NoProfile -NonInteractive -Command "Get-Process | Where-Object { $_.Path -like ''' + Dir + '\*'' } | Stop-Process -Force"',
       '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp;
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep <> ssPostInstall then
    exit;
  WizardForm.ProgressGauge.Style := npbstMarquee;

  // In this process for the model download and the first launch (children inherit it), and in the
  // registry for every later start.
  SetEnvironmentVariable('TRANSCRIBE_MODEL', ChosenModel);
  RegWriteStringValue(HKEY_CURRENT_USER, EnvKey, 'TRANSCRIBE_MODEL', ChosenModel);

  Ready := False;
  repeat
    if RunScript('setup.cmd', 'Downloading the speech libraries (about 500 MB). This takes a few minutes...', SW_HIDE) = 0 then
      Ready := True
    else if MsgBox('Transcribe couldn''t download its components. Check your internet connection, then press Retry.' + #13#10#13#10 +
                   'Details are in ' + ExpandConstant('{app}\install.log'), mbError, MB_RETRYCANCEL) <> IDRETRY then
    begin
      MsgBox('Setup is not finished. Run this installer again when you are connected to the internet.', mbInformation, MB_OK);
      exit;
    end;
  until Ready;

  while RunScript('download-models.cmd', 'Downloading the Whisper speech model ' + ChosenModel + '. Progress is shown in the other window...', SW_SHOWNORMAL) <> 0 do
    if MsgBox('The speech model download didn''t finish.' + #13#10#13#10 +
              'Press Retry to continue it, or Cancel to skip: the model will then download the first time you transcribe a meeting.',
              mbError, MB_RETRYCANCEL) <> IDRETRY then
      break;

  WizardForm.ProgressGauge.Style := npbstNormal;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    StopRunningApp;
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Transcribe');
    RegDeleteValue(HKEY_CURRENT_USER, EnvKey, 'TRANSCRIBE_MODEL');
  end;
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    MsgBox('Transcribe was removed. Your recordings were kept in ' + ExpandConstant('{%USERPROFILE}') + '\Meetings.' + #13#10#13#10 +
           'The Whisper speech model (1.6-3 GB) was kept too, in case you reinstall. To free that space, delete the folder ' +
           ExpandConstant('{%USERPROFILE}') + '\.cache\huggingface.', mbInformation, MB_OK);
end;
