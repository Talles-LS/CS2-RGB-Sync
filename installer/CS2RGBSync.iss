; Script do Inno Setup 6 para gerar CS2RGBSync_Setup.exe (Windows 11 64 bits)

#define MyAppName "CS2 RGB Sync"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "CS2 RGB Sync"
#define MyAppExeName "CS2RGBSync.exe"

[Setup]
AppId={{9E8B2D4C-4F1A-4D7E-A2B3-7C91D8A5F010}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\CS2 RGB Sync
DefaultGroupName=CS2 RGB Sync
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\dist
OutputBaseFilename=CS2RGBSync_Setup
SetupIconFile=..\assets\icons\cs2_rgb_sync.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\THIRD_PARTY_LICENSES.txt
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"
Name: "startup"; Description: "Iniciar o CS2 RGB Sync automaticamente com o Windows"; GroupDescription: "Opções de inicialização:"; Flags: unchecked
Name: "setupgsi"; Description: "Configurar automaticamente o arquivo GSI do Counter-Strike 2"; GroupDescription: "Integração com o CS2:"

[Files]
Source: "..\dist\CS2RGBSync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CONFIGURACAO.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\MANUAL_INSTALACAO.pdf"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\CS2 RGB Sync"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Manual de Instalação (PDF)"; Filename: "{app}\MANUAL_INSTALACAO.pdf"
Name: "{group}\Desinstalar CS2 RGB Sync"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CS2 RGB Sync"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CS2RGBSync"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: startup
Root: HKCU; Subkey: "Software\CS2RGBSync\Install"; ValueType: string; ValueName: "CS2Dir"; ValueData: "{code:GetCS2Dir}"; Flags: uninsdeletekey; Tasks: setupgsi

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "{code:GetSetupGsiArgs}"; StatusMsg: "Configurando arquivo GSI do Counter-Strike 2..."; Flags: runhidden waituntilterminated; Tasks: setupgsi; Check: HasValidCS2Dir
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar o CS2 RGB Sync agora"; Flags: nowait postinstall skipifsilent

[Code]
var
  CS2DirPage: TInputDirWizardPage;
  DetectedCS2Dir: string;

function NormalizeCS2Candidate(const RawPath: string): string;
var
  CleanPath, Candidate: string;
begin
  Result := '';
  CleanPath := RemoveBackslashUnlessRoot(Trim(RawPath));
  if CleanPath = '' then
    Exit;

  if DirExists(CleanPath + '\cfg') and (Lowercase(ExtractFileName(CleanPath)) = 'csgo') then
  begin
    Result := CleanPath;
    Exit;
  end;

  Candidate := CleanPath + '\game\csgo';
  if DirExists(Candidate + '\cfg') then
  begin
    Result := Candidate;
    Exit;
  end;

  Candidate := CleanPath + '\csgo';
  if DirExists(Candidate + '\cfg') then
  begin
    Result := Candidate;
    Exit;
  end;

  if Lowercase(ExtractFileName(CleanPath)) = 'cfg' then
  begin
    Candidate := ExtractFileDir(CleanPath);
    if DirExists(Candidate + '\cfg') and (Lowercase(ExtractFileName(Candidate)) = 'csgo') then
      Result := Candidate;
  end;
end;

function ExtractQuotedValue(const Line, KeyName: string): string;
var
  Trimmed, SearchKey: string;
  P, Q1, Q2: Integer;
begin
  Result := '';
  Trimmed := Trim(Line);
  SearchKey := '"' + KeyName + '"';
  P := Pos(SearchKey, Trimmed);
  if P = 0 then
    Exit;
  Delete(Trimmed, 1, P + Length(SearchKey) - 1);
  Trimmed := Trim(Trimmed);
  Q1 := Pos('"', Trimmed);
  if Q1 = 0 then
    Exit;
  Delete(Trimmed, 1, Q1);
  Q2 := Pos('"', Trimmed);
  if Q2 = 0 then
    Exit;
  Result := Copy(Trimmed, 1, Q2 - 1);
  StringChangeEx(Result, '\\', '\', True);
end;

function DetectFromVdf(const VdfPath: string): string;
var
  Lines: TArrayOfString;
  I: Integer;
  CurrentLib, FoundFallback, Candidate: string;
  CurrentHasCS2: Boolean;
begin
  Result := '';
  FoundFallback := '';
  if not FileExists(VdfPath) then
    Exit;
  if not LoadStringsFromFile(VdfPath, Lines) then
    Exit;

  CurrentLib := '';
  CurrentHasCS2 := False;
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    if Pos('"path"', Lines[I]) > 0 then
    begin
      if (CurrentLib <> '') and CurrentHasCS2 then
      begin
        Candidate := NormalizeCS2Candidate(CurrentLib + '\steamapps\common\Counter-Strike Global Offensive');
        if Candidate <> '' then
        begin
          Result := Candidate;
          Exit;
        end;
      end;
      CurrentLib := ExtractQuotedValue(Lines[I], 'path');
      CurrentHasCS2 := False;
      if (CurrentLib <> '') and (FoundFallback = '') then
        FoundFallback := NormalizeCS2Candidate(CurrentLib + '\steamapps\common\Counter-Strike Global Offensive');
    end
    else if Pos('"730"', Lines[I]) > 0 then
      CurrentHasCS2 := True;
  end;

  if (CurrentLib <> '') and CurrentHasCS2 then
  begin
    Candidate := NormalizeCS2Candidate(CurrentLib + '\steamapps\common\Counter-Strike Global Offensive');
    if Candidate <> '' then
    begin
      Result := Candidate;
      Exit;
    end;
  end;

  Result := FoundFallback;
end;

function DetectCS2Dir(): string;
var
  CliOverride, SteamPath, Candidate: string;
  Fallbacks: array[0..3] of string;
  I: Integer;
begin
  Result := '';

  CliOverride := ExpandConstant('{param:CS2DIR|}');
  if CliOverride <> '' then
  begin
    Candidate := NormalizeCS2Candidate(CliOverride);
    if Candidate <> '' then
      Result := Candidate
    else
      Result := CliOverride;
    Exit;
  end;

  if RegQueryStringValue(HKCU, 'Software\Valve\Steam', 'SteamPath', SteamPath) then
  begin
    StringChangeEx(SteamPath, '/', '\', True);
    Candidate := DetectFromVdf(RemoveBackslashUnlessRoot(SteamPath) + '\steamapps\libraryfolders.vdf');
    if Candidate <> '' then
    begin
      Result := Candidate;
      Exit;
    end;
  end;

  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath', SteamPath) then
  begin
    Candidate := DetectFromVdf(RemoveBackslashUnlessRoot(SteamPath) + '\steamapps\libraryfolders.vdf');
    if Candidate <> '' then
    begin
      Result := Candidate;
      Exit;
    end;
  end;

  Fallbacks[0] := 'D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo';
  Fallbacks[1] := 'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo';
  Fallbacks[2] := 'C:\Program Files\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo';
  Fallbacks[3] := 'D:\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo';

  for I := 0 to 3 do
  begin
    Candidate := NormalizeCS2Candidate(Fallbacks[I]);
    if Candidate <> '' then
    begin
      Result := Candidate;
      Exit;
    end;
  end;
end;

procedure InitializeWizard();
begin
  DetectedCS2Dir := DetectCS2Dir();
  CS2DirPage := CreateInputDirPage(
    wpSelectTasks,
    'Localizar Counter-Strike 2',
    'Selecione a pasta do Counter-Strike 2 para configurar o arquivo GSI',
    'O instalador detecta automaticamente suas bibliotecas Steam. ' +
    'Confirme o caminho abaixo (pasta "...\game\csgo" ou raiz do CS2) ou selecione manualmente caso necessário.'#13#10 +
    'Nenhum arquivo executável do CS2 será alterado — apenas gamestate_integration_cs2rgbsync.cfg será instalado em cfg.',
    False,
    ''
  );
  CS2DirPage.Add('Pasta do Counter-Strike 2:');
  CS2DirPage.Values[0] := DetectedCS2Dir;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = CS2DirPage.ID then
  begin
    if not WizardIsTaskSelected('setupgsi') then
      Result := True;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Normalized: string;
begin
  Result := True;
  if CurPageID = CS2DirPage.ID then
  begin
    if Trim(CS2DirPage.Values[0]) = '' then
    begin
      if MsgBox(
        'Nenhuma pasta do CS2 foi informada. Deseja continuar e configurar o arquivo GSI depois pelo aplicativo?',
        mbConfirmation, MB_YESNO
      ) = IDNO then
        Result := False;
      Exit;
    end;
    Normalized := NormalizeCS2Candidate(CS2DirPage.Values[0]);
    if Normalized = '' then
    begin
      MsgBox(
        'A pasta selecionada não contém "game\csgo\cfg" válido do Counter-Strike 2. ' +
        'Selecione "...\Counter-Strike Global Offensive\game\csgo" ou deixe em branco para configurar depois.',
        mbError, MB_OK
      );
      Result := False;
      Exit;
    end;
    CS2DirPage.Values[0] := Normalized;
  end;
end;

function GetCS2Dir(Param: string): string;
begin
  if CS2DirPage <> nil then
    Result := Trim(CS2DirPage.Values[0])
  else
    Result := DetectedCS2Dir;
end;

function HasValidCS2Dir(): Boolean;
begin
  Result := NormalizeCS2Candidate(GetCS2Dir('')) <> '';
end;

function GetSetupGsiArgs(Param: string): string;
var
  Cs2Dir, ConfigPathParam: string;
begin
  Cs2Dir := NormalizeCS2Candidate(GetCS2Dir(''));
  Result := '--setup-gsi "' + Cs2Dir + '"';
  ConfigPathParam := ExpandConstant('{param:CONFIGPATH|}');
  if ConfigPathParam <> '' then
    Result := Result + ' --config-path "' + ConfigPathParam + '"';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  SavedCs2Dir, CfgFile: string;
  Content: AnsiString;
begin
  if CurUninstallStep = usUninstall then
  begin
    if RegQueryStringValue(HKCU, 'Software\CS2RGBSync\Install', 'CS2Dir', SavedCs2Dir) then
    begin
      CfgFile := RemoveBackslashUnlessRoot(SavedCs2Dir) + '\cfg\gamestate_integration_cs2rgbsync.cfg';
      if FileExists(CfgFile) and LoadStringFromFile(CfgFile, Content) then
      begin
        if Pos('Managed by CS2 RGB Sync', string(Content)) > 0 then
        begin
          if not UninstallSilent then
          begin
            if MsgBox(
              'Deseja remover o arquivo de configuração GSI criado pelo CS2 RGB Sync?'#13#10 +
              CfgFile + #13#10#13#10 +
              '(Suas configurações pessoais em AppData e o Corsair iCUE não serão alterados.)',
              mbConfirmation, MB_YESNO
            ) = IDYES then
              DeleteFile(CfgFile);
          end;
        end;
      end;
    end;
  end;
end;
