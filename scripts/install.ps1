<#
.SYNOPSIS
Installs the nubor client on Windows.

.DESCRIPTION
Downloads the published archive for this platform, verifies it against the
release checksums, installs it under %USERPROFILE%\.nubor and puts it on PATH.

    .\install.ps1
    .\install.ps1 -Version 0.3.0

Re-running upgrades in place and is safe.
#>
[CmdletBinding()]
param(
    [string]$Version,
    [string]$Repo   = $(if ($env:NUBOR_REPO) { $env:NUBOR_REPO } else { 'nubor-net/nubor-cli' }),
    [string]$Prefix = $(if ($env:NUBOR_HOME) { $env:NUBOR_HOME } else { Join-Path $HOME '.nubor' })
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$api = 'https://api.github.com'
$tmp = $null

function Fail([string]$Message) { Write-Error $Message; exit 1 }

try {
    # --- platform ----------------------------------------------------------
    if ([Environment]::Is64BitOperatingSystem -ne $true) {
        Fail 'Only 64-bit Windows is supported.'
    }
    $target = 'windows-x86_64'

    # --- resolve the release ----------------------------------------------
    $releaseUrl = if ($Version) {
        "$api/repos/$Repo/releases/tags/v$($Version -replace '^v', '')"
    } else {
        "$api/repos/$Repo/releases/latest"
    }

    try {
        $release = Invoke-RestMethod -Uri $releaseUrl -Headers @{ Accept = 'application/vnd.github+json' }
    } catch {
        Fail "Could not read the release from $Repo. Check that the version exists."
    }

    $tag = $release.tag_name
    if (-not $tag) { Fail 'Could not determine the release tag.' }
    $resolved = $tag -replace '^v', ''

    # The version becomes a directory name that is later removed recursively,
    # so constrain it before it reaches a path.
    if ($resolved -notmatch '^[0-9A-Za-z][0-9A-Za-z.+-]*$') {
        Fail "Refusing to use '$resolved' as a version: unexpected characters."
    }

    $archive = "nubor-$resolved-$target.zip"
    Write-Host "Installing nubor $resolved ($target)"

    $tmp = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid()))

    function Get-Asset([string]$Name, [string]$Destination) {
        $asset = $release.assets | Where-Object { $_.name -eq $Name }
        if (-not $asset) { Fail "Release $tag has no asset named $Name." }
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $Destination
    }

    $archivePath = Join-Path $tmp $archive
    $sumsPath    = Join-Path $tmp 'SHA256SUMS'
    Get-Asset $archive $archivePath
    Get-Asset 'SHA256SUMS' $sumsPath

    # --- verify ------------------------------------------------------------
    # SHA256SUMS covers every platform, so match this archive's line rather than
    # verifying the whole file, which would fail on the archives not downloaded.
    $actual = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLower()
    $expected = $null
    foreach ($line in Get-Content $sumsPath) {
        $parts = $line -split '\s+', 2
        if ($parts.Count -eq 2 -and ($parts[1].TrimStart('*').Trim()) -eq $archive) {
            $expected = $parts[0].ToLower()
            break
        }
    }
    if (-not $expected) { Fail "SHA256SUMS has no entry for $archive." }
    if ($actual -ne $expected) {
        Fail "Checksum mismatch for $archive.`n  expected $expected`n  actual   $actual`nRefusing to install."
    }
    Write-Host 'Checksum verified.'

    # --- install -----------------------------------------------------------
    $dest = Join-Path (Join-Path $Prefix 'versions') $resolved
    $bin  = Join-Path $Prefix 'bin'
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    New-Item -ItemType Directory -Force -Path $dest, $bin | Out-Null

    Expand-Archive -Path $archivePath -DestinationPath $dest -Force
    $exe = Join-Path $dest 'nubor.exe'
    if (-not (Test-Path $exe)) { Fail 'Archive did not contain the expected binary.' }

    # Run the new binary before it becomes the current one. On an upgrade this
    # keeps a working install in place if the downloaded build is broken.
    & $exe --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail 'The downloaded binary did not run; leaving the existing installation untouched.'
    }

    # Windows has no dependable symlink without elevation, so the stable entry
    # point is a shim that forwards to the versioned binary.
    $shim = Join-Path $bin 'nubor.cmd'
    "@echo off`r`n`"$exe`" %*" | Set-Content -Path $shim -Encoding ASCII
    Write-Host "Installed to $shim"

    # --- PATH --------------------------------------------------------------
    # Read the raw registry value rather than [Environment]::GetEnvironmentVariable,
    # which expands %VAR% and would write the expansions back permanently.
    # setx is avoided entirely: it truncates PATH at 1024 characters.
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
    try {
        $rawPath = $key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $kind    = $key.GetValueKind('Path')
    } catch {
        $rawPath = ''
        $kind    = [Microsoft.Win32.RegistryValueKind]::ExpandString
    }

    $entries = @($rawPath -split ';' | Where-Object { $_ -ne '' })
    if ($entries -contains $bin) {
        Write-Host "PATH already contains $bin"
    } else {
        $new = (@($entries) + $bin) -join ';'
        $key.SetValue('Path', $new, $kind)
        Write-Host "Added $bin to your user PATH"
    }
    $key.Close()

    Write-Host ''
    Write-Host "Open a new terminal, or run: `$env:Path = `"$bin;`$env:Path`""
    Write-Host ''
    Write-Host 'To enable command completion, add to your PowerShell profile:'
    Write-Host '  $env:_NUBOR_COMPLETE = "powershell_source"; nubor | Out-String | Invoke-Expression'
    Write-Host ''
    Write-Host "Run 'nubor --help' to get started."
}
finally {
    if ($tmp -and (Test-Path $tmp)) { Remove-Item -Recurse -Force $tmp }
}
