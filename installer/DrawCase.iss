; ============================================================
; DrawCase Inno Setup 脚本
; - 支持「升级覆盖安装」：同 AppId，安装时保留用户数据目录
; - 生成 setup exe
; ============================================================

#define MyAppName "DrawCase"
#define MyAppVersion GetEnv("APP_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppPublisher "FiresonZ"
#define MyAppExeName "DrawCase.exe"
#define MyAppURL "https://github.com/FiresonZ/DrawCase"

[Setup]
AppId={{8C1F5B7E-9D2A-4C6B-B0F3-DRAWCASE000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppContact=dev@gith.uk
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; 升级覆盖安装：不卸载旧版本数据，直接覆盖程序文件
UsePreviousAppDir=yes
DirExistsWarning=no
AppendDefaultDirName=yes
AllowNoIcons=yes
OutputDir=dist\installer
OutputBaseFilename=DrawCase-Setup-{#MyAppVersion}
SetupIconFile=assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
; 用户数据（依赖 runtime/输出/配置）在 %LOCALAPPDATA%\DrawCase，卸载时默认保留
UninstallFilesDir={app}\uninst

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "dist\DrawCase\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs replacesameversion

[Dirs]
; 内置模型文件夹：用户手动放入下载好的模型；升级覆盖与卸载都不删除
Name: "{app}\models\QwenImage"; Flags: uninsneveruninstall
Name: "{app}\models\SDXL"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 仅清理程序目录，不动 %LOCALAPPDATA% 用户数据（依赖 runtime、生成作品保留）
Type: filesandordirs; Name: "{app}\uninst"

[Messages]
WelcomeLabel2=这将安装 [name/ver]。%n%n支持升级覆盖安装：直接运行新版安装包即可，AI 依赖、模型文件夹与生成作品将完整保留。
