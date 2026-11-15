param(
    [string]$Src = (Join-Path $PSScriptRoot '..\校对后文章'),
    [string]$Report = (Join-Path $PSScriptRoot '记录\男同筛查.csv')
)

$mAnal = '他的(屁眼|后穴|菊花|后庭|肠道|屁股眼)|插(进|入)他(的)?(屁眼|后穴|菊花|后庭)|(操|干|肏|日)他(的)?(屁眼|后面|后穴)|他(的)?(屁眼|后穴)里|他(的)?(肉棒|阴茎|龟头)|握(住|着)他(的)?(肉棒|阴茎)|舔他(的)?(肉棒|龟头)|他(的)?(精液|白浊)'
$fAnal = '她的(屁眼|后穴|菊花|后庭)|插(进|入)她(的)?(屁眼|后穴|菊花|后庭)|她(的)?(屁眼|后穴)里'
$tag   = '耽美|男男|BL文|攻受|小受|总攻|攻君|基佬|同性恋|男风|断袖|龙阳|男宠|男妓|双男主|两个男人'

$rows = @()
foreach ($f in Get-ChildItem -LiteralPath $Src -Recurse -File -Filter *.txt) {
    $t = [IO.File]::ReadAllText($f.FullName)
    $len = $t.Length
    $t = $t.Substring(0, [Math]::Min($len, 80000))
    $ma = ([regex]::Matches($t, $mAnal)).Count
    $fa = ([regex]::Matches($t, $fAnal)).Count
    $tg = ([regex]::Matches($t, $tag)).Count
    $he = ([regex]::Matches($t, '他')).Count
    $she = ([regex]::Matches($t, '她')).Count
    $rows += [pscustomobject]@{
        Ip     = Split-Path (Split-Path $f.FullName -Parent) -Leaf
        File   = $f.Name
        Chars  = $len
        MaleAct= $ma
        FemAct = $fa
        Tag    = $tg
        He     = $he
        She    = $she
        Path   = $f.FullName
    }
}
$rows | Sort-Object -Property @{ Expression = 'MaleAct'; Descending = $true }, @{ Expression = 'Tag'; Descending = $true } |
    Export-Csv -LiteralPath $Report -NoTypeInformation -Encoding UTF8

"=== 男性被插入/被口 明确句式（MaleAct>=2） ==="
$rows | Where-Object { $_.MaleAct -ge 2 } | Sort-Object MaleAct -Descending |
    Select-Object Ip, File, Chars, MaleAct, FemAct, Tag, He, She | Format-Table -AutoSize
"=== BL 标签命中 ==="
$rows | Where-Object { $_.Tag -ge 2 } | Select-Object Ip, File, Tag, MaleAct, FemAct | Format-Table -AutoSize
"=== 男性代词占绝对优势且无女性（He>She*3 且 She<20，字数>3000） ==="
$rows | Where-Object { $_.Chars -gt 3000 -and $_.She -lt 20 -and $_.He -gt 60 } | Sort-Object He -Descending |
    Select-Object Ip, File, Chars, MaleAct, FemAct, He, She | Format-Table -AutoSize
