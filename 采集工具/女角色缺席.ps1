param(
    [string]$Src = (Join-Path $PSScriptRoot '..\校对后文章'),
    [string]$Report = (Join-Path $PSScriptRoot '记录\女角色缺席.csv')
)

$femNames = @(
    '薰儿','熏儿','萧薰','古薰','美杜莎','彩鳞','小医仙','云韵','纳兰嫣然','纳兰','雅妃','紫研','紫妍','青鳞',
    '萧潇','古娴','李卿婵','绫清竹','应欢欢','姜雪','林静','九幽','洛璃','洛神','清霜','清灵','苏萱','苏灵儿',
    '璃潇','温清璇','小舞','朱竹清','宁荣荣','白沉香','唐舞桐','王冬儿','王秋儿','王冬','古月娜','古月','娜儿',
    '冻千秋','白秀秀','叶星澜','马小桃','蓝梦琴','冰帝','雪帝','南秋秋','雅莉','月夜','珈蓝','唐音梦','蓝木子',
    '艾欧','小七','初代','寒若若','萧萧','朱竹','千仞雪','比比东','阿银','柳二龙','波塞西','碧姬','梦红尘',
    '木冰眉','南宫婉','元瑶','陈巧倩','红拂','刘氏','李氏','海大少','冰凤','苏茹','陆雪琪'
)
$maleNames = @(
    '萧炎','药老','萧战','萧鼎','韩枫','林修崖','严浩','白山','付傲','翎泉','杨皓','牧尘','慕枫','灵剑子',
    '西天战皇','北月','力神王','摩诃幽','叶擎','唐三','戴沐白','奥斯卡','马红俊','霍雨浩','蓝轩宇','唐舞麟',
    '戴华斌','王喆','龙皓晨','韩立','厉飞雨','江云','林动','林琅天','叶凡','庞博','辰南','武煌','卢罡','萧研',
    '唐舞麟','云冥','戴维斯','徐三石','贝贝','药尘','诸葛','叶星澜'
)
$sex = '肉棒|龟头|鸡巴|阳具|阴茎|小穴|骚逼|花穴|蜜穴|乳|屁眼|后穴|口交|射精|精液|淫叫|呻吟'

$rows = @()
foreach ($f in Get-ChildItem -LiteralPath $Src -Recurse -File -Filter *.txt) {
    $t = [IO.File]::ReadAllText($f.FullName)
    $sexN = ([regex]::Matches($t, $sex)).Count
    if ($sexN -lt 15) { continue }
    $fem = 0; $fwho = @()
    foreach ($n in $femNames) {
        $c = ([regex]::Matches($t, [regex]::Escape($n))).Count
        if ($c -gt 0) { $fem += $c; $fwho += "$n($c)" }
    }
    $mal = 0; $mwho = @()
    foreach ($n in $maleNames) {
        $c = ([regex]::Matches($t, [regex]::Escape($n))).Count
        if ($c -gt 0) { $mal += $c; $mwho += "$n($c)" }
    }
    $she = ([regex]::Matches($t, '她')).Count
    $rows += [pscustomobject]@{
        Ip     = Split-Path (Split-Path $f.FullName -Parent) -Leaf
        File   = $f.Name
        Chars  = $t.Length
        SexN   = $sexN
        FemN   = $fem
        MaleN  = $mal
        She    = $she
        FemWho = ($fwho -join ' ')
        MaleWho= ($mwho -join ' ')
        Path   = $f.FullName
    }
}
$rows | Sort-Object FemN | Export-Csv -LiteralPath $Report -NoTypeInformation -Encoding UTF8
"=== 女性角色几乎不出现（FemN<=1）的涉性文件 ==="
$rows | Where-Object { $_.FemN -le 1 } | Sort-Object FemN, SexN -Descending |
    Select-Object Ip, File, Chars, SexN, FemN, MaleN, She, MaleWho | Format-Table -AutoSize -Wrap
