param(
    [string]$Src = (Join-Path $PSScriptRoot '..\校对后文章'),
    [string]$Out = (Join-Path $PSScriptRoot '记录\男同片段.txt')
)

$pat = "他(的)?(屁眼|后穴|菊花|后庭|肠道)|(插|干|操|肏|日|弄|顶|进入)(进|入|着)?他(的)?(里面|身体|屁股|后面|深处)|两个男人|男(人|孩)的(肉棒|身体)"
$sb = New-Object System.Text.StringBuilder
$n = 0
foreach ($f in Get-ChildItem -LiteralPath $Src -Recurse -File -Filter *.txt) {
    $t = [IO.File]::ReadAllText($f.FullName)
    $t = $t.Substring(0, [Math]::Min($t.Length, 80000))
    $ms = [regex]::Matches($t, $pat)
    if ($ms.Count -eq 0) { continue }
    $she = ([regex]::Matches($t, '她')).Count
    $n++
    [void]$sb.AppendLine("### " + (Split-Path (Split-Path $f.FullName -Parent) -Leaf) + " / " + $f.Name + "  [她x$she, 命中$($ms.Count)]")
    $shown = 0
    $last = -1
    foreach ($m in $ms) {
        if ($shown -ge 2) { break }
        if ($m.Index - $last -lt 60) { continue }
        $s = [Math]::Max(0, $m.Index - 70)
        $len = [Math]::Min(130, $t.Length - $s)
        [void]$sb.AppendLine("   … " + ($t.Substring($s, $len) -replace '\r?\n', ' ') + " …")
        $last = $m.Index; $shown++
    }
    [void]$sb.AppendLine()
}
[IO.File]::WriteAllText($Out, $sb.ToString(), (New-Object System.Text.UTF8Encoding $true))
"候选 {0} 份 -> {1} ({2} 字符)" -f $n, $Out, $sb.Length
