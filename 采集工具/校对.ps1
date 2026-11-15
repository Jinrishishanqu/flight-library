#requires -Version 7.0
<#
  校对：严格按 README.md《文本格式校对规则》执行
  ────────────────────────────────────────────────────────────────────────
  规则映射：
    读取       严格解码 UTF-8 / UTF-16(BOM) / GB18030，不替换坏字节；DOCX 按正文顺序提取
    换行段落   ① 按每份原文统计常见行宽（区分全角半角）接回固定行宽断行
               ② 行首出现上一行的标点（，。、；：！？”’））…）一律接回
               ③ 章标题/序章/后记/分隔线/独立省略号保留独立行
               ④ 清行尾空白，段间留一空行，CRLF + UTF-8 BOM
               ⑤ 缺线索处保留分段，错字/缺文/乱码原样保留
    章节合并   连续章号拼接，交界留一空行，保留原章标题；正篇/续篇分开编号
    文件命名   《作品》-章节-字数.txt；字数按非空白字符计，≥1万用 w 保留一位小数
    校验       忽略排版空白后，输出字符序列与原文拼接结果必须一致

  用法：
    pwsh -File _采集\校对.ps1 -DryRun
    pwsh -File _采集\校对.ps1                 # 校对 原文库 → 校对后TXT
    pwsh -File _采集\校对.ps1 -Recheck         # 只按清单重跑校验
