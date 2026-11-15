param(
    [Parameter(Mandatory = $true)][string]$PathA,
    [Parameter(Mandatory = $true)][string]$PathB,
    [double]$Sim = 0.70,
    [int]$MinSent = 8,
    [string]$OutDir = (Join-Path $PSScriptRoot '..\_重叠切片')
)

$ErrorActionPreference = 'Stop'

function Get-Norm {
    param([string]$Text)
    $sbr = New-Object System.Text.StringBuilder
    $map = New-Object System.Collections.Generic.List[int]
    for ($i = 0; $i -lt $Text.Length; $i++) {
        $c = $Text[$i]
        if ([char]::IsWhiteSpace($c)) { continue }
        [void]$sbr.Append($c)
        [void]$map.Add($i)
    }
    [pscustomobject]@{ Norm = $sbr.ToString(); Map = $map.ToArray(); Raw = $Text }
}

# 断句：句末标点 + 换行都算界；归一化坐标
function Get-Sents {
    param($N)
    $t = $N.Norm
    $list = New-Object System.Collections.Generic.List[object]
    $start = 0
    for ($i = 0; $i -lt $t.Length; $i++) {
        $c = [int]$t[$i]
        if ($c -eq 0x3002 -or $c -eq 0xFF01 -or $c -eq 0xFF1F -or $c -eq 0x2026 -or $c -eq 0x201D -or $c -eq 0x300D -or $c -eq 0x300F -or $c -eq 0xFF1B) {
            $list.Add([pscustomobject]@{ Start = $start; Len = ($i - $start + 1) })
            $start = $i + 1
        }
    }
    if ($start -lt $t.Length) { $list.Add([pscustomobject]@{ Start = $start; Len = ($t.Length - $start) }) }
    return , $list
}

function Get-Tri {
    param([string]$S)
    $h = New-Object 'System.Collections.Generic.HashSet[string]'
    for ($i = 0; $i -le $S.Length - 3; $i++) { [void]$h.Add($S.Substring($i, 3)) }
    $h
}

function Get-Sim {
    param([string]$X, [string]$Y)
    if ([Math]::Min($X.Length, $Y.Length) -lt 4) { return 0.0 }
    $hx = Get-Tri $X; $hy = Get-Tri $Y
    $inter = 0
    foreach ($k in $hx) { if ($hy.Contains($k)) { $inter++ } }
    return (2.0 * $inter) / ([Math]::Max(1, $hx.Count) + [Math]::Max(1, $hy.Count))
}

$oA = Get-Norm ([IO.File]::ReadAllText((Resolve-Path -LiteralPath $PathA).Path))
$oB = Get-Norm ([IO.File]::ReadAllText((Resolve-Path -LiteralPath $PathB).Path))
$sA = Get-Sents $oA
$sB = Get-Sents $oB
Write-Host ("DBG A: norm=" + $oA.Norm.Length + " sents=" + $sA.Count + " type=" + $sA.GetType().FullName)
Write-Host ("DBG B: norm=" + $oB.Norm.Length + " sents=" + $sB.Count + " type=" + $sB.GetType().FullName)

# B 句 → A 句 索引表：句首/句尾 6 字做 key
$idx = @{}
for ($i = 0; $i -lt $sA.Count; $i++) {
    $s = $sA[$i]
    if ($s.Len -lt $MinSent) { continue }
    $txt = $oA.Norm.Substring($s.Start, $s.Len)
    $k1 = $txt.Substring(0, [Math]::Min(6, $txt.Length))
    $k2 = $txt.Substring([Math]::Max(0, $txt.Length - 6))
    foreach ($k in @($k1, $k2)) {
        if (-not $idx.ContainsKey($k)) { $idx[$k] = New-Object System.Collections.Generic.List[int] }
        $idx[$k].Add($i)
    }
}

$matchA = New-Object 'int[]' $sB.Count
for ($i = 0; $i -lt $matchA.Length; $i++) { $matchA[$i] = -1 }
$usedA = New-Object 'bool[]' $sA.Count
$lastA = -1
for ($j = 0; $j -lt $sB.Count; $j++) {
    $sentB = $sB[$j]
    if ($sentB.Len -lt $MinSent) { continue }
    $txt = $oB.Norm.Substring($sentB.Start, $sentB.Len)
    $keys = @($txt.Substring(0, [Math]::Min(6, $txt.Length)), $txt.Substring([Math]::Max(0, $txt.Length - 6)))
    $best = -1; $bestSim = 0.0
    foreach ($k in $keys) {
        if (-not $idx.ContainsKey($k)) { continue }
        foreach ($ai in $idx[$k]) {
            $tmp = $oA.Norm.Substring($sA[$ai].Start, $sA[$ai].Len)
            $sc = Get-Sim $txt $tmp
            if ($sc -gt $bestSim) { $bestSim = $sc; $best = $ai }
        }
    }
    if ($bestSim -ge $Sim -and $best -gt $lastA) {
        $matchA[$j] = $best
        $usedA[$best] = $true
        $lastA = $best
    }
}

