param(
    [Parameter(Mandatory = $true)][string]$PathA,
    [Parameter(Mandatory = $true)][string]$PathB,
    [double]$Sim = 0.45,
    [string]$Report = ''
)

$ErrorActionPreference = 'Stop'
$enc = New-Object System.Text.UTF8Encoding $true

function Get-Chap {
    param([string]$Text, [string]$Tag)
    $rx = [regex]'第(\d+)章[：:]?([^\r\n]{0,40})'
    $ms = $rx.Matches($Text)
    $list = New-Object System.Collections.Generic.List[object]
    # 前言
    $firstPos = $Text.Length
    if ($ms.Count -gt 0) { $firstPos = $ms[0].Index }
    if ($firstPos -gt 50) {
        $pre = $Text.Substring(0, $firstPos)
        $norm = $pre -replace '\s', ''
        $list.Add([pscustomobject]@{ No = 0; Title = '(前言)'; Start = 0; End = $firstPos; Chars = $norm.Length; Head = $(if ($norm.Length -gt 300) { $norm.Substring(0, 300) } else { $norm }) })
    }
    for ($i = 0; $i -lt $ms.Count; $i++) {
        $m = $ms[$i]
        $st = $m.Index
        $en = if ($i + 1 -lt $ms.Count) { $ms[$i + 1].Index } else { $Text.Length }
        $body = $Text.Substring($st, $en - $st)
        $norm = $body -replace '\s', ''
        $list.Add([pscustomobject]@{
                No = [int]$m.Groups[1].Value; Title = $m.Groups[2].Value.Trim(); Start = $st; End = $en
                Chars = $norm.Length
                Head = $(if ($norm.Length -gt 300) { $norm.Substring(0, 300) } else { $norm })
            })
    }
    $list
}

function Get-Tri { param([string]$S)
    $h = New-Object 'System.Collections.Generic.HashSet[string]'
    for ($i = 0; $i -le $S.Length - 3; $i++) { [void]$h.Add($S.Substring($i, 3)) }
    $h
}
function Get-Sim { param([string]$X, [string]$Y)
    if ([Math]::Min($X.Length, $Y.Length) -lt 10) { return 0.0 }
    $hx = Get-Tri $X; $hy = Get-Tri $Y
    $inter = 0
    foreach ($k in $hx) { if ($hy.Contains($k)) { $inter++ } }
    return (2.0 * $inter) / ([Math]::Max(1, $hx.Count) + [Math]::Max(1, $hy.Count))
}

$tA = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $PathA).Path)
$tB = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $PathB).Path)
$cA = Get-Chap $tA 'A'
$cB = Get-Chap $tB 'B'

$rep = New-Object System.Text.StringBuilder
[void]$rep.AppendLine("A: " + [IO.Path]::GetFileNameWithoutExtension($PathA))
[void]$rep.AppendLine("   章数 $($cA.Count)，共 $(($cA | Measure-Object Chars -Sum).Sum) 字")
[void]$rep.AppendLine("B: " + [IO.Path]::GetFileNameWithoutExtension($PathB))
[void]$rep.AppendLine("   章数 $($cB.Count)，共 $(($cB | Measure-Object Chars -Sum).Sum) 字")
[void]$rep.AppendLine("")

# 交叉比对
$dupA = @{}; $dupB = @{}
foreach ($a in $cA) {
    $best = $null; $bs = 0.0
    foreach ($b in $cB) {
        $s = Get-Sim $a.Head $b.Head
        if ($s -gt $bs) { $bs = $s; $best = $b }
    }
    if ($best -and $bs -ge $Sim) {
        $dupA[$a.No] = @{ B = $best.No; Sim = $bs; AChars = $a.Chars; BChars = $best.Chars }
        $dupB[$best.No] = $a.No
    }
}

[void]$rep.AppendLine("== 重复章（正文相似 ≥ $Sim）==")
if ($dupA.Count -eq 0) { [void]$rep.AppendLine("  无") }
foreach ($k in ($dupA.Keys | Sort-Object)) {
    $d = $dupA[$k]
    $keep = if ($d.BChars -gt $d.AChars) { 'B' } else { 'A' }
    [void]$rep.AppendLine(("  A 第{0}章  {1} 字  ≈  B 第{2}章  {3} 字   相似 {4:P0}   建议留 {5}" -f $k, $d.AChars, $d.B, $d.BChars, $d.Sim, $keep))
}
[void]$rep.AppendLine("")
[void]$rep.AppendLine("== A 独有章 ==")
foreach ($a in $cA) { if (-not $dupA.ContainsKey($a.No)) { [void]$rep.AppendLine(("  第{0}章  {1} 字  {2}" -f $a.No, $a.Chars, $a.Title)) } }
[void]$rep.AppendLine("")
[void]$rep.AppendLine("== B 独有章 ==")
foreach ($b in $cB) { if (-not $dupB.ContainsKey($b.No)) { [void]$rep.AppendLine(("  第{0}章  {1} 字  {2}" -f $b.No, $b.Chars, $b.Title)) } }
[void]$rep.AppendLine("")

# 章号分布
[void]$rep.AppendLine("== 章号分布 ==")
[void]$rep.AppendLine("  A: " + (($cA | ForEach-Object { $_.No }) -join ','))
[void]$rep.AppendLine("  B: " + (($cB | ForEach-Object { $_.No }) -join ','))

if (-not $Report) {
    $Report = Join-Path $PSScriptRoot ('记录\章对齐_' + [IO.Path]::GetFileNameWithoutExtension($PathA).Substring(0, [Math]::Min(18, [IO.Path]::GetFileNameWithoutExtension($PathA).Length)) + '.txt')
}
[IO.File]::WriteAllText($Report, $rep.ToString(), $enc)
"报告: $Report"
$rep.ToString()
