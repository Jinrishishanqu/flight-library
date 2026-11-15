# 整合.ps1 —— 把同一本书散落的章节/版本整合成一件
# 计划文件：采集工具\整合计划.psd1
# 用法：
#   pwsh -File 采集工具\整合.ps1                      # DryRun
#   pwsh -File 采集工具\整合.ps1 -Only 薰儿线           # 只跑标题含该词的族
#   pwsh -File 采集工具\整合.ps1 -Apply                # 执行
param(
  [string]$PlanFile = '',
  [string]$Only = '',
  [switch]$Apply,
  [switch]$KeepSource
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $PlanFile) { $PlanFile = Join-Path $PSScriptRoot '整合计划.psd1' }
if (-not (Test-Path -LiteralPath $PlanFile)) { throw "找不到计划文件：$PlanFile" }
$plan = Import-PowerShellDataFile -LiteralPath $PlanFile
$families = @($plan.Families)
if ($Only) { $families = @($families | Where-Object { $_.Title -like "*$Only*" }) }
if ($families.Count -eq 0) { throw '没有匹配的族' }

$utf8 = New-Object System.Text.UTF8Encoding($true)
$logPath = Join-Path $root '采集工具\记录\整合记录.csv'
$recDir = Split-Path $logPath -Parent
if (-not (Test-Path -LiteralPath $recDir)) { New-Item -ItemType Directory -Path $recDir -Force | Out-Null }

function Convert-CnNum([string]$s) {
  if (-not $s) { return 0 }
  if ($s -match '^\d+$') { return [int]$s }
  $map = @{ '零' = 0; '〇' = 0; '一' = 1; '二' = 2; '两' = 2; '三' = 3; '四' = 4; '五' = 5; '六' = 6; '七' = 7; '八' = 8; '九' = 9 }
  $unit = @{ '十' = 10; '百' = 100; '千' = 1000; '万' = 10000 }
  $total = 0; $section = 0; $num = 0
  foreach ($ch in $s.ToCharArray()) {
    $c = [string]$ch
    if ($map.ContainsKey($c)) { $num = $map[$c] }
    elseif ($unit.ContainsKey($c)) {
      $u = $unit[$c]
      if ($u -eq 10000) { $section = ($section + $num) * $u; $total += $section; $section = 0; $num = 0 }
      else { if ($num -eq 0) { $num = 1 }; $section += $num * $u; $num = 0 }
    }
  }
  return $total + $section + $num
}

$chRx = '【第([0-9一二三四五六七八九十百零〇两]+)\s*(?:回|章)'

function Get-Ch([string]$fileName, [string]$head) {
  $bare = $fileName -replace '\.txt$', '' -replace '[《》]', ''
  if ($bare -match '-(\d+)~(\d+)-') { return [int]$Matches[1] }
  if ($bare -match '-(\d+)-') { return [int]$Matches[1] }
  if ($head -match '第([0-9一二三四五六七八九十百零〇两]+)\s*(?:回|章)') { return (Convert-CnNum $Matches[1]) }
  return 0
}

function Get-Head([string]$path) {
  $sr = New-Object System.IO.StreamReader($path, [System.Text.Encoding]::UTF8, $true)
  $line = $sr.ReadLine()
  $sr.Close()
  if ($null -eq $line) { return '' }
  return $line.TrimStart([char]0xFEFF).Trim()
}

function Get-Chars([string]$path) {
  $t = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
  return ($t -replace '\s', '').Length
}

function Get-WcTag([int]$chars) {
  if ($chars -ge 10000) { return (('{0}w' -f [Math]::Round($chars / 10000.0, 1)).Replace('.0w', 'w')) }
  return ('{0}字' -f $chars)
}

# 把一个整本文件按【第X回/章】切成若干段，返回 @{Ch;Text}
function Split-ByChapter([string]$text, [int]$fallbackCh) {
  $out = @()
  $ms = [regex]::Matches($text, $chRx)
  if ($ms.Count -eq 0) { return @([pscustomobject]@{ Ch = $fallbackCh; Text = $text.Trim() }) }
  if ($ms[0].Index -gt 0) {
    $pre = $text.Substring(0, $ms[0].Index).Trim()
    if ($pre.Length -gt 0) { $out += [pscustomobject]@{ Ch = 0; Text = $pre } }
  }
  for ($i = 0; $i -lt $ms.Count; $i++) {
    $st = $ms[$i].Index
    $ed = if ($i + 1 -lt $ms.Count) { $ms[$i + 1].Index } else { $text.Length }
    $seg = $text.Substring($st, $ed - $st).Trim()
    $ch = Convert-CnNum $ms[$i].Groups[1].Value
    $out += [pscustomobject]@{ Ch = $ch; Text = $seg }
  }
  return $out
}

