param(
    [Parameter(Mandatory = $true)][string]$PathA,
    [Parameter(Mandatory = $true)][string]$PathB,
    [int]$K = 16,
    [int]$GapTol = 60,
    [int]$Ctx = 300,
    [string]$Report = (Join-Path $PSScriptRoot '记录\重叠检测.txt')
)

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

$objA = Get-Norm ([IO.File]::ReadAllText((Resolve-Path -LiteralPath $PathA).Path))
$objB = Get-Norm ([IO.File]::ReadAllText((Resolve-Path -LiteralPath $PathB).Path))
$an = $objA.Norm; $bn = $objB.Norm
if ($an.Length -lt $K -or $bn.Length -lt $K) { "文本太短，跳过（A=$($an.Length) B=$($bn.Length)）"; return }

# 建 A 的 k-gram 索引（每个 key 最多记 4 个位置）
$dict = New-Object 'System.Collections.Generic.Dictionary[string,System.Collections.Generic.List[int]]'
for ($i = 0; $i -le $an.Length - $K; $i++) {
    $key = $an.Substring($i, $K)
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
$i = 0
while ($i -le $bn.Length - $K) {
    $key = $bn.Substring($i, $K)
    $lst = $null
    if (-not $dict.TryGetValue($key, [ref]$lst)) { $i++; continue }
    $bestLen = 0; $bestPre = 0
    foreach ($pos in $lst) {
        $len = 0
        while (($i + $len) -lt $bn.Length -and ($pos + $len) -lt $an.Length -and $bn[$i + $len] -eq $an[$pos + $len]) { $len++ }
        $pre = 0
        while (($i - $pre - 1) -ge 0 -and ($pos - $pre - 1) -ge 0 -and $bn[$i - $pre - 1] -eq $an[$pos - $pre - 1]) { $pre++ }
        if ($len -gt $bestLen) { $bestLen = $len; $bestPre = $pre }
    }
    if ($bestLen -lt $K) { $i++; continue }
    $s = [Math]::Max(0, $i - $bestPre)
    $e = $i + $bestLen
    for ($j = $s; $j -lt $e -and $j -lt $bn.Length; $j++) { $covered[$j] = $true }
    $i = $e
}

# 合并覆盖块（间隔 <= GapTol 视为同一块）
$blocks = New-Object System.Collections.Generic.List[object]
$j = 0
while ($j -lt $covered.Length) {
    if (-not $covered[$j]) { $j++; continue }
    $s = $j
    while ($j -lt $covered.Length -and $covered[$j]) { $j++ }
    $e = $j
    if ($blocks.Count -gt 0 -and ($s - $blocks[$blocks.Count - 1].End) -le $GapTol) {
        $blocks[$blocks.Count - 1].End = $e
    } else {
        $blocks.Add([pscustomobject]@{ Start = $s; End = $e })
    }
}

function Get-RawSlice {
    param($N, [int]$Start, [int]$Len)
    if ($Len -le 0) { return '' }
    $s = $N.Map[$Start]
    $e = $N.Map[[Math]::Min($Start + $Len - 1, $N.Map.Length - 1)]
    return ($N.Raw.Substring($s, $e - $s + 1) -replace '\r?\n', ' ¶ ' -replace '\s+', ' ')
}

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("A: $((Resolve-Path -LiteralPath $PathA).Path)")
[void]$sb.AppendLine("   字符数(去空白)=$($an.Length)")
[void]$sb.AppendLine("B: $((Resolve-Path -LiteralPath $PathB).Path)")
[void]$sb.AppendLine("   字符数(去空白)=$($bn.Length)")
[void]$sb.AppendLine("覆盖块数=$($blocks.Count)")

foreach ($blk in $blocks) {
    $len = $blk.End - $blk.Start
    $after = $bn.Length - $blk.End
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("=== 块 B[$($blk.Start)..$($blk.End)] 共 $len 字；B 之后剩余 $after 字；B 之前剩余 $($blk.Start) 字")
    [void]$sb.AppendLine("  B 起点前文: ..." + (Get-RawSlice $objB ([Math]::Max(0, $blk.Start - $Ctx)) ([Math]::Min($Ctx, $blk.Start))))
    [void]$sb.AppendLine("  B 块首 80 : " + (Get-RawSlice $objB $blk.Start ([Math]::Min(80, $len))))
    [void]$sb.AppendLine("  B 块尾 80 : " + (Get-RawSlice $objB ([Math]::Max($blk.Start, $blk.End - 80)) ([Math]::Min(80, $len))))
    [void]$sb.AppendLine("  B 块后文: " + (Get-RawSlice $objB $blk.End ([Math]::Min($Ctx, $after))))
}

[IO.File]::WriteAllText($Report, $sb.ToString(), (New-Object System.Text.UTF8Encoding $true))
"报告: $Report"
$sb.ToString()
