param(
    [string]$ListFile = (Join-Path $PSScriptRoot '记录\男同名单.txt'),
    [string]$Quarantine = (Join-Path $PSScriptRoot '..\_已删除_男同'),
    [switch]$Apply,
    [switch]$Purge
)

$roots = @(
    (Join-Path $PSScriptRoot '..\校对后文章'),
    (Join-Path $PSScriptRoot '..\原文'),
    (Join-Path $PSScriptRoot '..\归档\备份_整合前'),
    (Join-Path $PSScriptRoot '..\归档\重复_根级')
)

if ($Purge) {
    if (Test-Path -LiteralPath $Quarantine) {
        $c = (Get-ChildItem -LiteralPath $Quarantine -Recurse -File).Count
        Remove-Item -LiteralPath $Quarantine -Recurse -Force
        "已清空隔离目录（$c 个文件）: $Quarantine"
    } else { "隔离目录不存在: $Quarantine" }
    return
}

if (-not (Test-Path -LiteralPath $ListFile)) { "名单不存在: $ListFile"; return }
$keys = Get-Content -LiteralPath $ListFile -Encoding UTF8 |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith('#') }
if ($keys.Count -eq 0) { "名单为空，无需处理。"; return }

$log = Join-Path $PSScriptRoot '记录\男同删除.csv'
$rows = @()
foreach ($k in $keys) {
    foreach ($r in $roots) {
        if (-not (Test-Path -LiteralPath $r)) { continue }
        $hits = Get-ChildItem -LiteralPath $r -Recurse -File -Filter *.txt |
            Where-Object { $_.Name -like "*$k*" }
        foreach ($h in $hits) {
            $rel = $h.FullName.Substring($r.Length).TrimStart('\')
            $dst = Join-Path $Quarantine (Split-Path $r -Leaf)
            $dst = Join-Path $dst $rel
            if ($Apply) {
                $dstDir = Split-Path $dst -Parent
                if (-not (Test-Path -LiteralPath $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
                Move-Item -LiteralPath $h.FullName -Destination $dst -Force
                $rows += [pscustomobject]@{ Time = (Get-Date).ToString('s'); Key = $k; From = $h.FullName; To = $dst }
            } else {
                "DRY  $k  ->  $($h.FullName)"
            }
        }
    }
}
if ($Apply -and $rows.Count -gt 0) {
    $rows | Export-Csv -LiteralPath $log -NoTypeInformation -Encoding UTF8 -Append
    "已移入隔离目录：$($rows.Count) 个文件 -> $Quarantine"
    "接着跑：重建清单.ps1 -> 校验.ps1 -> 索引.ps1"
}
if ($Apply -and $rows.Count -eq 0) { "名单内无匹配文件。" }
