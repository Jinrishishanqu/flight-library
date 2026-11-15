# 第一版主（移动版）正文爬取：搜索 → 目录 → 逐章取正文 → 合并成整本 → 落 raw
# 用法：
#   pwsh -NoProfile -File 采集工具\版主爬.ps1 -Queries 斗破苍穹,斗罗大陆 -MaxBooks 5
#   pwsh -NoProfile -File 采集工具\版主爬.ps1 -Queries 斗破苍穹 -DryRun
param(
  [string[]]$Queries = @('斗破苍穹','斗罗大陆','大主宰','武动乾坤','凡人修仙传','遮天','完美世界','神印王座'),
  [int[]]$BookIds = @(),
  [string]$Base = 'https://m.diyibanzhu.space',
  [int]$MaxBooks = 20,
  [int]$MaxChapters = 300,
  [int]$MinChars = 800,
  [int]$DelayMs = 350,
  [string]$OutDir = '',
  [string]$Proxy = '',
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
# 兼容 bash 传参：-Queries "斗破苍穹,斗罗大陆" 会被当成单个字符串，这里再拆一次
$Queries = @($Queries | ForEach-Object { $_ -split '[,，\s]+' } | Where-Object { $_ -ne '' } | Select-Object -Unique)
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $root '采集工具\raw' }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

$UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
$logDir = Join-Path $root '采集工具\记录'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logCsv = Join-Path $logDir '版主采集.csv'

# H 词（与 sources.psd1 的 hWords 口径一致，取高频那批）
$hWords = @('淫','操','肉棒','鸡巴','龟头','阴蒂','阴唇','阴道','后穴','奶子','乳房','乳头','射精','精液',
            '高潮','呻吟','抽插','淫水','淫液','骚','贱','调教','凌辱','强奸','奸','肉欲','快感','发情',
            '媚药','春药','奴','母狗','淫荡','淫乱','淫靡','娇喘','挺进','插入','内射','中出','爆乳')

function Get-Page {
  param([string]$Url, [string]$Method = 'GET', $Body = $null)
  $p = @{
    Uri = $Url; Method = $Method; UserAgent = $UA; TimeoutSec = 40;
    Headers = @{ 'Accept-Language' = 'zh-CN,zh;q=0.9'; 'Referer' = $Base + '/' }
  }
  if ($Body) { $p.Body = $Body; $p.ContentType = 'application/x-www-form-urlencoded' }
  if ($Proxy) { $p.Proxy = $Proxy }
  $r = Invoke-WebRequest @p
  return $r.Content
}

function Clean-Body {
  param([string]$Html)
  $m = [regex]::Match($Html, '(?s)id="nr1"(?:\s[^>]*)?>(.*?)(?:</div>\s*<div|</div>\s*</div>|$)')
  $t = if ($m.Success) { $m.Groups[1].Value } else { '' }
  if (-not $t) { return '' }
  $t = [regex]::Replace($t, '(?is)<script.*?</script>', '')
  $t = [regex]::Replace($t, '(?is)<div[^>]*id="announceinfo".*?</div>', '')
  $t = [regex]::Replace($t, '(?i)<br\s*/?>', "`n")
  $t = [regex]::Replace($t, '(?i)</p>', "`n")
  $t = [regex]::Replace($t, '(?s)<[^>]+>', '')
  $t = [System.Net.WebUtility]::HtmlDecode($t)
  $t = $t -replace "`r", ''
  # 去掉头部「作者：xx / 字数：xx / 日期 / 章节名」与行首全角缩进
  $lines = $t -split "`n" | ForEach-Object { ($_ -replace "[\u3000\u00a0]", ' ').Trim() }
  $out = New-Object System.Collections.Generic.List[string]
  $skip = 0
  foreach ($ln in $lines) {
    if ($ln -eq '') { if ($out.Count -gt 0) { $out.Add('') }; continue }
    if ($skip -lt 4 -and ($ln -match '^(作者|字数|日期)[：:]' -or $ln -match '^\d{2,4}年\d{1,2}月\d{1,2}日$' -or $ln -match '^\d{4}-\d{2}-\d{2}')) { $skip++; continue }
    # 站方页脚噪声：分页提示、最新章节、广告串
    if ($ln -match '数字分页|最新章节请访问|请记住本站|本站域名|天才一秒记住|手机用户请浏览|加入书签|投推荐票') { continue }
    if ($ln -match '^https?://') { continue }
    $out.Add($ln)
  }
  return (($out -join "`n") -replace "`n{3,}", "`n`n").Trim()
}

function Get-HScore {
  param([string]$Text)
  $n = 0
  foreach ($w in $hWords) {
    $c = ([regex]::Matches($Text, [regex]::Escape($w))).Count
    if ($c -gt 0) { $n++ }
  }
  return $n
}

$stamp = Get-Date
$results = New-Object System.Collections.Generic.List[object]
$seen = @{}

