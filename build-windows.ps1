param(
    [string]$PythonExecutable = (Join-Path $PSScriptRoot ".venv/Scripts/python.exe"),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot ("dist/release-" + (Get-Date -Format "yyyyMMdd-HHmmss"))),
    [ValidateSet("full", "edge")]
    [string]$Profile = "full",
    [string]$FFmpegDirectory = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path $PSScriptRoot).Path
$python = (Resolve-Path -LiteralPath $PythonExecutable).Path
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputRoot) {
    throw "Use a new output directory. Existing builds are preserved: $outputRoot"
}

# Fail before creating output if the selected build runtime is incomplete.
$preflight = @'
import struct
import sys
import tkinter
import PyInstaller

if sys.platform != "win32" or struct.calcsize("P") != 8:
    raise RuntimeError("Build on Windows x64 with 64-bit Python.")
'@
if ($Profile -eq "full") {
    $preflight += "`n" + @'
if not (3, 10) <= sys.version_info[:2] < (3, 14):
    raise RuntimeError("The full CPU profile requires Python 3.10-3.13.")
import kokoro_onnx
import piper
import onnxruntime
'@
}
& $python -c $preflight
if ($LASTEXITCODE -ne 0) {
    throw "Build prerequisites failed. Full builds require Windows x64 Python 3.10-3.13 and requirements-build.txt."
}
if ($FFmpegDirectory) {
    $toolRoot = (Resolve-Path -LiteralPath $FFmpegDirectory).Path
    foreach ($name in @("ffmpeg.exe", "ffprobe.exe", "LICENSE.txt", "source.txt")) {
        if (-not (Test-Path -LiteralPath (Join-Path $toolRoot $name) -PathType Leaf)) {
            throw "Bundled media tools require $name in $toolRoot."
        }
    }
}

New-Item -ItemType Directory -Path $outputRoot | Out-Null
$distRoot = Join-Path $outputRoot "dist"
$distribution = Join-Path $distRoot "WindowsTTSApp"
$archive = Join-Path $outputRoot "WindowsTTSApp-windows-x64.zip"
$arguments = @(
    "-m", "PyInstaller", "--windowed", "--onedir", "--noupx",
    "--distpath", $distRoot, "--workpath", (Join-Path $outputRoot "work"),
    "--specpath", $outputRoot, "--name", "WindowsTTSApp",
    "--additional-hooks-dir", (Join-Path $repoRoot "build_hooks"),
    "--add-data", "$(Join-Path $repoRoot 'ttsapp/models/piper_english.json');ttsapp/models",
    "--exclude-module", "torch", "--exclude-module", "tensorflow",
    "--exclude-module", "pytest", "--exclude-module", "onnx"
)
if ($Profile -eq "full") {
    foreach ($package in @("kokoro_onnx", "espeakng_loader", "phonemizer")) {
        $arguments += @("--collect-all", $package)
    }
} else {
    foreach ($package in @("kokoro_onnx", "piper", "espeakng_loader", "phonemizer", "onnxruntime", "numpy")) {
        $arguments += @("--exclude-module", $package)
    }
}
$arguments += "app.py"
Push-Location $repoRoot
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE. Partial output retained at $outputRoot."
    }
    $executable = Join-Path $distribution "WindowsTTSApp.exe"
    if (-not (Test-Path -LiteralPath $executable)) {
        throw "PyInstaller did not produce $executable."
    }
    & $python -m scripts.package_notices --output $distribution --profile $Profile
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency notices could not be generated."
    }
    if ($FFmpegDirectory) {
        $tools = Join-Path $distribution "tools"
        New-Item -ItemType Directory -Path $tools | Out-Null
        $hashes = @{}
        foreach ($name in @("ffmpeg.exe", "ffprobe.exe", "LICENSE.txt", "source.txt")) {
            Copy-Item -LiteralPath (Join-Path $toolRoot $name) -Destination $tools
            if ($name.EndsWith(".exe")) {
                $hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $tools $name) -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
        $hashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $tools "sha256.json") -Encoding utf8
    }
    $inventory = @{
        profile = $Profile
        built_utc = [DateTime]::UtcNow.ToString("o")
        bundled_media = [bool]$FFmpegDirectory
        models_included = $false
    }
    $inventory | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $distribution "build-info.json") -Encoding utf8
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($distribution, $archive, [System.IO.Compression.CompressionLevel]::Optimal, $true)
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $archiveFiles = @($zip.Entries | Where-Object { -not $_.FullName.EndsWith("/") }).Count
        $sourceFiles = @(Get-ChildItem -LiteralPath $distribution -File -Recurse).Count
        if ($archiveFiles -ne $sourceFiles) {
            throw "Archive file count mismatch."
        }
        if (-not ($zip.Entries | Where-Object { $_.FullName -eq "WindowsTTSApp/_internal/base_library.zip" })) {
            throw "Archive is missing the Python base library."
        }
        if ($zip.Entries | Where-Object { $_.FullName -match "\.(onnx|bin)$" }) {
            throw "Model assets must remain outside the package."
        }
    } finally {
        $zip.Dispose()
    }
    (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash | Set-Content -LiteralPath ($archive + ".sha256") -Encoding ascii
    Write-Output "Created $archive"
} finally {
    Pop-Location
}
