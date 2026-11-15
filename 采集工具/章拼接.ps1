param(
    [Parameter(Mandatory = $true)][string]$PathA,
    [Parameter(Mandatory = $true)][string]$PathB,
    [Parameter(Mandatory = $true)][string[]]$Plan,
    [Parameter(Mandatory = $true)][string]$Title,
    [string]$Span = '',
    [string]$OutDir = '',
    [switch]$Renumber,
    [switch]$Apply,
    [switch]$KeepSource
)

$ErrorActionPreference = 'Stop'
$enc = New-Object System.Text.UTF8Encoding $true

function Get-Chaps {
    param([string]$Text)
    $rx = [regex]'第(\d+)章[：:]?([^\r\n]{0,40})'
    $ms = $rx.Matches($Text)
    $map = @{}
    $firstPos = if ($ms.Count -gt 0) { $ms[0].Index } else { $Text.Length }
    $pre = $Text.Substring(0, $firstPos).TrimEnd("`r", "`n")
    $map[0] = $pre
    for ($i = 0; $i -lt $ms.Count; $i++) {
        $st = $ms[$i].Index
        $en = if ($i + 1 -lt $ms.Count) { $ms[$i + 1].Index } else { $Text.Length }
        $map[[int]$ms[$i].Groups[1].Value] = $Text.Substring($st, $en - $st).TrimEnd("`r", "`n")
    }
    $map
}

$tA = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $PathA).Path)
$tB = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $PathB).Path)
$cA = Get-Chaps $tA
$cB = Get-Chaps $tB

$sb = New-Object System.Text.StringBuilder
$rows = New-Object System.Collections.Generic.List[object]
$n = 0
$cnum = 0
foreach ($it in $Plan) {
    $src, $no = $it -split ':', 2
    $no = [int]$no
    $map = if ($src -eq 'A') { $cA } else { $cB }
    if (-not $map.ContainsKey($no)) { throw "找不到 $src 第 $no 章" }
    $seg = $map[$no]
    $n++
    if ($no -ne 0) { $cnum++ }
    if ($Renumber -and $no -ne 0) {
        $seg = [regex]::Replace($seg, '第\d+章', "第${cnum}章", 1)
    }
    [void]$sb.AppendLine($seg)
    [void]$sb.AppendLine('')
    $rows.Add([pscustomobject]@{ Seq = $n; Src = $it; Chars = ($seg -replace '\s', '').Length })
}

$text = $sb.ToString().TrimEnd("`r", "`n") + "`r`n"
$chars = ($text -replace '\s', '').Length

if (-not $Span) {
    $Span = if ($Renumber -and $cnum -gt 0) { "1~${cnum}章" } else { "合并" }
}
$wc = ('{0}w' -f [Math]::Round($chars / 10000.0, 1)).Replace('.0w', 'w')
$name = "《$Title》-$Span-$wc.txt"
if (-not $OutDir) { $OutDir = Split-Path -Parent (Resolve-Path -LiteralPath $PathA).Path }
$out = Join-Path $OutDir $name

""
"章序列（共 $n 段，去空白 $chars 字 → $wc）"
foreach ($r in $rows) { "  [{0,2}] {1,-6} {2} 字" -f $r.Seq, $r.Src, $r.Chars }

if (-not $Apply) {
    ""
    "DRY：产物将写入 $out"
    "加 -Apply 才写盘。"
    return
}

[IO.File]::WriteAllText($out, $text, $enc)
"已写入: $out"

if (-not $KeepSource) {
    $bakRoot = Join-Path (Split-Path -Parent $OutDir) '归档\备份_校对后\重叠'
    foreach ($p in @($PathA, $PathB)) {
        $dir = Join-Path $bakRoot (Split-Path -Leaf (Split-Path -Parent (Resolve-Path -LiteralPath $p).Path))
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Move-Item -LiteralPath $p -Destination $dir -Force
        "已备份并移走: $p → $dir"
    }
}
