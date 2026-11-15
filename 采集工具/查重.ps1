# 查重.ps1 —— 找出「正文实质重复」的文件（改名换标题的重复件）
#   pwsh -File 采集工具\查重.ps1            # 报告
#   pwsh -File 采集工具\查重.ps1 -Apply      # 把重复件（保留最长）移入 归档\重复_根级
param(
    [switch]$Apply,
    [double]$Threshold = 0.90
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$src  = Join-Path $root '校对后文章'
$rec  = Join-Path $PSScriptRoot '记录'

function Get-Body([string]$p) {
    $t = [IO.File]::ReadAllText($p).TrimStart([char]0xFEFF)
    return ($t -replace '[\s　]', '')
}
function Get-Grams([string]$s, [int]$n = 5) {
    $set = New-Object 'System.Collections.Generic.HashSet[string]'
    if ($s.Length -lt $n) { [void]$set.Add($s); return ,$set }
    for ($i = 0; $i -le $s.Length - $n; $i++) { [void]$set.Add($s.Substring($i, $n)) }
    return ,$set
}
function Get-Jaccard($a, $b) {
    $inter = 0
    if ($a.Count -gt $b.Count) { $t = $a; $a = $b; $b = $t }
    foreach ($x in $a) { if ($b.Contains($x)) { $inter++ } }
    $union = $a.Count + $b.Count - $inter
    if ($union -eq 0) { return 0 }
    return [double]$inter / $union
}

$files = Get-ChildItem -LiteralPath $src -Recurse -File -Filter *.txt
$info = @()
foreach ($f in $files) {
    $b = Get-Body $f.FullName
    $info += [pscustomobject]@{
        Path = $f.FullName
        Dir  = $f.Directory.Name
        Name = $f.Name
        Len  = $b.Length
        Head = $b.Substring(0, [Math]::Min(120, $b.Length))
        _b   = $b
    }
}

# 先按正文前 120 字聚类（快筛），再对组内做 5-gram Jaccard 精确判定
$groups = $info | Group-Object Head | Where-Object Count -gt 1
$pairs  = @()
foreach ($g in $groups) {
    $arr = @($g.Group)
    for ($i = 0; $i -lt $arr.Count; $i++) {
        for ($j = $i + 1; $j -lt $arr.Count; $j++) {
            $a = $arr[$i]; $b = $arr[$j]
            $ga = Get-Grams $a._b
            $gb = Get-Grams $b._b
            $s = Get-Jaccard $ga $gb
            if ($s -ge $Threshold) {
                $keep, $drop = if ($a.Len -ge $b.Len) { $a, $b } else { $b, $a }
                $pairs += [pscustomobject]@{ Sim = [Math]::Round($s, 3); Keep = $keep.Name; KeepLen = $keep.Len; Drop = $drop.Name; DropLen = $drop.Len; DropPath = $drop.Path; Dir = $drop.Dir }
            }
        }
    }
}

# 同一文件可能被多个 keep 指向，按路径去重（保留相似度最高的那条）
$dropMap = @{}
foreach ($p in ($pairs | Sort-Object Sim -Descending)) {
    if (-not $dropMap.ContainsKey($p.DropPath)) { $dropMap[$p.DropPath] = $p }
}
$final = @($dropMap.Values | Sort-Object Dir, Drop)

"重复对：{0}；待移出：{1} 份" -f $pairs.Count, $final.Count
$final | Select-Object Dir, Sim, Keep, KeepLen, Drop, DropLen | Format-Table -AutoSize | Out-String -Width 200

if ($final.Count -gt 0) {
    $csv = Join-Path $rec '重复候选.csv'
    $final | Select-Object Dir, Sim, Keep, KeepLen, Drop, DropLen, DropPath |
        Export-Csv $csv -NoTypeInformation -Encoding utf8BOM
    "报告：$csv"
}

if (-not $Apply) { "加 -Apply 执行移出。" ; return }

$dupRoot = Join-Path $root '归档\重复_根级'
foreach ($p in $final) {
    $dst = Join-Path $dupRoot $p.Dir
    if (-not (Test-Path -LiteralPath $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
    Move-Item -LiteralPath $p.DropPath -Destination (Join-Path $dst $p.Drop) -Force
    "MOV  {0}\{1}  (重复于 {2})" -f $p.Dir, $p.Drop, $p.Keep
}
