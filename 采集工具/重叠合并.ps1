param(
    [Parameter(Mandatory = $true)][string[]]$Paths,
    [string]$Title,
    [string]$Span,
    [string]$OutDir,
    [int]$K = 16,
    [int]$MinBlock = 200,
    [int]$GapTol = 60,
    [int]$Ctx = 200,
    [switch]$Apply,
    [switch]$KeepSource
)

$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot '记录\重叠合并.csv'
$report = Join-Path $PSScriptRoot '记录\重叠合并报告.txt'

function Get-Norm {
    param([string]$Text)
    $sb = New-Object System.Text.StringBuilder
    $map = New-Object System.Collections.Generic.List[int]
    for ($i = 0; $i -lt $Text.Length; $i++) {
        $c = $Text[$i]
        if ([char]::IsWhiteSpace($c)) { continue }
        [void]$sb.Append($c)
        [void]$map.Add($i)
    }
    [pscustomobject]@{ Norm = $sb.ToString(); Map = $map.ToArray(); Raw = $Text }
}

function Get-RawSlice {
    param($N, [int]$Start, [int]$Len)
    if ($Len -le 0) { return '' }
    $s = $N.Map[$Start]
    $e = $N.Map[[Math]::Min($Start + $Len - 1, $N.Map.Length - 1)]
    return ($N.Raw.Substring($s, $e - $s + 1))
}

# 用 A 的归一化文本建 k-gram 索引，返回 B 相对 A 的覆盖情况
function Get-Overlap {
    param($ObjA, $ObjB, [int]$Kk)
    $an = $ObjA.Norm; $bn = $ObjB.Norm
    $dict = New-Object 'System.Collections.Generic.Dictionary[string,System.Collections.Generic.List[int]]'
    for ($i = 0; $i -le $an.Length - $Kk; $i++) {
        $key = $an.Substring($i, $Kk)
        $lst = $null
        if ($dict.TryGetValue($key, [ref]$lst)) {
            if ($lst.Count -lt 4) { $lst.Add($i) }
        } else {
            $nl = New-Object 'System.Collections.Generic.List[int]'
            $nl.Add($i)
            $dict[$key] = $nl
        }
    }
    $covered = New-Object 'bool[]' $bn.Length
    $aPos = New-Object 'int[]' $bn.Length
    for ($i = 0; $i -lt $aPos.Length; $i++) { $aPos[$i] = -1 }
    $i = 0
    while ($i -le $bn.Length - $Kk) {
        $key = $bn.Substring($i, $Kk)
        $lst = $null
        if (-not $dict.TryGetValue($key, [ref]$lst)) { $i++; continue }
        $bestLen = 0; $bestPre = 0; $bestAt = -1
        foreach ($pos in $lst) {
            $len = 0
            while (($i + $len) -lt $bn.Length -and ($pos + $len) -lt $an.Length -and $bn[$i + $len] -eq $an[$pos + $len]) { $len++ }
            $pre = 0
            while (($i - $pre - 1) -ge 0 -and ($pos - $pre - 1) -ge 0 -and $bn[$i - $pre - 1] -eq $an[$pos - $pre - 1]) { $pre++ }
            if ($len -gt $bestLen) { $bestLen = $len; $bestPre = $pre; $bestAt = $pos }
        }
        if ($bestLen -lt $Kk) { $i++; continue }
        $s = [Math]::Max(0, $i - $bestPre)
        $e = [Math]::Min($i + $bestLen, $bn.Length)
        for ($j = $s; $j -lt $e; $j++) { $covered[$j] = $true; $aPos[$j] = $bestAt - ($i - $j) }
        $i = $e
    }
    $blocks = New-Object System.Collections.Generic.List[object]
    $j = 0
    while ($j -lt $covered.Length) {
        if (-not $covered[$j]) { $j++; continue }
        $s = $j
        while ($j -lt $covered.Length -and $covered[$j]) { $j++ }
        $e = $j
        $ap = $aPos[$s]
        if ($blocks.Count -gt 0 -and ($s - $blocks[$blocks.Count - 1].End) -le $GapTol) {
            $blocks[$blocks.Count - 1].End = $e
        } else {
            $blocks.Add([pscustomobject]@{ Start = $s; End = $e; AStart = $ap })
        }
    }
    [pscustomobject]@{ Blocks = $blocks; ANormLen = $an.Length; BNormLen = $bn.Length }
}

