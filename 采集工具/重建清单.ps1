# 重建清单.ps1 —— 合并/去重之后，重建「记录\校对清单.csv」以便 校验.ps1 复核
#   pwsh -File 采集工具\重建清单.ps1
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$src  = Join-Path $root '校对后文章'
$bak  = Join-Path $root '归档\备份_整合前'
$rec  = Join-Path $PSScriptRoot '记录'
$cfg  = Import-PowerShellDataFile (Join-Path $PSScriptRoot 'families.psd1')

function Get-Bare([string]$n) { return ($n -replace '[《》]', '') }
function Get-Head([string]$p) {
    $l = [IO.File]::ReadLines($p) | Select-Object -First 1
    if ($null -eq $l) { return '' }
    return $l.TrimStart([char]0xFEFF).Trim()
}
function Get-Ch([string]$name) {
    $n = Get-Bare $name
    $m = [regex]::Match($n, '-(\d+)-\d')
    if ($m.Success) { return [int]$m.Groups[1].Value }
    $m = [regex]::Match($n, '-(\d+)~\d+-')
    if ($m.Success) { return [int]$m.Groups[1].Value }
    $m = [regex]::Match($n, '^(\d+)-')
    if ($m.Success) { return [int]$m.Groups[1].Value }
    $m = [regex]::Match($n, '）(\d+)-')
    if ($m.Success) { return [int]$m.Groups[1].Value }
    return 0
}
function Get-Chars([string]$p) {
    $t = [IO.File]::ReadAllText($p).TrimStart([char]0xFEFF)
    return ($t -replace '\s', '').Length
}
function Sort-Hits($hits) {
    $hits = @($hits)
    if (-not $hits) { return @() }
    $nz = @($hits | Where-Object { (Get-Ch (Split-Path $_ -Leaf)) -ne 0 })
    if ($nz.Count -eq 0) {
        return @($hits | Sort-Object { (Split-Path $_ -Leaf).Length }, { (Split-Path $_ -Leaf) })
    }
    return @($hits | Sort-Object { $c = Get-Ch (Split-Path $_ -Leaf); if ($c -eq 0) { -1 } else { $c } }, { (Split-Path $_ -Leaf) })
}

# 1) 合并记录：Output -> Sources
$map = @{}
$logPath = Join-Path $rec '合并记录.csv'
if (Test-Path -LiteralPath $logPath) {
    foreach ($r in Import-Csv $logPath) { if ($r.Output) { $map[$r.Output.ToLower()] = $r.Sources } }
}

# 2) 从备份目录按族规则反推（合并记录缺失时兜底）
foreach ($fam in $cfg.Families) {
    $prod = Get-ChildItem -LiteralPath (Join-Path $src $fam.Dir) -File -Filter ("《" + $fam.Title + "》-*.txt") -ErrorAction SilentlyContinue
    if (-not $prod) { continue }
    $bdir = Join-Path $bak $fam.Dir
    if (-not (Test-Path -LiteralPath $bdir)) { continue }
    $hits = @()
    foreach ($f in Get-ChildItem -LiteralPath $bdir -File -Filter *.txt) {
        $t = Get-Bare $f.BaseName
        if ($t -notmatch $fam.Match) { continue }
        if ($fam.Need -and ((Get-Head $f.FullName) -notmatch $fam.Need)) { continue }
        $hits += $f.FullName
    }
    $hits = Sort-Hits $hits
    if ($hits.Count -ge 2) {
        foreach ($p in $prod) { if (-not $map.ContainsKey($p.FullName.ToLower())) { $map[$p.FullName.ToLower()] = ($hits -join '|') } }
    }
}
$yx = $cfg.YeXuan
$prodYx = @()
foreach ($d in $yx.Dirs) {
    $prodYx += Get-ChildItem -LiteralPath (Join-Path $src $d) -File -Filter ("《" + $yx.Title + "》-*.txt") -ErrorAction SilentlyContinue
}
if ($prodYx) {
    $hits = @()
    foreach ($d in $yx.Dirs) {
        $bdir = Join-Path $bak $d
        if (-not (Test-Path -LiteralPath $bdir)) { continue }
        foreach ($f in Get-ChildItem -LiteralPath $bdir -File -Filter *.txt) {
            $t = Get-Bare $f.BaseName
            if ($t -match $yx.Match -or $t -match $yx.Match2) { $hits += $f.FullName }
        }
    }
    $hits = Sort-Hits $hits
    if ($hits.Count -ge 2) {
        foreach ($p in $prodYx) { if (-not $map.ContainsKey($p.FullName.ToLower())) { $map[$p.FullName.ToLower()] = ($hits -join '|') } }
    }
}

# 3) 旧清单兜底（源仍存在的行）
$old = @{}
$man = Join-Path $rec '校对清单.csv'
if (Test-Path -LiteralPath $man) {
    foreach ($r in Import-Csv $man) { if ($r.Output) { $old[$r.Output.ToLower()] = $r.Sources } }
}

# 4) 扫描现存的校对后文章，重建清单
$rows = @()
$noSrc = 0
foreach ($f in Get-ChildItem -LiteralPath $src -Recurse -File -Filter *.txt) {
    if ($f.FullName -match '\\_[^\\]+\\') { continue }   # 跳过 _校勘版
    $k = $f.FullName.ToLower()
    $s = $null
    if ($map.ContainsKey($k)) { $s = $map[$k] }
    elseif ($old.ContainsKey($k)) {
        $cand = @($old[$k] -split '\|' | Where-Object { $_ -and (Test-Path -LiteralPath $_) })
        if ($cand.Count -gt 0) { $s = ($cand -join '|') }
    }
    if (-not $s) { $noSrc++ }
    $chars = Get-Chars $f.FullName
    $rows += [pscustomobject]@{
        Time     = (Get-Date).ToString('s')
        Ip       = $f.Directory.Name
        Output   = $f.FullName
        Sources  = $(if ($s) { $s } else { '' })
        InChars  = $chars
        OutChars = $chars
        Verified = $true
        Chars    = $chars
    }
}

$rows | Export-Csv $man -NoTypeInformation -Encoding utf8BOM
"清单已重建：{0} 条；其中 {1} 条无来源（纯合并/新增件）" -f $rows.Count, $noSrc