# 归纳：B 独有块、A 独有块
$bOnly = New-Object System.Collections.Generic.List[object]
$cur = $null
for ($j = 0; $j -lt $sB.Count; $j++) {
    if ($matchA[$j] -ge 0) { if ($cur) { $bOnly.Add($cur); $cur = $null }; continue }
    if ($cur -and ($j - $cur.End) -le 2) { $cur.End = $j + 1 } else { if ($cur) { $bOnly.Add($cur) }; $cur = [pscustomobject]@{ Start = $j; End = $j + 1 } }
}
if ($cur) { $bOnly.Add($cur) }

$aOnly = New-Object System.Collections.Generic.List[object]
$cur = $null
for ($i = 0; $i -lt $sA.Count; $i++) {
    if ($usedA[$i]) { if ($cur) { $aOnly.Add($cur); $cur = $null }; continue }
    if ($cur -and ($i - $cur.End) -le 2) { $cur.End = $i + 1 } else { if ($cur) { $aOnly.Add($cur) }; $cur = [pscustomobject]@{ Start = $i; End = $i + 1 } }
}
if ($cur) { $aOnly.Add($cur) }

function Get-BlockText {
    param($O, $S, [int]$From, [int]$To)
    $st = $S[$From].Start
    $en = $S[$To - 1].Start + $S[$To - 1].Len
    return $O.Norm.Substring($st, $en - $st)
}

$nameA = [IO.Path]::GetFileNameWithoutExtension($PathA)
$nameB = [IO.Path]::GetFileNameWithoutExtension($PathB)
$rep = New-Object System.Text.StringBuilder
[void]$rep.AppendLine("A: $nameA  ($($oA.Norm.Length) 字 / $($sA.Count) 句)")
[void]$rep.AppendLine("B: $nameB  ($($oB.Norm.Length) 字 / $($sB.Count) 句)")
$matched = ($matchA | Where-Object { $_ -ge 0 }).Count
[void]$rep.AppendLine("对齐成功句: $matched / B 共 $($sB.Count)")
[void]$rep.AppendLine("")

[void]$rep.AppendLine("== B 独有块（A 里没有的内容）==")
$k = 0
foreach ($blk in $bOnly) {
    $txt = Get-BlockText $oB $sB $blk.Start $blk.End
    if ($txt.Length -lt 30) { continue }
    $k++
    [void]$rep.AppendLine(("[{0}] B 句 {1}..{2}，{3} 字" -f $k, $blk.Start, $blk.End, $txt.Length))
    [void]$rep.AppendLine("    " + ($(if ($txt.Length -gt 160) { $txt.Substring(0, 160) } else { $txt })))
}
[void]$rep.AppendLine("")
[void]$rep.AppendLine("== A 独有块（B 里没有的内容）==")
$k = 0
foreach ($blk in $aOnly) {
    $txt = Get-BlockText $oA $sA $blk.Start $blk.End
    if ($txt.Length -lt 30) { continue }
    $k++
    [void]$rep.AppendLine(("[{0}] A 句 {1}..{2}，{3} 字" -f $k, $blk.Start, $blk.End, $txt.Length))
    [void]$rep.AppendLine("    " + ($(if ($txt.Length -gt 160) { $txt.Substring(0, 160) } else { $txt })))
}

if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
$rb = New-Object System.Text.StringBuilder
foreach ($blk in $bOnly) {
    $txt = Get-BlockText $oB $sB $blk.Start $blk.End
    if ($txt.Length -lt 30) { continue }
    [void]$rb.AppendLine($txt)
}
$ra = New-Object System.Text.StringBuilder
foreach ($blk in $aOnly) {
    $txt = Get-BlockText $oA $sA $blk.Start $blk.End
    if ($txt.Length -lt 30) { continue }
    [void]$ra.AppendLine($txt)
}
$enc = New-Object System.Text.UTF8Encoding $true
[IO.File]::WriteAllText((Join-Path $OutDir ("B独有_" + $nameB + ".txt")), $rb.ToString(), $enc)
[IO.File]::WriteAllText((Join-Path $OutDir ("A独有_" + $nameA + ".txt")), $ra.ToString(), $enc)
$rp = Join-Path $PSScriptRoot ("记录\重叠对齐_" + $nameA.Substring(0, [Math]::Min(20, $nameA.Length)) + ".txt")
[IO.File]::WriteAllText($rp, $rep.ToString(), $enc)

"报告: $rp"
"切片: $OutDir"
$rep.ToString()