# ---------- 载入 ----------
$objs = @()
foreach ($p in $Paths) {
    $full = (Resolve-Path -LiteralPath $p).Path
    $objs += [pscustomobject]@{ Path = $full; Obj = (Get-Norm ([IO.File]::ReadAllText($full))) }
}
if ($objs.Count -lt 2) { "至少给两个文件"; return }

$rpt = New-Object System.Text.StringBuilder
[void]$rpt.AppendLine("== 重叠合并 ==")
foreach ($o in $objs) { [void]$rpt.AppendLine(("  {0}  ({1} 字)" -f (Split-Path $o.Path -Leaf), $o.Obj.Norm.Length)) }

# ---------- 逐对合并 ----------
$cur = $objs[0].Obj
$curPath = $objs[0].Path
$modes = @()
for ($n = 1; $n -lt $objs.Count; $n++) {
    $nx = $objs[$n].Obj
    $ov = Get-Overlap -ObjA $cur -ObjB $nx -Kk $K
    $big = $ov.Blocks | Where-Object { ($_.End - $_.Start) -ge $MinBlock } | Sort-Object { $_.End - $_.Start } -Descending
    $an = $cur.Norm.Length; $bn = $nx.Norm.Length
    $mode = ''
    $newText = ''
    if (-not $big) {
        # 无显著重叠：顺序拼接，保留双方全部内容
        $mode = 'concat'
        $newText = $cur.Raw.TrimEnd() + "`r`n`r`n" + $nx.Raw.TrimStart()
        [void]$rpt.AppendLine("  [$n] 与上一件无 ≥$MinBlock 字的重叠（最大块 $(if ($ov.Blocks.Count) { ($ov.Blocks | Measure-Object -Property { $_.End - $_.Start } -Maximum).Maximum } else { 0 }) 字）→ 顺序拼接")
    } else {
        $blk = $big[0]
        $len = $blk.End - $blk.Start
        $aStart = $blk.AStart
        if ($aStart -lt 0) { $aStart = 0 }
        $tailOfA = ($an - ($aStart + $len)) -le 40
        $headOfB = $blk.Start -le 40
        $headOfA = $aStart -le 40
        $tailOfB = ($bn - $blk.End) -le 40
        if ($tailOfA -and $headOfB) {
            $mode = 'append'
            $newText = $cur.Raw.TrimEnd() + "`r`n`r`n" + (Get-RawSlice $nx $blk.End ($bn - $blk.End)).TrimStart()
            [void]$rpt.AppendLine("  [$n] 重叠 $len 字：接在 A 尾部、B 头部 → 取 A 全文 + B 后段 $(($bn - $blk.End)) 字")
        } elseif ($headOfA -and $tailOfB) {
            $mode = 'prepend'
            $newText = (Get-RawSlice $nx 0 $blk.Start).TrimEnd() + "`r`n`r`n" + $cur.Raw.TrimStart()
            [void]$rpt.AppendLine("  [$n] 重叠 $len 字：B 尾部覆盖 A 头部 → 取 B 前段 $($blk.Start) 字 + A 全文")
        } elseif ($tailOfA -and $tailOfB) {
            # B 整段落在 A 内部
            $mode = 'inside'
            $newText = $cur.Raw
            [void]$rpt.AppendLine("  [$n] 重叠 $len 字：B 全部被 A 覆盖，B 无新内容 → 只用 A")
        } else {
            $mode = 'insert'
            $aEnd = [Math]::Min($an, $aStart + $len)
            $preTxt = if ($aStart -gt 0) { (Get-RawSlice $cur 0 $aStart) } else { '' }
            $midTxt = (Get-RawSlice $nx $blk.Start $len)
            $sufTxt = if ($aEnd -lt $an) { (Get-RawSlice $cur $aEnd ($an - $aEnd)) } else { '' }
            $newText = ($preTxt.TrimEnd() + "`r`n`r`n" + $midTxt.Trim() + "`r`n`r`n" + $sufTxt.TrimStart()).Trim()
            [void]$rpt.AppendLine("  [$n] 重叠 $len 字：B 插在 A 中间 → A 前段 $aStart 字 + B 重叠段 + A 后段 $($an - $aEnd) 字")
        }
        [void]$rpt.AppendLine("      重叠块 B[$($blk.Start)..$($blk.End)] / A 起 $aStart")
        [void]$rpt.AppendLine("      接缝预览: " + (($newText -replace '\s+', ' ')))
    }
    $newText = ($newText -replace "`r`n", "`n" -replace "`r", "`n") -replace "`n{3,}", "`n`n"
    $newText = $newText -replace "`n", "`r`n"
    $cur = Get-Norm $newText
    $modes += $mode
}

