param(
    [string[]]$Srcs = @((Join-Path $PSScriptRoot '..\校对后文章'), (Join-Path $PSScriptRoot '..\原文')),
    [string]$Digest = (Join-Path $PSScriptRoot '记录\男同精查.txt')
)

$males = @('萧炎','药老','萧战','萧鼎','韩枫','林修崖','严浩','白山','付傲','翎泉','杨皓','唐三','戴沐白','奥斯卡','马红俊','霍雨浩','蓝轩宇','唐舞麟','戴华斌','王喆','戴维斯','徐三石','贝贝','云冥','龙皓晨','韩立','厉飞雨','江云','海大少','林动','林琅天','牧尘','慕枫','灵剑子','西天战皇','北月','力神王','摩诃幽','叶擎','石昊','周武泰','叶冥','元煞','卢罡','辰南','武煌','叶凡','庞博','黑皇','帝尊','天皇子')
$verb = '含住|含着|含入|含进|吞下|吞入|舔|吮吸|套弄|握住|握住|轻抚|抚摸|握住|口交|吸吮|吞咽'
$organ = '肉棒|阳具|龟头|鸡巴|阴茎|男根|巨物'
$re = New-Object System.Text.RegularExpressions.Regex("($verb)([^。！？\r\n]{0,14}?)($organ)")

$sb = New-Object System.Text.StringBuilder
$n = 0
foreach ($src in $Srcs) {
    if (-not (Test-Path -LiteralPath $src)) { continue }
    foreach ($f in Get-ChildItem -LiteralPath $src -Recurse -File -Filter *.txt) {
        $t = [IO.File]::ReadAllText($f.FullName)
        $hits = @()
        foreach ($m in $re.Matches($t)) {
            $pre = $t.Substring([Math]::Max(0, $m.Index - 40), [Math]::Min(40, $m.Index))
            $post = $t.Substring($m.Index + $m.Length, [Math]::Min(16, $t.Length - ($m.Index + $m.Length)))
            $pm = @(); foreach ($mn in $males) { if ($pre.Contains($mn)) { $pm += $mn } }
            $om = @(); foreach ($mn in $males) { if ($post.Contains($mn)) { $om += $mn } }
            if ($pm.Count -lt 1 -or $om.Count -lt 1) { continue }
            $hits += "[$($pm -join ',')] => $($m.Value) => [$($om -join ',')]"
        }
        if ($hits.Count -eq 0) { continue }
        $n++
        [void]$sb.AppendLine("### " + $f.FullName.Replace($PSScriptRoot, '') )
        foreach ($h in ($hits | Select-Object -First 4)) { [void]$sb.AppendLine("   * " + $h) }
        [void]$sb.AppendLine()
    }
}
[IO.File]::WriteAllText($Digest, $sb.ToString(), (New-Object System.Text.UTF8Encoding $true))
"疑似「男性对男性口/手」命中文件：$n 份 -> $Digest"
