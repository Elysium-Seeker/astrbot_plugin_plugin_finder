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

    $prepareOutput = & $python @prepareArgs
    if ($prepareOutput) {
        $prepareOutput | ForEach-Object { Write-Output $_ }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "release_prepare.py failed"
    }

    $version = ""
    foreach ($line in $prepareOutput) {
        if ($line -match '^release_prepared v([0-9]+\.[0-9]+\.[0-9]+)$') {
            $version = $Matches[1]
            break
        }
    }

    if (-not $version) {
        foreach ($line in Get-Content "metadata.yaml") {
            if ($line -match '^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$') {
                $version = $Matches[1]
                break
            }
        }
    }

    if (-not $version) {
        throw "cannot parse version from metadata.yaml"
    }

    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Output "release_push_no_changes"
        exit 0
    }

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
