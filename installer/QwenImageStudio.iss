; ============================================================
; QwenImageStudio Inno Setup 脚本
; - 支持「升级覆盖安装」：同 AppId，安装时保留用户数据目录
; - 生成 setup exe
; ============================================================

#define MyAppName "QwenImageStudio"
#define MyAppNameZh "Qwen 镜像工坊"
#define MyAppVersion GetEnv("APP_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppPublisher "FiresonZ"
#define MyAppExeName "QwenImageStudio.exe"
#define MyAppURL "https://github.com/FiresonZ"

[Setup]
AppId={{8C1F5B7E-9D2A-4C6B-B0F3-QWENIMGSTUDIO}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppContact=dev@gith.uk
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppNameZh}
UninstallDisplayName={#MyAppNameZh}
UninstallDisplayIcon={app}\{#MyAppExeName}
; 升级覆盖安装：不卸载旧版本数据，直接覆盖程序文件
UsePreviousAppDir=yes
DirExistsWarning=no
AppendDefaultDirName=yes
AllowNoIcons=yes
OutputDir=dist\installer
OutputBaseFilename=QwenImageStudio-Setup-{#MyAppVersion}
SetupIconFile=assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
; 用户数据（模型/输出/配置）在 %LOCALAPPDATA%\QwenImageStudio，卸载时默认保留
UninstallFilesDir={app}\uninst

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "dist\QwenImageStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs replacesameversion

[Icons]
Name: "{group}\{#MyAppNameZh}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppNameZh}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppNameZh}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppNameZh}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 仅清理程序目录，不动 %LOCALAPPDATA% 用户数据（模型、作品保留）
Type: filesandordirs; Name: "{app}\uninst"

[Messages]
WelcomeLabel2=这将安装 [name/ver]。%n%n支持升级覆盖安装：直接运行新版安装包即可，已下载的模型与生成作品将完整保留。