foreach ($q in $Queries) {
  Write-Host "== 搜索：$q" -ForegroundColor Cyan
  try {
    $html = Get-Page "$Base/wap.php?action=search" 'POST' @{ wd = $q; objectType = '2' }
  } catch {
    Write-Host "  搜索失败：$($_.Exception.Message)" -ForegroundColor Red
    continue
  }
  $books = @()
  foreach ($m in [regex]::Matches($html, '<a[^>]*href="/list/(\d+)\.html"[^>]*>([^<]+)</a>')) {
    $books += [pscustomobject]@{ Id = [int]$m.Groups[1].Value; Title = ($m.Groups[2].Value -replace '^\s+|\s+$', '') }
  }
  $books = $books | Sort-Object Id -Unique
  if ($BookIds.Count -gt 0) {
    $books = $books | Where-Object { $BookIds -contains $_.Id }
    if ($books.Count -eq 0) { $books = @($BookIds | ForEach-Object { [pscustomobject]@{ Id = $_; Title = "[$_]" } }) }
  }
  Write-Host "  命中 $($books.Count) 本"

  $take = 0
  foreach ($b in $books) {
    if ($take -ge $MaxBooks) { break }
    if ($seen.ContainsKey($b.Id)) { continue }
    $seen[$b.Id] = $true
    $take++

    Write-Host ("  · [{0}] {1}" -f $b.Id, $b.Title)
    try { $listHtml = Get-Page "$Base/list/$($b.Id).html" } catch { Write-Host "    目录失败" -ForegroundColor Yellow; continue }
    Start-Sleep -Milliseconds $DelayMs

    $bm = [regex]::Match($listHtml, '(?s)<h1[^>]*>(.*?)</h1>')
    $realTitle = if ($bm.Success) { ([regex]::Replace($bm.Groups[1].Value, '(?s)<[^>]+>', '')).Trim() } else { $b.Title }

    $chap = @()
    foreach ($m in [regex]::Matches($listHtml, '<a[^>]*href="/view/(\d+)\.html"[^>]*>([^<]*)</a>')) {
      $chap += [pscustomobject]@{ Id = [int]$m.Groups[1].Value; Name = ($m.Groups[2].Value -replace '^\s+|\s+$', '') }
    }
    # 章节按页面 id 升序 = 发布顺序
    $chap = $chap | Sort-Object Id -Unique
    if ($chap.Count -eq 0) { Write-Host "    无章节" -ForegroundColor Yellow; continue }
    if ($chap.Count -gt $MaxChapters) { $chap = $chap[0..($MaxChapters - 1)] }

    $sb = New-Object System.Text.StringBuilder
    $got = 0
    foreach ($c in $chap) {
      try {
        $vHtml = Get-Page "$Base/view/$($c.Id).html"
        $txt = Clean-Body $vHtml
        # 章节内分页：/view/<id>_2.html、_3.html ...
        $maxPage = 1
        foreach ($pm in [regex]::Matches($vHtml, "/view/$($c.Id)_(\d+)\.html")) {
          $pn = [int]$pm.Groups[1].Value
          if ($pn -gt $maxPage) { $maxPage = $pn }
        }
        if ($maxPage -gt 1) {
          for ($pn = 2; $pn -le $maxPage; $pn++) {
            Start-Sleep -Milliseconds $DelayMs
            try {
              $pHtml = Get-Page "$Base/view/$($c.Id)_$pn.html"
              $pt = Clean-Body $pHtml
              if ($pt.Length -gt 50) { $txt = $txt + "`r`n" + $pt }
            } catch {
              Write-Host ("    章 {0} 第 {1} 页失败" -f $c.Id, $pn) -ForegroundColor DarkYellow
            }
          }
        }
        if ($txt.Length -ge 100) {
          [void]$sb.AppendLine($c.Name)
          [void]$sb.AppendLine($txt)
          [void]$sb.AppendLine('')
          $got++
        }
      } catch {
        Write-Host ("    章 {0} 失败：{1}" -f $c.Id, $_.Exception.Message) -ForegroundColor Yellow
      }
      Start-Sleep -Milliseconds $DelayMs
    }

    $body = $sb.ToString().Trim()
    $chars = ($body -replace '\s', '').Length
    $score = Get-HScore $body
    Write-Host ("    {0} 章 → {1} 字，H 词 {2}" -f $got, $chars, $score)

    if ($chars -lt $MinChars) { Write-Host "    字数不足，跳过" -ForegroundColor Yellow; continue }
    if ($score -lt 2) { Write-Host "    H 词密度不足，跳过" -ForegroundColor Yellow; continue }

    $safe = ($realTitle -replace '[\\/:*?"<>|]', '_')
    $wc = if ($chars -ge 10000) { ('{0}w' -f [Math]::Round($chars / 10000.0, 1)).Replace('.0w', 'w') } else { '{0}字' -f $chars }
    $name = "$safe.txt"
    $path = Join-Path $OutDir $name
    if (Test-Path -LiteralPath $path) {
      $name = "$safe-2.txt"; $path = Join-Path $OutDir $name
    }
    if (-not $DryRun) {
      $utf8 = New-Object System.Text.UTF8Encoding($true)
      [System.IO.File]::WriteAllText($path, ($body -replace "`r?`n", "`r`n"), $utf8)
    }
    $results.Add([pscustomobject]@{
      Time = (Get-Date).ToString('s'); Source = 'diyibanzhu'; Id = $b.Id; Title = $realTitle;
      Query = $q; Chapters = $got; Chars = $chars; HScore = $score;
      Url = "$Base/list/$($b.Id).html"; File = $path
    })
  }
}

if ($results.Count -gt 0 -and -not $DryRun) {
  $new = $results | Select-Object Time, Source, Id, Title, Query, Chapters, Chars, HScore, Url, File
  if (Test-Path $logCsv) {
    $new | Export-Csv -LiteralPath $logCsv -Append -NoTypeInformation -Encoding UTF8
  } else {
    $new | Export-Csv -LiteralPath $logCsv -NoTypeInformation -Encoding UTF8
  }
}

Write-Host ""
Write-Host "本次产出 $($results.Count) 本，落地目录：$OutDir" -ForegroundColor Green
$results | Select-Object Title, Chapters, Chars, HScore | Format-Table -AutoSize
