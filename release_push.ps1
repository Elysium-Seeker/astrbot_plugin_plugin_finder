param(
    [Parameter(Mandatory = $true)]
    [string[]]$Change,

    [string]$Version = "",
    [string]$Remote = "origin",
    [string]$Branch = "master"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $repoRoot
try {
    $python = Join-Path $repoRoot ".venv/Scripts/python.exe"
    if (-not (Test-Path $python)) {
        $python = "python"
    }

    $prepareArgs = @("release_prepare.py")
    if ($Version) {
        $prepareArgs += @("--version", $Version)
    }
    foreach ($item in $Change) {
        $prepareArgs += @("--change", $item)
    }

    & $python @prepareArgs
    if ($LASTEXITCODE -ne 0) {
        throw "release_prepare.py 执行失败。"
    }

    $version = (& $python -c "import pathlib, re; t=pathlib.Path('metadata.yaml').read_text(encoding='utf-8'); m=re.search(r'^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$', t, re.M); print(m.group(1) if m else '')").Trim()
    if (-not $version) {
        throw "无法从 metadata.yaml 读取版本号。"
    }

    git add main.py metadata.yaml README.md CHANGELOG.md release_prepare.py release_push.ps1
    git commit -m "chore(release): v$version"

    $tag = "v$version"
    git tag -a $tag -m $tag
    git push $Remote $Branch
    git push $Remote $tag

    Write-Output "release_push_ok $tag"
}
finally {
    Pop-Location
}
