param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$buildDir = Join-Path $projectDir 'build\desktop'
New-Item -ItemType Directory -Force -Path $buildDir, $OutputDirectory | Out-Null
$launcher = Join-Path $buildDir 'TravelAgency.exe'
& $compiler /nologo /target:winexe /platform:anycpu /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Net.Http.dll /out:$launcher (Join-Path $PSScriptRoot 'TravelAgency.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
$projectConfig = Join-Path $buildDir 'project-path.txt'
Set-Content -LiteralPath $projectConfig -Value $projectDir -Encoding UTF8
$setup = Join-Path $OutputDirectory 'TravelAgency-Setup.exe'
& $compiler /nologo /target:winexe /platform:anycpu /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:Microsoft.CSharp.dll "/resource:${launcher},TravelAgency.exe" "/resource:${projectConfig},project-path.txt" "/out:$setup" (Join-Path $PSScriptRoot 'Setup.cs')
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
Write-Output $setup