function Add-WithOverlap([System.Text.StringBuilder]$sbr, [string]$text) {
  if ($sbr.Length -eq 0) { $sbr.Append($text) | Out-Null; return }
  $acc = $sbr.ToString()
  $probeLen = [Math]::Min(40, $text.Length)
  if ($probeLen -ge 12) {
    $probe = $text.Substring(0, $probeLen)
    $tailStart = [Math]::Max(0, $acc.Length - 8000)
    $idx = $acc.IndexOf($probe, $tailStart)
    if ($idx -ge 0) {
      $overlap = $acc.Length - $idx
      if ($overlap -lt $text.Length) { $text = $text.Substring($overlap) } else { return }
    }
  }
  $sbr.Append("`r`n`r`n").Append($text) | Out-Null
}

function Write-Log([string]$line) {
  if (-not (Test-Path -LiteralPath $logPath)) {
    [System.IO.File]::WriteAllText($logPath, "Time,Dir,Title,Mode,Chars,Dropped,Output`r`n", $utf8)
  }
  [System.IO.File]::AppendAllText($logPath, $line + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
}

$summary = @()
foreach ($fam in $families) {
  $dirName = $fam.Dir
  $searchDirs = @()
  if ($fam.Dirs) { foreach ($d in $fam.Dirs) { $searchDirs += (Join-Path $root $d) } }
  else { $searchDirs += (Join-Path $root ('校对后文章\' + $dirName)) }

  Write-Host ''
  Write-Host ("=== " + $fam.Title + " ===") -ForegroundColor Magenta

  $hits = @()
  foreach ($sd in $searchDirs) {
    if (-not (Test-Path -LiteralPath $sd)) { continue }
    foreach ($f in (Get-ChildItem -LiteralPath $sd -File -Filter *.txt)) {
      $bare = $f.Name -replace '\.txt$', ''
      $ok = $false
      foreach ($rx in @($fam.Include)) { if ($bare -match $rx) { $ok = $true; break } }
      if (-not $ok) { continue }
      $skip = $false
      if ($fam.Exclude) { foreach ($rx in @($fam.Exclude)) { if ($bare -match $rx) { $skip = $true; break } } }
      if ($skip) { continue }
      if ($fam.Base -and ($bare -match $fam.Base)) { continue }
      $head = Get-Head $f.FullName
      if ($fam.HeadPattern -and ($head -notmatch $fam.HeadPattern)) { continue }
      $ch = if ($fam.NoChapter) { 0 } else { Get-Ch $f.Name $head }
      $chars = Get-Chars $f.FullName
      $hits += [pscustomobject]@{ Path = $f.FullName; Name = $f.Name; Head = $head; Ch = $ch; Chars = $chars; IsBase = $false }
    }
  }
  # Base：已有的合并整本，先按章切段再参与去重
  if ($fam.Base) {
    foreach ($sd in $searchDirs) {
      if (-not (Test-Path -LiteralPath $sd)) { continue }
      foreach ($f in (Get-ChildItem -LiteralPath $sd -File -Filter *.txt)) {
        $bare = $f.Name -replace '\.txt$', ''
        if ($bare -notmatch $fam.Base) { continue }
        $chars = Get-Chars $f.FullName
        $hits += [pscustomobject]@{ Path = $f.FullName; Name = $f.Name; Head = (Get-Head $f.FullName); Ch = 0; Chars = $chars; IsBase = $true }
      }
    }
  }
  if ($hits.Count -eq 0) { Write-Host '    （无成员，跳过）' -ForegroundColor Yellow; continue }

  if ($fam.Mode -eq 'KeepBest') {
    $sorted = $hits | Sort-Object -Property @{ Expression = 'Chars'; Descending = $true }
    $keep = $sorted[0]
    $drop = @($sorted | Select-Object -Skip 1)
    $chars = $keep.Chars
    $wc = Get-WcTag $chars
    $outName = ('《{0}》-{1}-{2}.txt' -f $fam.Title, $(if ($fam.Span) { $fam.Span } else { '全篇' }), $wc)
    Write-Host ("    保留：" + $keep.Name + "  " + $keep.Chars + " 字 → " + $outName) -ForegroundColor Green
    foreach ($d in $drop) { Write-Host ("    重复： " + $d.Name + "  " + $d.Chars + " 字") -ForegroundColor DarkGray }
    if ($Apply) {
      $dedupDir = Join-Path $root ('归档\重复_校对后\整合\' + $dirName)
      if (-not (Test-Path -LiteralPath $dedupDir)) { New-Item -ItemType Directory -Path $dedupDir -Force | Out-Null }
      foreach ($d in $drop) { if (Test-Path -LiteralPath $d.Path) { Move-Item -LiteralPath $d.Path -Destination $dedupDir -Force } }
      if ($keep.Name -ne $outName) {
        $target = Join-Path (Split-Path $keep.Path -Parent) $outName
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
        Rename-Item -LiteralPath $keep.Path -NewName $outName
      }
      Write-Log ('{0},{1},{2},{3},{4},{5},{6}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $dirName, $fam.Title, 'KeepBest', $chars, @($drop).Count, $outName)
    }
    $summary += [pscustomobject]@{ Title = $fam.Title; Mode = 'KeepBest'; Keep = $hits.Count; Chars = $chars; Out = $outName }
    continue
  }

  # Concat：全部切成章段 → 按章号取长 → 排序拼接
  $segs = @()
  $usedFiles = @()
  foreach ($h in $hits) {
    $txt = [System.IO.File]::ReadAllText($h.Path, [System.Text.Encoding]::UTF8)
    $parts = Split-ByChapter $txt $h.Ch
    foreach ($p in $parts) { $segs += [pscustomobject]@{ Ch = $p.Ch; Text = $p.Text; From = $h.Name; Chars = (($p.Text -replace '\s', '').Length) } }
    $usedFiles += $h
  }
  # 同章取长（章号 0 表示无章号，全部保留、按文件名排序）
  $zero = @($segs | Where-Object { $_.Ch -eq 0 } | Sort-Object -Property From, Chars)
  $byCh = @{}
  foreach ($s in $segs) {
    if ($s.Ch -eq 0) { continue }
    $k = $s.Ch
    if (-not $byCh.ContainsKey($k) -or $byCh[$k].Chars -lt $s.Chars) { $byCh[$k] = $s }
  }
  $order = @($byCh.Keys | Sort-Object)
  $sbr = New-Object System.Text.StringBuilder
  foreach ($z in $zero) {
    Write-Host ("      #0    {0,7} 字  ← {1}" -f $z.Chars, $z.From) -ForegroundColor DarkGray
    Add-WithOverlap $sbr $z.Text
  }
  foreach ($k in $order) { Add-WithOverlap $sbr $byCh[$k].Text }
  $body = $sbr.ToString()
  $chars = ($body -replace '\s', '').Length
  $chs = @($order | Where-Object { $_ -gt 0 } | Sort-Object)
  $span = if ($fam.Span) { $fam.Span }
          elseif ($chs.Count -eq 0) { '合集' }
          elseif ($chs.Count -eq 1) { [string]$chs[0] }
          else { '{0}~{1}' -f $chs[0], $chs[-1] }
  if (-not $fam.Span -and $chs.Count -gt 1) {
    $missing = @()
    for ($i = $chs[0]; $i -le $chs[-1]; $i++) { if ($chs -notcontains $i) { $missing += $i } }
    if ($missing.Count -gt 0 -and $missing.Count -le 8) { $span += ('（缺' + ($missing -join '、') + '）') }
    elseif ($missing.Count -gt 8) { $span += ('（缺{0}章）' -f $missing.Count) }
  }
  $wc = Get-WcTag $chars
  $outName = ('《{0}》-{1}-{2}.txt' -f $fam.Title, $span, $wc)
  $outDir = Join-Path $root ('校对后文章\' + $dirName)
  $outPath = Join-Path $outDir $outName

  Write-Host ("    文件 {0} 个 → 章段 {1} 个（章号 {2}）→ {3}" -f $hits.Count, $segs.Count, $order.Count, $outName) -ForegroundColor Green
  foreach ($k in $order) {
    $s = $byCh[$k]
    Write-Host ("      #{0,-4} {1,7} 字  ← {2}" -f $k, $s.Chars, $s.From) -ForegroundColor DarkGray
  }

  if ($Apply) {
    if (Test-Path -LiteralPath $outPath) { Remove-Item -LiteralPath $outPath -Force }
    [System.IO.File]::WriteAllText($outPath, ($body -replace "`r?`n", "`r`n"), $utf8)
    if (-not $KeepSource) {
      $bak = Join-Path $root ('归档\备份_校对后\整合\' + $dirName)
      if (-not (Test-Path -LiteralPath $bak)) { New-Item -ItemType Directory -Path $bak -Force | Out-Null }
      foreach ($u in $usedFiles) { if (Test-Path -LiteralPath $u.Path) { Move-Item -LiteralPath $u.Path -Destination $bak -Force } }
    }
    Write-Log ('{0},{1},{2},{3},{4},{5},{6}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $dirName, $fam.Title, 'Concat', $chars, $usedFiles.Count, $outName)
  }
  $summary += [pscustomobject]@{ Title = $fam.Title; Mode = 'Concat'; Keep = $usedFiles.Count; Chars = $chars; Out = $outName }
}

Write-Host ''
Write-Host '--- 汇总 ---' -ForegroundColor Cyan
$summary | Format-Table -AutoSize
if (-not $Apply) { Write-Host '（DryRun，未改动任何文件；确认后加 -Apply）' -ForegroundColor Yellow }
