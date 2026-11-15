# 查同书.ps1 —— 扫「疑似同一部长篇被拆成多篇」的候选（供人工确认后写进 families.psd1）
param(
    [int]$MinPrefix = 5
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$src  = Join-Path $root '校对后文章'

function Get-Stem([string]$leaf) {
    $t = $leaf -replace '^《', '' -replace '》-\S*-\S*\.txt$', ''
    $t = $t -replace '[（(][^）)]*字数[^）)]*[）)]', ''
    $t = $t -replace '[（(]\d+[^）)]*[）)]$', ''
    return $t.Trim()
}

$rows = @()
foreach ($d in Get-ChildItem -LiteralPath $src -Directory) {
    $files = Get-ChildItem -LiteralPath $d.FullName -File -Filter *.txt
    $map = @{}
    foreach ($f in $files) { $map[$f.Name] = Get-Stem $f.Name }

    # 两两比较：主标题互为前缀（≥MinPrefix 字）或首 MinPrefix 字相同
    $names = @($map.Keys)
    for ($i = 0; $i -lt $names.Count; $i++) {
        for ($j = $i + 1; $j -lt $names.Count; $j++) {
            $a = $map[$names[$i]]; $b = $map[$names[$j]]
            if ($a.Length -lt $MinPrefix -or $b.Length -lt $MinPrefix) { continue }
            $short = if ($a.Length -le $b.Length) { $a } else { $b }
            $long = if ($a.Length -le $b.Length) { $b } else { $a }
            $common = 0
            $n = [Math]::Min($a.Length, $b.Length)
            while ($common -lt $n -and $a[$common] -eq $b[$common]) { $common++ }
            if ($common -ge $MinPrefix) {
                $rows += [pscustomobject]@{ Dir = $d.Name; Common = $common; A = $names[$i]; B = $names[$j] }
            }
        }
    }
}

$rows = $rows | Sort-Object Dir, @{Expression = 'Common'; Descending = $true }
"候选对：{0}" -f $rows.Count
$rows | Select-Object -First 80 | Format-Table -AutoSize | Out-String -Width 200
if ($rows.Count -gt 0) {
    $csv = Join-Path (Join-Path $PSScriptRoot '记录') '同书候选.csv'
    $rows | Export-Csv $csv -NoTypeInformation -Encoding utf8BOM
    "报告：$csv"
}
