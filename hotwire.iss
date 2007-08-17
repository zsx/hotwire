[Setup]
AppName=hotwire
AppVerName=hotwire 0.556
AppPublisher=me
AppPublisherURL=http://submind.verbum.org/hotwire
DefaultDirName={pf}\hotwire
DefaultGroupName=hotwire
DisableProgramGroupPage=true
OutputBaseFilename=setup
Compression=lzma
SolidCompression=true
AllowUNCPath=false
VersionInfoVersion=1.0
VersionInfoCompany=me inc
VersionInfoDescription=hotwire

[Dirs]
Name: {app}; Flags: uninsalwaysuninstall;

[Files]
Source: dist\*; DestDir: {app}; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: {group}\hotwire; Filename: {app}\hotwire.exe; WorkingDir: {app}

[Run]
Filename: {app}\hotwire.exe; Description: {cm:LaunchProgram,hotwire}; Flags: nowait postinstall
