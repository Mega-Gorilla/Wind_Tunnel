param([switch]$Execute)
$ErrorActionPreference = 'Stop'
$projectPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$studyPath = [IO.Path]::GetFullPath($PSScriptRoot)
if ($studyPath -ne 'D:\codes\Wind_Tunnel\analysis\plate_cfd_20261019') { throw 'Unexpected study directory.' }
$manifestPath = Join-Path $projectPath 'Docs/tests/cfd/2026-10-19_fixed_plate_refined/results/cleanup_manifest.json'
if ($Execute -and (Test-Path -LiteralPath $manifestPath)) { throw 'Manifest already exists; do not repeat cleanup.' }
if (Get-Process simpleFoam,pimpleFoam -ErrorAction SilentlyContinue) { throw 'A native solver is running.' }

# Every removal is an exact file. No recursive deletion or shell-to-shell expansion.
$targets = [Collections.Generic.List[object]]::new()
function Add-Target([IO.FileInfo]$File, [string]$Reason) {
    $resolved = (Resolve-Path -LiteralPath $File.FullName).Path
    if (!$resolved.StartsWith($studyPath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Outside study: $resolved" }
    $ancestor = $File
    while ($ancestor.FullName -ne $studyPath) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse points are not allowed.' }
        $ancestor = if ($ancestor -is [IO.FileInfo]) { $ancestor.Directory } else { $ancestor.Parent }
    }
    $targets.Add([ordered]@{path=[IO.Path]::GetRelativePath($projectPath,$resolved).Replace('\','/');absolute_path=$resolved;bytes=$File.Length;reason=$Reason})
}
foreach ($caseName in @('fitted_A_empty','fitted_A_plate','fitted_C_plate')) {
    $meshPath = Join-Path $studyPath "cases/$caseName/constant/polyMesh"
    if (Test-Path -LiteralPath $meshPath) {
        Get-ChildItem -LiteralPath $meshPath -File -Recurse | ForEach-Object { Add-Target $_ 'Rejected, never solved mesh; metadata, input settings, and checkMesh log retained.' }
    }
}
foreach ($label in @('fitted_A','fitted_C','fitted_D')) {
    foreach ($name in @('section.msh','section.npz')) {
        $path = Join-Path $studyPath "meshes/$label/$name"
        if (Test-Path -LiteralPath $path) { Add-Target (Get-Item -LiteralPath $path) 'Rejected section mesh; generation source and metadata retained.' }
    }
}
for ($rank=0; $rank -lt 8; $rank++) {
    $rankPath = Join-Path $studyPath "cases/fitted_F_urans/processor$rank"
    foreach ($dir in Get-ChildItem -LiteralPath $rankPath -Directory) {
        $timeValue = 0.0
        if (![double]::TryParse($dir.Name,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$timeValue)) { continue }
        if ($timeValue -le 0.01 -or $timeValue -ge 0.01126998051) { continue }
        $files = @(Get-ChildItem -LiteralPath $dir.FullName -File -Recurse)
        if ($files.Count -ne 3 -or @($files | Where-Object { $_.Name -notin @('pMean','UMean','UPrime2Mean') -or $_.DirectoryName -ne $dir.FullName }).Count) { throw "Unexpected checkpoint contents: $($dir.FullName)" }
        foreach ($file in $files) { Add-Target $file 'Unadopted per-step startup averages only; initial and all complete checkpoints plus monitor series retained.' }
    }
}
$totalBytes = ($targets | ForEach-Object { $_.bytes } | Measure-Object -Sum).Sum
[pscustomobject]@{files=$targets.Count;bytes=$totalBytes;GiB=[math]::Round($totalBytes/1GB,3);execute=[bool]$Execute} | ConvertTo-Json
if (!$Execute) { return }
$records = [Collections.Generic.List[object]]::new()
foreach ($item in $targets) {
    $records.Add([ordered]@{path=$item.path;bytes=$item.bytes;sha256=(Get-FileHash -LiteralPath $item.absolute_path -Algorithm SHA256).Hash.ToLower();reason=$item.reason;deleted=$false})
}
$manifest = [ordered]@{date='2026-10-19';status='prepared';scope='Rejected meshes and unadopted mean-only intermediate outputs';backup_created=$false;recovery='Regenerate/recompute from retained source and inputs; deleted file bytes are not archived.';file_count=$records.Count;bytes=$totalBytes;files=$records}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
for ($i=0; $i -lt $targets.Count; $i++) {
    Remove-Item -LiteralPath $targets[$i].absolute_path -Force
    if (Test-Path -LiteralPath $targets[$i].absolute_path) { throw 'Removal verification failed.' }
    $records[$i].deleted=$true
}
# Remove only confirmed empty leaf directories of selected files, never project/case roots.
$emptyParents = $targets | ForEach-Object { [IO.Path]::GetDirectoryName($_.absolute_path) } | Sort-Object -Unique
foreach ($dir in $emptyParents) {
    if ((Test-Path -LiteralPath $dir) -and @(Get-ChildItem -LiteralPath $dir -Force).Count -eq 0) { Remove-Item -LiteralPath $dir }
}
$manifest.status='completed'
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output 'Completed. Essential fields, monitor data, input settings and logs were preserved.'
