param(
    [string]$Src = (Join-Path $PSScriptRoot '..\校对后文章'),
    [string]$Digest = (Join-Path $PSScriptRoot '记录\男同段落.txt')
)

$males = @('萧炎','药老','萧战','萧鼎','韩枫','林修崖','严浩','白山','付傲','翎泉','杨皓','萧研','唐三','戴沐白','奥斯卡','马红俊','霍雨浩','蓝轩宇','唐舞麟','戴华斌','王喆','戴维斯','徐三石','贝贝','云冥','龙皓晨','韩立','厉飞雨','江云','海大少','林动','林琅天','牧尘','慕枫','灵剑子','西天战皇','北月','力神王','摩诃幽','叶擎','石昊','周武泰','叶冥','元煞','卢罡','辰南','武煌','叶凡','庞博','黑皇','帝尊','天皇子','紫天凤')
$gen = '肉棒|龟头|鸡巴|阳具|阴茎|马眼|屁眼|后穴|菊花|后庭|精液|射精|口交|含着|含住|套弄|吮吸'

$sb = New-Object System.Text.StringBuilder
$n = 0
foreach ($f in Get-ChildItem -LiteralPath $Src -Recurse -File -Filter *.txt) {
    $t = [IO.File]::ReadAllText($f.FullName)
    $paras = $t -split '\r?\n\s*\r?\n'
    $hits = @()
    foreach ($p in $paras) {
        if ($p.Length -lt 40) { continue }
        if ($p -notmatch $gen) { continue }
        $found = @()
        foreach ($mn in $males) { if ($p.Contains($mn)) { $found += $mn } }
        if ($found.Count -lt 2) { continue }
        $hits += ($p -replace '\s+', ' ') + "   <<" + ($found -join ',') + ">>"
    }
    if ($hits.Count -eq 0) { continue }
    $n++
    [void]$sb.AppendLine("### " + (Split-Path (Split-Path $f.FullName -Parent) -Leaf) + " / " + $f.Name + "  [段 $($hits.Count)]")
    foreach ($h in ($hits | Select-Object -First 3)) {
        $s = if ($h.Length -gt 170) { $h.Substring(0, 170) } else { $h }
        [void]$sb.AppendLine("   > " + $s)
    }
    [void]$sb.AppendLine()
}
[IO.File]::WriteAllText($Digest, $sb.ToString(), (New-Object System.Text.UTF8Encoding $true))
"两男同段的文件：$n 份 -> $Digest"
