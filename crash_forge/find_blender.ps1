# find_blender.ps1 - resolves a Blender executable path for run_probe.bat.
#
# Checked in order: the blendfile file-association command in the
# registry, then C:\Program Files\Blender Foundation\Blender */blender.exe
# (newest version-looking folder first), then the Steam install location,
# then the WindowsApps execution-alias folder. Prints exactly one path to
# stdout on success, nothing on failure - run_probe.bat treats empty
# output as "not found".

$candidates = @()

try {
    $key = Get-ItemProperty -Path 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\blendfile\shell\open\command' -ErrorAction Stop
    $value = $key.'(default)'
    if ($value) {
        if ($value -match '"([^"]+)"') {
            # Typical form: "C:\...\blender.exe" "%1"
            $candidates += $Matches[1]
        } else {
            # Unquoted form (only safe when the path has no spaces):
            # C:\...\blender.exe "%1"
            $exePart = ($value -split '\.exe', 2)[0] + '.exe'
            $candidates += $exePart.Trim()
        }
    }
} catch {}

$candidates += Get-ChildItem -Path 'C:\Program Files\Blender Foundation' -Filter 'Blender *' -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName 'blender.exe' }

$candidates += Get-ChildItem -Path 'C:\Program Files (x86)\Steam\steamapps\common\Blender' -Filter 'blender.exe' -Recurse -ErrorAction SilentlyContinue |
    ForEach-Object { $_.FullName }

$candidates += Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps') -Filter 'blender.exe' -ErrorAction SilentlyContinue |
    ForEach-Object { $_.FullName }

$found = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1

if ($found) {
    Write-Output $found
}
