# 合并.ps1 —— 把「同书不同章标题」的分篇合并成一部
#   pwsh -File 采集工具\合并.ps1 -DryRun     # 只列候选
#   pwsh -File 采集工具\合并.ps1 -Apply      # 执行（原文件移到 归档\备份_整合前）
param(
    [switch]$DryRun,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$src  = Join-Path $root '校对后文章'
$bak  = Join-Path $root '归档\备份_整合前'
$cfg  = Import-PowerShellDataFile (Join-Path $PSScriptRoot 'families.psd1')
$families = $cfg.Families
$yeXuan   = $cfg.YeXuan

function Get-Bare([string]$name) { return ($name -replace '[《》]', '') }

function Get-Ch([string]$name) {
    $name = Get-Bare $name
    $m = [regex]::Match($name, '-(\d+)-\d')
    if ($m.Success) { return [int]$m.Groups[1].Value }
    $m = [regex]::Match($name, '-(\d+)~\d+-')
    if ($m.Success) { return [int]$m.Groups[1].Value }
    $m = [regex]::Match($name, '^(\d+)-')
    if ($m.Success) { return [int]$m.Groups[1].Value }
    $m = [regex]::Match($name, '）(\d+)-')
    if ($m.Success) { return [int]$m.Groups[1].Value }
    return 0
}

function Get-Head([string]$path) {
    $line = [IO.File]::ReadLines($path) | Select-Object -First 1
    if ($null -eq $line) { return '' }
    return $line.TrimStart([char]0xFEFF).Trim()
}

$plan = New-Object System.Collections.ArrayList

foreach ($fam in $families) {
    $dir = Join-Path $src $fam.Dir
    if (-not (Test-Path -LiteralPath $dir)) { continue }
    $hits = @()
    foreach ($f in Get-ChildItem -LiteralPath $dir -File -Filter *.txt) {
        $t = Get-Bare $f.BaseName
        if ($t -notmatch $fam.Match) { continue }
        if ($fam.Need) {
            if ((Get-Head $f.FullName) -notmatch $fam.Need) { continue }
        }
        $hits += $f
    }
    if ($hits.Count -ge 2) {
        [void]$plan.Add([pscustomobject]@{ Title = $fam.Title; Files = @($hits); Span = $fam.Span })
    }
}

$yx = @()
foreach ($d in $yeXuan.Dirs) {
    $dir = Join-Path $src $d
    if (-not (Test-Path -LiteralPath $dir)) { continue }
    foreach ($f in Get-ChildItem -LiteralPath $dir -File -Filter *.txt) {
        $t = Get-Bare $f.BaseName
        if ($t -match $yeXuan.Match -or $t -match $yeXuan.Match2) { $yx += $f }
    }
}
if ($yx.Count -ge 2) {
    [void]$plan.Add([pscustomobject]@{ Title = $yeXuan.Title; Files = @($yx) })
}

# 同章多版本：只留最长的一份，其余进 归档\重复_根级
$dupes = New-Object System.Collections.ArrayList
foreach ($p in $plan) {
    $zeros  = @($p.Files | Where-Object { (Get-Ch $_.BaseName) -eq 0 } | Sort-Object { $_.Name.Length }, Name)
    $others = @($p.Files | Where-Object { (Get-Ch $_.BaseName) -ne 0 })
    $best = @{}; $order = New-Object System.Collections.ArrayList
    foreach ($f in $others) {
        $ch = Get-Ch $f.BaseName
        if (-not $best.ContainsKey($ch)) { $best[$ch] = $f; [void]$order.Add($ch) }
        elseif ($f.Length -gt $best[$ch].Length) { [void]$dupes.Add($best[$ch]); $best[$ch] = $f }
        else { [void]$dupes.Add($f) }
    }
    $p.Files = @($zeros) + @($order | Sort-Object | ForEach-Object { $best[$_] })
}

foreach ($p in $plan) {
    "== {0}  （{1} 篇）" -f $p.Title, $p.Files.Count
    foreach ($f in $p.Files) { "   {0,4}  {1}" -f (Get-Ch $f.BaseName), $f.BaseName }
}
if ($dupes.Count) {
    "同章重复版本 {0} 篇 -> 归档\重复_根级" -f $dupes.Count
    foreach ($d in $dupes) { "   DUP " + $d.Name }
}

if (-not $Apply) { "共 {0} 族；加 -Apply 执行。" -f $plan.Count; return }

$dupDirRoot = Join-Path $root '归档\重复_根级'
foreach ($f in $dupes) {
    $d = Join-Path $dupDirRoot $f.Directory.Name
    if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    Move-Item -LiteralPath $f.FullName -Destination (Join-Path $d $f.Name) -Force
    "DUP  {0}" -f $f.Name
}

$logRows = @()
foreach ($p in $plan) {
    $sb = New-Object System.Text.StringBuilder
    $nums = @()
    foreach ($f in $p.Files) {
        $t = ([IO.File]::ReadAllText($f.FullName)).TrimStart([char]0xFEFF)
        [void]$sb.AppendLine($t.TrimEnd())
        [void]$sb.AppendLine()
        $nums += (Get-Ch $f.BaseName)
    }
    $body  = $sb.ToString().TrimEnd() + "`r`n"
    $chars = ($body -replace '\s', '').Length
    $wc    = if ($chars -ge 10000) { ('{0}w' -f [Math]::Round($chars / 10000.0, 1)).Replace('.0w', 'w') } else { '{0}字' -f $chars }

    $uniq = $nums | Sort-Object -Unique
    $min = ($uniq | Measure-Object -Minimum).Minimum
    $max = ($uniq | Measure-Object -Maximum).Maximum
    $span = if ($p.Span) { $p.Span } elseif ($min -eq 0) { '合集' } else { '{0}~{1}' -f $min, $max }
    $missing = @()
    if ($min -gt 0 -and $max -gt $min) { $missing = ($min..$max) | Where-Object { $uniq -notcontains $_ } }
    if ($missing.Count -gt 0) {
        if ($missing.Count -le 6) { $span += '（缺' + ($missing -join '、') + '）' }
        else { $span += ('（缺{0}章）' -f $missing.Count) }
    }

    $outName = '《{0}》-{1}-{2}.txt' -f $p.Title, $span, $wc
    $outPath = Join-Path $p.Files[0].Directory.FullName $outName
    [IO.File]::WriteAllText($outPath, $body, (New-Object Text.UTF8Encoding $true))

    $bakDir = Join-Path $bak $p.Files[0].Directory.Name
    if (-not (Test-Path -LiteralPath $bakDir)) { New-Item -ItemType Directory -Path $bakDir -Force | Out-Null }
    $moved = @()
    foreach ($f in $p.Files) {
        $target = Join-Path $bakDir $f.Name
        Move-Item -LiteralPath $f.FullName -Destination $target -Force
        $moved += $target
    }
    "OUT  {0}  <- {1} 篇  {2} 字" -f $outName, $p.Files.Count, $chars

    $logRows += [pscustomobject]@{
        Time    = (Get-Date).ToString('s')
        Ip      = $p.Files[0].Directory.Name
        Title   = $p.Title
        Output  = $outPath
        Sources = ($moved -join '|')
        Count   = $moved.Count
        Chars   = $chars
    }
}

$logPath = Join-Path (Join-Path $PSScriptRoot '记录') '合并记录.csv'
$logRows | Export-Csv $logPath -NoTypeInformation -Encoding utf8BOM -Append:$false
"记录：$logPath"
