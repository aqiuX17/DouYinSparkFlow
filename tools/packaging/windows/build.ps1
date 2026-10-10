param(
    [string]$Python = 'python',
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [string]$BrowserSource = '',
    [string]$GostSource = ''
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$out = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $out) { throw 'OutputRoot must be a fresh directory, to avoid packaging private state.' }
New-Item -ItemType Directory -Path $out | Out-Null
function Run-Checked([string]$program, [string[]]$arguments) {
    & $program @arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $program" }
}
Push-Location $repo
try {
    Run-Checked $Python @('-c', 'import PyInstaller, playwright, cloakbrowser, openai')
    Push-Location 'app\web\ui'
    try { Run-Checked 'npm.cmd' @('ci'); Run-Checked 'npm.cmd' @('run','build') } finally { Pop-Location }
    if (-not $BrowserSource) {
        $url = 'https://github.com/CloakHQ/CloakBrowser/releases/download/chromium-v146.0.7680.177.5/cloakbrowser-windows-x64.zip'
        Invoke-WebRequest -Uri $url -OutFile (Join-Path $out 'browser.zip')
        Expand-Archive -LiteralPath (Join-Path $out 'browser.zip') -DestinationPath (Join-Path $out 'browser-extract')
        $chrome = Get-ChildItem (Join-Path $out 'browser-extract') -Recurse -Filter chrome.exe | Select-Object -First 1
        if (-not $chrome) { throw 'Browser download has no chrome.exe' }
        $BrowserSource = $chrome.DirectoryName
    }
    $BrowserSource = (Resolve-Path -LiteralPath $BrowserSource).Path
    if (-not (Test-Path -LiteralPath (Join-Path $BrowserSource 'chrome.exe'))) { throw 'BrowserSource must contain chrome.exe' }
    if (-not $GostSource) {
        Invoke-WebRequest -Uri 'https://github.com/go-gost/gost/releases/download/v3.3.0/gost_3.3.0_windows_amd64.zip' -OutFile (Join-Path $out 'gost.zip')
        Expand-Archive -LiteralPath (Join-Path $out 'gost.zip') -DestinationPath (Join-Path $out 'gost-extract')
        $gost = Get-ChildItem (Join-Path $out 'gost-extract') -Recurse -Filter gost.exe | Select-Object -First 1
        if (-not $gost) { throw 'Gost download has no gost.exe' }
        $GostSource = $gost.FullName
    }
    $GostSource = (Resolve-Path -LiteralPath $GostSource).Path
    $pi = @('-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','DouyinSparkFlow','--icon',(Join-Path $repo 'app\logo.ico'),
        '--hidden-import','cloakbrowser','--hidden-import','geoip2',
        '--hidden-import','geoip2.database','--hidden-import','maxminddb','--hidden-import','socksio',
        '--collect-all','cloakbrowser','--collect-all','playwright','--collect-all','dotenv',
        '--add-data',((Join-Path $repo 'app\web\dist') + ';app\web\dist'),
        '--distpath',(Join-Path $out 'dist'),'--workpath',(Join-Path $out 'build'),
        '--specpath',$out,(Join-Path $repo 'main.py'))
    Run-Checked $Python $pi
    $bundle = Join-Path $out 'dist\DouyinSparkFlow'
    Copy-Item -LiteralPath $BrowserSource -Destination (Join-Path $bundle 'cloakbrowser-windows-x64') -Recurse
    New-Item -ItemType Directory -Path (Join-Path $bundle 'gost') | Out-Null
    Copy-Item -LiteralPath $GostSource -Destination (Join-Path $bundle 'gost\gost.exe')
    foreach ($file in @('README.md','LICENSE','VERSION','.env.example')) { Copy-Item -LiteralPath $file -Destination $bundle }
    Copy-Item -LiteralPath 'docs' -Destination $bundle -Recurse
    $version = (Get-Content -LiteralPath 'VERSION' -Raw).Trim()
    $zip = Join-Path $out "DouyinSparkFlow-$version-win-x64.zip"
    Run-Checked $Python @('-c', 'import shutil,sys;shutil.make_archive(sys.argv[1],"zip",root_dir=sys.argv[2],base_dir="DouyinSparkFlow")', $zip.Substring(0,$zip.Length-4), (Join-Path $out 'dist'))
    Get-FileHash -LiteralPath $zip -Algorithm SHA256 | Format-List
    Write-Output "PACKAGE=$zip"
} finally { Pop-Location }