#>
[CmdletBinding()]
param(
  [string]$Root      = (Split-Path -Parent $PSScriptRoot),
  [string[]]$Source  = @(),
  [string]$OutRoot   = '',
  [switch]$DryRun,
  [switch]$Recheck,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$Utf8Bom   = [System.Text.UTF8Encoding]::new($true)
$Gbk       = [System.Text.Encoding]::GetEncoding(936)
$Strict    = [System.Text.UTF8Encoding]::new($false, $true)

if (-not $OutRoot) { $OutRoot = Join-Path $Root '校对后文章' }
if (-not $Source -or $Source.Count -eq 0) { $Source = @((Join-Path $Root '原文')) }
$LogDir = Join-Path $PSScriptRoot '记录'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$ManifestPath = Join-Path $LogDir '校对清单.csv'

# ══════════════════════════ 读取 ══════════════════════════
function Read-Doc {
  param([string]$Path)
  if ($Path -match '\.docx$') {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('docx-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $Path -DestinationPath $tmp -Force
    $xml = Get-Content (Join-Path $tmp 'word\document.xml') -Raw -Encoding UTF8
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    $t = $xml -replace '</w:p>', "`n" -replace '<w:br[^>]*/>', "`n" -replace '<w:tab[^>]*/>', "`t" -replace '<[^>]+>', ''
    return ($t -replace '&lt;', '<' -replace '&gt;', '>' -replace '&amp;', '&' -replace '&quot;', '"')
  }
  $b = [System.IO.File]::ReadAllBytes($Path)
  if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
    return $Utf8NoBom.GetString($b, 3, $b.Length - 3)
  }
  if ($b.Length -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) {
    return [System.Text.Encoding]::Unicode.GetString($b, 2, $b.Length - 2)
  }
  if ($b.Length -ge 2 -and $b[0] -eq 0xFE -and $b[1] -eq 0xFF) {
    return [System.Text.Encoding]::BigEndianUnicode.GetString($b, 2, $b.Length - 2)
  }
  try { return $Strict.GetString($b) } catch { return $Gbk.GetString($b) }
}

# ══════════════════════════ 排版基础量 ══════════════════════════
function Get-DispWidth {
  param([string]$s)
  $w = 0
  foreach ($ch in $s.ToCharArray()) {
    $c = [int]$ch
    if ($c -lt 128) { $w += 1 } else { $w += 2 }
  }
  return $w
}

function Test-Indent {
  param([string]$s)
  return ($s -match '^(\u3000|\s{2,})')
}

function Test-Heading {
  param([string]$s)
  if ($s -match '^\s*(第[〇零一二三四五六七八九十百千万两\d]+[章节回卷话幕]|序[章言]?|楔子|前言|后记|尾声|番外|Chapter\s*\d+|CHAPTER\s*\d+)') { return $true }
  if ($s -match '^\s*[（(【\[]?\s*\d{1,3}\s*[）)】\]]?\s*$') { return $true }
  if ($s -match '^\s*[-=*—_]{3,}\s*$') { return $true }
  if ($s -match '^\s*[.．…·]{3,}\s*$') { return $true }
  return $false
}

$ContPunct = '^[，。、；：！？,.!?;:％%]|^[」』\u201D\u2019）)】\]…—～~]'

# ══════════════════════════ 断行接回 ══════════════════════════
function Repair-Wrap {
  param([string]$Raw)

  $lines = $Raw -split "\r\n|\n|\r"
  for ($i = 0; $i -lt $lines.Count; $i++) { $lines[$i] = $lines[$i].TrimEnd() }

  # 常见行宽：正文行（宽度 ≥ 24）直方图取众数
  $wHist = @{}
  foreach ($l in $lines) {
    if ($l.Trim().Length -eq 0) { continue }
    $w = Get-DispWidth $l
    if ($w -lt 24) { continue }
    if ($wHist.ContainsKey($w)) { $wHist[$w]++ } else { $wHist[$w] = 1 }
  }
  $W = 0
  if ($wHist.Count -gt 0) {
    $sorted = $wHist.GetEnumerator() | Sort-Object Value -Descending
    $top = $sorted | Select-Object -First 1
    $bodyLines = ($lines | Where-Object { (Get-DispWidth $_) -ge 24 }).Count
    if ($bodyLines -gt 0 -and ($top.Value / $bodyLines) -ge 0.10) { $W = $top.Key }
  }

  # 该文件的缩进规律
  $body = @($lines | Where-Object { $_.Trim().Length -gt 0 })
  $indented = @($body | Where-Object { Test-Indent $_ }).Count
  $hasIndent = ($body.Count -gt 0) -and (($indented / $body.Count) -ge 0.15)

  $out = [System.Collections.Generic.List[string]]::new()
  $i = 0
  while ($i -lt $lines.Count) {
    $cur = $lines[$i]
    if ($cur.Trim().Length -eq 0) { $i++; continue }        # 空行 = 段界，不产出

    $buf = $cur                                           # 保留首行缩进
    $j = $i
    while ($j + 1 -lt $lines.Count) {
      $nxRaw = $lines[$j + 1]
      $nx = $nxRaw.Trim()
      if ($nx.Length -eq 0) { break }                     # 下一行是空行 → 段结束
      if (Test-Heading $buf) { break }
      if (Test-Heading $nx) { break }

      $join = $false; $sep = ''
      if ($nx -match $ContPunct) { $join = $true }                                              # ② 标点错断
      elseif (($buf -match '[A-Za-z0-9]$') -and ($nx -match '^[A-Za-z0-9]')) { $join = $true; $sep = ' ' }   # 半角连读留空格
      elseif ($W -gt 0 -and (Get-DispWidth $buf) -ge ($W - 2) -and -not (Test-Indent $nxRaw)) {
        if ($hasIndent) { $join = $true }                                                       # ① 有缩进规律：无缩进行必是续行
        elseif ($buf -notmatch '[。！？」』\u201D\u2019…）)]$') { $join = $true }                 # 无缩进：句末标点才断段
      }
      if (-not $join) { break }

      $buf = $buf + $sep + $nx
      $j++
    }
    $out.Add($buf)
    $i = $j + 1
  }
  return $out
}

# ══════════════════════════ 输出格式化 ══════════════════════════
function Format-Doc {
  param([System.Collections.Generic.List[string]]$Paras)
  $clean = foreach ($p in $Paras) { $p.TrimEnd() }
  return (($clean -join "`r`n`r`n") + "`r`n")
}

function Get-CharCount {
  param([string]$Text)
  return ($Text -replace '\s', '').Length
}

function Format-Words {
  param([int]$n)
  if ($n -lt 10000) { return "$($n)字" }
  $w = [Math]::Round($n / 10000.0, 1)
  return (("{0}w" -f $w).Replace('.0w', 'w'))
}

function Get-SafeName {
  param([string]$s)
  $s = $s -replace '[\\/:*?"<>|]', { param($m)
      switch ($m.Value) { ':' { '：' } '/' { '／' } '\' { '＼' } '*' { '＊' } '?' { '？' } '"' { '＂' } '<' { '＜' } '>' { '＞' } '|' { '｜' } }
  }
  return $s.Trim()
}

# ══════════════════════════ 文件名解析 ══════════════════════════
function ConvertFrom-Cn {
  param([string]$s)
  if ($s -match '^\d+$') { return [int]$s }
  $digit = @{ '〇' = 0; '零' = 0; '一' = 1; '二' = 2; '两' = 2; '三' = 3; '四' = 4; '五' = 5; '六' = 6; '七' = 7; '八' = 8; '九' = 9 }
  $unit  = @{ '十' = 10; '百' = 100; '千' = 1000 }
  $total = 0; $section = 0; $num = 0
  foreach ($ch in $s.ToCharArray()) {
    $c = [string]$ch
    if ($digit.ContainsKey($c)) { $num = $digit[$c] }
    elseif ($unit.ContainsKey($c)) {
      $u = $unit[$c]
      if ($num -eq 0 -and $u -eq 10) { $num = 1 }
      $section += $num * $u; $num = 0
    }
    else { return $null }
  }
  $total = $section + $num
  if ($total -le 0) { return $null }
  return $total
}

function Parse-BookName {
  param([string]$BaseName)
  $name = $BaseName
  $name = $name -replace '^pixiv-\d+-|^qbtr-\d+-', ''
  $chapter = $null; $part = ''

  # ① 第X章 / 第X回 / 第X话（含中文数字），取最后一个
  $ms = [regex]::Matches($name, '第(?<n>[〇零一二三四五六七八九十百千两\d]+)(?<u>[章节回话幕])')
  if ($ms.Count -gt 0) {
    $last = $ms[$ms.Count - 1]
    $num = ConvertFrom-Cn $last.Groups['n'].Value
    if ($null -ne $num) {
      $chapter = @($num, $num)
      $name = $name.Remove($last.Index, $last.Length)
    }
  }
  # ② 阿拉伯数字区间/单章
  if ($null -eq $chapter) {
    if ($name -match '^(?<t>.*?)[-_\s]*第?(?<a>\d{1,4})[~\-－—到至](?<b>\d{1,4})\s*$') {
      $name = $Matches.t; $chapter = @([int]$Matches.a, [int]$Matches.b)
    } elseif ($name -match '^(?<t>.*?)[-_\s]*第?(?<a>\d{1,4})\s*$') {
      $name = $Matches.t; $chapter = @([int]$Matches.a, [int]$Matches.a)
    }
  }
  if ($name -match '^(?<t>.*?)[-_\s]*篇[-_\s]*(?<a>\d{1,4})') {
    $name = $Matches.t
    if ($null -eq $chapter) { $chapter = @([int]$Matches.a, [int]$Matches.a) }
    $part = '篇'
  }
  if ($name -match '(正篇|续篇)') { $part = $Matches[1] }
  $name = $name -replace '（\s*[\dvV.]+[Ww千万字]+\s*）|\(\s*[\dvV.]+[Ww千万字]+\s*\)', ''
  $name = $name -replace '[（(]\s*\d+\s*[）)]$', ''
  $name = $name -replace '[：:·、,，\s\-_]+$', ''
  $name = $name -replace '^[：:·、,，\s\-_]+', ''
  $name = $name -replace '第[〇零一二三四五六七八九十百千两\d]+[卷]', ''
  $name = $name -replace '[·、，,：:]{2,}', '·'
  $name = $name -replace '·[·、，,：:]', '·'
  $name = $name -replace '[·、，,：:]+$', ''
  $name = $name -replace '^[·、，,：:\s]+', ''
  return [pscustomobject]@{
    Title   = if ($name.Trim()) { $name.Trim() } else { $BaseName }
    Key     = ($name -replace '[\s\-_·、。，,.!！?？:：;；"\u201C\u201D\u2018\u2019（）()]', '').ToLowerInvariant()
    Chapter = $chapter
    Part    = $part
  }
}

function Format-Chapter {
  param($Chapter, [int]$Count)
  if ($null -eq $Chapter) { if ($Count -gt 1) { return "$($Count)篇" } else { return '全篇' } }
  if ($Chapter[0] -eq $Chapter[1]) { return "$($Chapter[0])" }
  return "$($Chapter[0])~$($Chapter[1])"
}

# ══════════════════════════ 校验 ══════════════════════════
function Test-RoundTrip {
  param([string]$OutText, [string[]]$SrcTexts)
  $a = (($SrcTexts -join '') -replace '\s', '')
  $b = ($OutText -replace '\s', '')
  return [pscustomobject]@{ Ok = ($a -eq $b); In = $a.Length; Out = $b.Length }
}

if ($Recheck) {
  if (-not (Test-Path $ManifestPath)) { Write-Host '没有校对清单，先跑一次校对' -ForegroundColor Yellow; return }
  $rows = Import-Csv $ManifestPath
  $bad = 0
  foreach ($r in $rows) {
    if (-not (Test-Path $r.Output)) { Write-Host "缺失：$($r.Output)" -ForegroundColor Red; $bad++; continue }
    $outText = Read-Doc $r.Output
    $src = @($r.Sources -split '\|' | Where-Object { $_ } | ForEach-Object { Read-Doc $_ })
    $v = Test-RoundTrip -OutText $outText -SrcTexts $src
    if (-not $v.Ok) { Write-Host ("不一致：{0}（原 {1} vs 出 {2}）" -f $r.Output, $v.In, $v.Out) -ForegroundColor Red; $bad++ }
  }
  Write-Host ("复校完成：{0} 篇，异常 {1}" -f $rows.Count, $bad) -ForegroundColor Green
  return
}

# ══════════════════════════ 主流程 ══════════════════════════
$jobs = @()   # {Ip, File}
foreach ($s in $Source) {
  if (-not (Test-Path $s)) { continue }
  foreach ($f in Get-ChildItem $s -Recurse -File -Include *.txt, *.docx) {
    if ($f.Name -like '~$*') { continue }
    $ip = if ($f.DirectoryName -eq $s) { Split-Path $s -Leaf } else { $f.Directory.Name }
    if ($ip -eq '原文库') { $ip = '待归类' }
    $jobs += [pscustomobject]@{ Ip = $ip; File = $f }
  }
}
if ($jobs.Count -eq 0) { Write-Host "没有待校对文件（源：$($Source -join ', ')）" -ForegroundColor Yellow; return }

# 幂等：已经在校对清单里的来源不再重复处理（-Force 可强制重跑）
if (-not $Force -and (Test-Path $ManifestPath)) {
  $done = @{}
  foreach ($r in (Import-Csv $ManifestPath)) {
    foreach ($s in ($r.Sources -split '\|')) { if ($s) { $done[$s] = $true } }
  }
  $before = $jobs.Count
  $jobs = @($jobs | Where-Object { -not $done.ContainsKey($_.File.FullName) })
  if ($jobs.Count -lt $before) { Write-Host ("跳过已校对 {0} 份" -f ($before - $jobs.Count)) -ForegroundColor DarkGray }
  if ($jobs.Count -eq 0) { Write-Host '全部已校对过（-Force 可强制重跑）' -ForegroundColor Yellow; return }
}
Write-Host ("待校对 {0} 份" -f $jobs.Count) -ForegroundColor Cyan

# 按 作品key 分组（同组内才可能合并章节）
$groups = $jobs | Group-Object { (Parse-BookName $_.File.BaseName).Key + '|' + (Parse-BookName $_.File.BaseName).Part }

$nOut = 0; $nFail = 0
foreach ($g in $groups) {
  $items = @()
  foreach ($j in $g.Group) {
    $meta = Parse-BookName $j.File.BaseName
    $items += [pscustomobject]@{ Ip = $j.Ip; File = $j.File; Meta = $meta }
  }

  # 章节合并：章号连续（下一份起点 = 上一份终点 + 1）才拼
  $items = $items | Sort-Object @{ e = { if ($_.Meta.Chapter) { $_.Meta.Chapter[0] } else { 0 } } }, @{ e = { $_.File.Name } }
  $bundles = [System.Collections.Generic.List[object]]::new()
  $cur = $null
  foreach ($it in $items) {
    if ($null -eq $cur) { $cur = [pscustomobject]@{ Ip = $it.Ip; Items = @($it); Title = $it.Meta.Title; Start = if ($it.Meta.Chapter) { $it.Meta.Chapter[0] } else { $null }; End = if ($it.Meta.Chapter) { $it.Meta.Chapter[1] } else { $null } }; continue }
    $contig = ($null -ne $cur.End) -and ($null -ne $it.Meta.Chapter) -and ($it.Meta.Chapter[0] -eq ($cur.End + 1))
    if ($contig -and $it.Ip -eq $cur.Ip) {
      $cur.Items += $it; $cur.End = $it.Meta.Chapter[1]
    } else {
      $bundles.Add($cur)
      $cur = [pscustomobject]@{ Ip = $it.Ip; Items = @($it); Title = $it.Meta.Title; Start = if ($it.Meta.Chapter) { $it.Meta.Chapter[0] } else { $null }; End = if ($it.Meta.Chapter) { $it.Meta.Chapter[1] } else { $null } }
    }
  }
  if ($null -ne $cur) { $bundles.Add($cur) }

  foreach ($b in $bundles) {
    $texts = @(); $paras = [System.Collections.Generic.List[string]]::new()
    foreach ($it in $b.Items) {
      $raw = Read-Doc $it.File.FullName
      $texts += $raw
      foreach ($p in (Repair-Wrap $raw)) { $paras.Add($p) }
      $paras.Add('')   # 文件交界留一个空行（合并时）
    }
    if ($paras.Count -gt 0 -and $paras[$paras.Count - 1] -eq '') { $paras.RemoveAt($paras.Count - 1) }
    $outText = Format-Doc $paras
    $chars = Get-CharCount $outText
    $chap = if ($null -ne $b.Start) { if ($b.Start -eq $b.End) { "$($b.Start)" } else { "$($b.Start)~$($b.End)" } } else { if ($b.Items.Count -gt 1) { "$($b.Items.Count)篇" } else { '全篇' } }
    $title = $b.Title
    if ($title -match '(正篇|续篇)') { }
    $fname = (Get-SafeName "《$title》-$chap-$(Format-Words $chars).txt")
    $destDir = Join-Path $OutRoot $b.Ip
    $dest = Join-Path $destDir $fname
    $i = 1
    while (Test-Path -LiteralPath $dest) { $dest = Join-Path $destDir ($fname -replace '\.txt$', "-($i).txt"); $i++ }

    $v = Test-RoundTrip -OutText $outText -SrcTexts $texts
    if (-not $v.Ok) { Write-Warning ("字符序列不一致：{0}（{1} vs {2}）" -f $fname, $v.In, $v.Out); $nFail++ }

    Write-Host ("{0,-52} {1,9}字 → {2}" -f $fname, $chars, $b.Ip) -ForegroundColor $(if ($v.Ok) { 'Cyan' } else { 'Yellow' })
    if (-not $DryRun) {
      New-Item -ItemType Directory -Force -Path $destDir | Out-Null
      [System.IO.File]::WriteAllText($dest, $outText, $Utf8Bom)
      [pscustomobject]@{
        Time    = (Get-Date).ToString('s'); Ip = $b.Ip; Output = $dest
        Sources = (($b.Items | ForEach-Object { $_.File.FullName }) -join '|')
        InChars = $v.In; OutChars = $v.Out; Verified = $v.Ok; Chars = $chars
      } | Export-Csv $ManifestPath -NoTypeInformation -Encoding utf8BOM -Append:((Test-Path $ManifestPath))
    }
    $nOut++
  }
}

Write-Host ""
Write-Host ("校对完成：输出 {0} 份，校验异常 {1} 份。目录 {2}" -f $nOut, $nFail, $OutRoot) -ForegroundColor Green
if ($DryRun) { Write-Host "（-DryRun：未写盘）" -ForegroundColor Yellow }
else { Write-Host "下一步：pwsh -File _采集\校验.ps1" -ForegroundColor DarkCyan }
