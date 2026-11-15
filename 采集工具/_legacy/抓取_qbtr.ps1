#requires -Version 7.0
<#
  全本同人小说网（qbtr.org）批量抓取器
  用法：
    pwsh -File _采集\抓取_qbtr.ps1 -Ids 10209,9699              # 指定书号
    pwsh -File _采集\抓取_qbtr.ps1 -Filter '艳|后宫|奴|调教' -Max 6   # 按标题关键词
    pwsh -File _采集\抓取_qbtr.ps1 -All -Max 20                # 全站前 20 本（榜单顺序）
  产出：_采集\raw\<书名>.txt  →  再跑 入库规范化.ps1 归档
#>
[CmdletBinding(DefaultParameterSetName = 'Filter')]
param(
  [Parameter(ParameterSetName = 'Ids')][int[]]$Ids,
  [Parameter(ParameterSetName = 'Filter')][string]$Filter = '斗破|斗罗|大主宰|武动|凡人|仙逆|元尊|遮天|完美世界|神墓|诛仙|星辰谷|吞噬星空|择天记|诡秘|大奉|剑来|万相|一念永恒|圣墟|绝世唐门',
  [Parameter(ParameterSetName = 'All')][switch]$All,
  [int]$Max = 100,
  [string]$OutDir = (Join-Path $PSScriptRoot 'raw'),
  [int]$SleepMs = 800
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ProgressPreference = 'SilentlyContinue'
$Base = 'https://www.qbtr.org'
$UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
$H = @{ 'User-Agent' = $UA; 'Referer' = "$Base/tongren/" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Get-Page { param([string]$Url)
  for ($i = 1; $i -le 3; $i++) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -Headers $H -TimeoutSec 30).Content }
    catch { Start-Sleep -Milliseconds (600 * $i) }
  }
  return $null
}

# ── 1. 取书目列表 ────────────────────────────────────────────────────────────
$books = [System.Collections.Generic.List[object]]::new()
if ($PSCmdlet.ParameterSetName -eq 'Ids') {
  foreach ($id in $Ids) { $books.Add([pscustomobject]@{ Id = $id; Title = '' }) }
}
else {
  for ($p = 1; $p -le 31 -and $books.Count -lt $Max; $p++) {
    $u = if ($p -eq 1) { "$Base/tongren/" } else { "$Base/tongren/index_$p.html" }
    $html = Get-Page $u
    if (-not $html) { continue }
    foreach ($m in [regex]::Matches($html, 'href="(/tongren/(\d+)\.html)"')) {
      $id = [int]$m.Groups[2].Value
      if ($books.Id -contains $id) { continue }
      $tail = $html.Substring($m.Index, [Math]::Min(600, $html.Length - $m.Index))
      $t = [regex]::Match($tail, '<h3[^>]*>([\s\S]{1,60}?)</h3>')
      $title = if ($t.Success) { ($t.Groups[1].Value -replace '<[^>]+>', '').Trim() } else { "book$id" }
      if (-not $All -and $Filter -and $title -notmatch $Filter) { continue }
      $books.Add([pscustomobject]@{ Id = $id; Title = $title })
      if ($books.Count -ge $Max) { break }
    }
    Start-Sleep -Milliseconds $SleepMs
  }
}

Write-Host ("待抓取 {0} 本" -f $books.Count) -ForegroundColor Cyan
$ok = 0; $fail = 0
$log = [System.Collections.Generic.List[object]]::new()

foreach ($b in $books) {
  try {
    # 书名（Ids 模式下补全）
    $title = $b.Title
    if (-not $title) {
      $bh = Get-Page "$Base/tongren/$($b.Id).html"
      $tm = [regex]::Match($bh, '<title>([^<(]{1,80})')
      $title = if ($tm.Success) { $tm.Groups[1].Value.Trim() } else { "book$($b.Id)" }
      $title = $title -replace '[:：]', '：'
    }

    # 取下载直链（帝国CMS：txt 页里带 pass 令牌）
    $tp = Get-Page "$Base/txt/2-$($b.Id)-0.html"
    if (-not $tp) { throw 'txt页取不到' }
    $pm = [regex]::Match($tp, 'doaction\.php\?enews=DownSoft&classid=2&id=(\d+)&pathid=0&pass=([0-9a-f]+)')
    if (-not $pm.Success) { throw '未找到下载令牌（可能需VIP/登录）' }
    $dl = "$Base/e/DownSys/doaction.php?enews=DownSoft&classid=2&id=$($b.Id)&pathid=0&pass=$($pm.Groups[2].Value)&p=::::::"

    $resp = Invoke-WebRequest -Uri $dl -UseBasicParsing -Headers $H -TimeoutSec 90
    $bytes = $resp.RawContentStream.ToArray()
    if ($bytes.Length -lt 5000) { throw "内容过小($($bytes.Length)B)" }
    if ($resp.Headers.'Content-Type' -match 'html') { throw '返回的是网页不是文件（限流/需登录）' }

    $safe = ($title -replace '[\\/:*?"<>|]', '_')
    $path = Join-Path $OutDir "$safe.txt"
    [System.IO.File]::WriteAllBytes($path, $bytes)
    $size = [math]::Round($bytes.Length / 1KB, 1)
    Write-Host ("OK   {0,-28} {1,8} KB  {2}" -f $title, $size, $path) -ForegroundColor Green
    $ok++
    $log.Add([pscustomobject]@{ Time = (Get-Date).ToString('s'); Id = $b.Id; Title = $title; KB = $size; Url = "$Base/tongren/$($b.Id).html"; Status = 'OK' })
  }
  catch {
    Write-Host ("FAIL {0} {1} — {2}" -f $b.Id, $b.Title, $_.Exception.Message) -ForegroundColor DarkYellow
    $fail++
    $log.Add([pscustomobject]@{ Time = (Get-Date).ToString('s'); Id = $b.Id; Title = $b.Title; KB = 0; Url = "$Base/tongren/$($b.Id).html"; Status = "FAIL: $($_.Exception.Message)" })
  }
  Start-Sleep -Milliseconds $SleepMs
}

$logPath = Join-Path $PSScriptRoot '抓取日志.csv'
$log | Export-Csv $logPath -NoTypeInformation -Encoding utf8BOM -Append:$((Test-Path $logPath))
Write-Host ("完成：成功 {0}，失败 {1}。下一步跑 入库规范化.ps1 -DryRun 检查，再正式入库。" -f $ok, $fail) -ForegroundColor Cyan
