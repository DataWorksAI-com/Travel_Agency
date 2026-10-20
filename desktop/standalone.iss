#ifndef StageDir
  #error StageDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
[Setup]
AppId={{8E57C672-A26C-42CA-96C1-FC2719A2F173}
AppName=Travel Agency Standalone
AppVersion=1.0.1
AppPublisher=Travel Agency Project
DefaultDirName={localappdata}\Programs\TravelAgencyStandalone
DefaultGroupName=Travel Agency Standalone
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir={#OutputDir}
OutputBaseFilename=TravelAgency-English-1.0.1-Setup
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=yes
DiskSliceSize=2000000000
SlicesPerDisk=1
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\TravelAgency.exe
CloseApplications=yes
SetupLogging=yes
LicenseFile={#StageDir}\THIRD-PARTY-NOTICES.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#StageDir}\*.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\*.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\*.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\app\*"; DestDir: "{app}\app"; Excludes: "*.pyc,__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\runtime\*"; DestDir: "{app}\runtime"; Excludes: "*.pyc,__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\browser\*"; DestDir: "{app}\browser"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\engine\*"; DestDir: "{app}\engine"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\models\*"; DestDir: "{app}\models"; Flags: ignoreversion nocompression

[Icons]
Name: "{userprograms}\Travel Agency Standalone"; Filename: "{app}\TravelAgency.exe"
Name: "{userdesktop}\Travel Agency Standalone"; Filename: "{app}\TravelAgency.exe"

[Run]
Filename: "{app}\TravelAgency.exe"; Description: "Launch Travel Agency"; Flags: nowait postinstall skipifsilent
