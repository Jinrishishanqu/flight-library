# 补源.ps1 —— 给清单里没有来源的行，回到 原文\ 按作品名找回备份源
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$man  = Join-Path (Join-Path $PSScriptRoot '记录') '校对清单.csv'
$srcRoot = Join-Path $root '原文'

$rows = Import-Csv $man
$pool = Get-ChildItem -LiteralPath $srcRoot -Recurse -File -Filter *.txt
$fixed = 0

foreach ($r in $rows) {
    if ($r.Sources) { continue }
    $leaf = Split-Path $r.Output -Leaf
    $title = $leaf -replace '^《', '' -replace '》-\S*-\S*\.txt$', ''
    $stem  = ($title -split '[（(]')[0]

    $cand = @($pool | Where-Object { $_.BaseName -eq $title })
    if ($cand.Count -eq 0) { $cand = @($pool | Where-Object { $_.BaseName -like ($stem + '*') }) }
    if ($cand.Count -eq 0) { $cand = @($pool | Where-Object { $_.BaseName -like ('*' + $stem + '*') }) }
    if ($cand.Count -eq 1) {
        $r.Sources = $cand[0].FullName
        $fixed++
        "SRC  {0}  <- {1}" -f $leaf, $cand[0].Name
    } elseif ($cand.Count -gt 1) {
        "AMB  {0}  ({1} 个候选)" -f $leaf, $cand.Count
    } else {
        "NON  {0}" -f $leaf
    }
}

if ($fixed -gt 0) {
    $rows | Export-Csv $man -NoTypeInformation -Encoding utf8BOM
    "已补来源 {0} 条" -f $fixed
}