# ---------- 产物 ----------
$chars = $cur.Norm.Length
if (-not $Title) {
    $base = [IO.Path]::GetFileNameWithoutExtension($objs[0].Path)
    $base = $base -replace '^《', '' -replace '》.*$', ''
    $Title = $base
}
if (-not $Span) { $Span = '合并' }
$wc = if ($chars -ge 10000) { ('{0}w' -f [Math]::Round($chars / 10000.0, 1)).Replace('.0w', 'w') } else { '{0}字' -f $chars }
$outName = ('《{0}》-{1}-{2}.txt' -f $Title, $Span, $wc)
if (-not $OutDir) { $OutDir = Split-Path $objs[0].Path -Parent }
$outPath = Join-Path $OutDir $outName

[void]$rpt.AppendLine("")
[void]$rpt.AppendLine("模式: $($modes -join ' -> ')")
[void]$rpt.AppendLine("输出: $outPath  ($chars 字去空白)")
[IO.File]::WriteAllText($report, $rpt.ToString(), (New-Object System.Text.UTF8Encoding $true))

if (-not $Apply) {
    $rpt.ToString()
    "DRY：加 -Apply 才写盘。报告 $report"
    return
}

[IO.File]::WriteAllText($outPath, $cur.Raw, (New-Object System.Text.UTF8Encoding $true))

if (-not $KeepSource) {
    $bakDir = Join-Path (Join-Path $PSScriptRoot '..\归档\备份_校对后\重叠') (Split-Path $OutDir -Leaf)
    if (-not (Test-Path -LiteralPath $bakDir)) { New-Item -ItemType Directory -Path $bakDir -Force | Out-Null }
    foreach ($p in $Paths) {
        $full = (Resolve-Path -LiteralPath $p).Path
        if ($full -eq $outPath) { continue }
        Move-Item -LiteralPath $full -Destination (Join-Path $bakDir (Split-Path $full -Leaf)) -Force
    }
}

$row = [pscustomobject]@{
    Time     = (Get-Date).ToString('s')
    Mode     = ($modes -join '>')
    Sources  = ($Paths -join ' | ')
    Output   = $outName
    OutChars = $chars
}
if (Test-Path -LiteralPath $log) { $row | Export-Csv -LiteralPath $log -NoTypeInformation -Encoding UTF8 -Append }
else { $row | Export-Csv -LiteralPath $log -NoTypeInformation -Encoding UTF8 }

"已输出：$outPath（$chars 字）"
"模式：$($modes -join ' -> ')"
"接着跑：重建清单.ps1 -> 校验.ps1 -> 索引.ps1"
