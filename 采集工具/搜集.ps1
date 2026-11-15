#requires -Version 7.0
<#
  搜集：多源 H 文抓取器
  ─────────────────────────────────────────────────────────────
  用法：
    # pixiv 按 tag 抓（同人 H 主场，中文 tag 全匹配）
    pwsh -File _采集\搜集.ps1 -Source pixiv -Tags 斗破苍穹,斗罗大陆 -Pages 2

    # 只抓 H 度达标的（默认 12/千字以上）
    pwsh -File _采集\搜集.ps1 -Source pixiv -Tags 斗破苍穹 -Pages 5 -HMin 12

    # 备源：qbtr 指定书号
    pwsh -File _采集\搜集.ps1 -Source qbtr -Ids 10209,9653

  产物：_采集\raw\<IP>\<源>-<id>-<标题>.txt   （原样落盘，不做任何清洗）
         _采集\采集记录.csv                  （来源/标签/字数/H度，供入库与校对追溯）
#>
[CmdletBinding()]
param(
  [ValidateSet('pixiv', 'qbtr')][string]$Source = 'pixiv',
  [string[]]$Tags,
  [int]$Pages = 1,
  [ValidateSet('date_d', 'popular_d')][string]$Order = 'date_d',
  [string[]]$Queries,
  [switch]$Auto,
  [string[]]$Targets,
  [ValidateSet('tudou', 'sanshao', 'chendong', 'works')][string]$Group,
  [string[]]$HQueries,
  [int]$PerQuery = 8,
  [int[]]$Ids,
  [int]$HMin = 2,
  [int]$MinChars = 800,
  [int]$SleepMs = 700,
  [string]$RawRoot = (Join-Path $PSScriptRoot 'raw')
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ProgressPreference = 'SilentlyContinue'
$Cfg = Import-PowerShellDataFile (Join-Path $PSScriptRoot 'sources.psd1')
$UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
$LogDir  = Join-Path $PSScriptRoot '记录'
$LogPath = Join-Path $LogDir '采集记录.csv'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $RawRoot | Out-Null

function Get-Json {
  param([string]$Url, [string]$Referer)
  $h = @{ 'User-Agent' = $UA; 'Accept' = 'application/json'; 'Referer' = $Referer }
  for ($i = 1; $i -le 3; $i++) {
    try {
      $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -Headers $h -TimeoutSec 40
      return ($r.Content | ConvertFrom-Json -AsHashtable)   # -AsHashtable：pixiv 的 tag 键大小写混用（ntr/NTR）会让普通转换报错
    } catch {
      Write-Host ("  [调试] 请求失败 {0}: {1}" -f $Url, $_.Exception.Message) -ForegroundColor DarkRed
      if ($i -eq 3) { return $null }
      Start-Sleep -Milliseconds (900 * $i)
    }
  }
}

function Get-HScore {
  param([string]$Text, [string]$Tags)
  # 标签命中即判定为 H（比正文词频更可靠，繁简通吃）
  if ($Tags -and $Tags -match '中出|口交|乳交|足交|肛交|性交|凌辱|调教|强奸|诱奸|内射|射精|潮吹|失禁|淫|肉文|肉玩具|性奴|NTR|牛头人|绿帽|H$|R-18|成人|工口|エロ|孕|孕ませ') { return 99 }
  if (-not $Text) { return 0 }
  $n = 0
  foreach ($w in $Cfg.hWords) { $n += ([regex]::Matches($Text, [regex]::Escape($w))).Count }
  $kw = [Math]::Max(1, ($Text -replace '\s', '').Length / 1000.0)
  return [Math]::Round($n / $kw, 1)
}

function Resolve-Ip {
  param([string]$Name, [string]$Head)
  $best = '待归类'; $bestScore = 0
  foreach ($k in $Cfg.ipRules.Keys) {
    $pat = $Cfg.ipRules[$k]
    $s = 3 * ([regex]::Matches($Name, $pat)).Count
    if ($Head) { $s += [regex]::Matches($Head, $pat).Count }
    if ($s -gt $bestScore) { $bestScore = $s; $best = $k }
  }
  return $best
}

function Save-Raw {
  param([string]$Ip, [string]$Name, [string]$Text)
  $dir = Join-Path $RawRoot $Ip
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $safe = ($Name -replace '[\\/:*?"<>|\[\]{}]', '_').Trim()
  if ($safe.Length -gt 70) { $safe = $safe.Substring(0, 70) }
  $p = Join-Path $dir "$safe.txt"
  $i = 1
  while (Test-Path -LiteralPath $p) { $p = Join-Path $dir ("$safe-($i).txt"); $i++ }
  [System.IO.File]::WriteAllText($p, $Text, [System.Text.UTF8Encoding]::new($true))
  return $p
}

function Write-Log {
  param($Row)
  $exists = Test-Path $LogPath
  $Row | Export-Csv $LogPath -NoTypeInformation -Encoding utf8BOM -Append:$exists
}

function Unescape-Html {
  param([string]$s)
  $s = $s -replace '(?i)<br\s*/?>', "`r`n"
  $s = $s -replace '(?s)<[^>]+>', ''
  $s = $s -replace '&nbsp;', ' ' -replace '&lt;', '<' -replace '&gt;', '>' -replace '&quot;', '"' -replace '&#39;', "'" -replace '&amp;', '&'
  return $s
}

$ok = 0; $skip = 0
$seen = [System.Collections.Generic.HashSet[string]]::new()
if (Test-Path $LogPath) {
  foreach ($r in (Import-Csv $LogPath)) { if ($r.Url) { [void]$seen.Add($r.Url) } }
}

# ══════════════════════════════════ pixiv ══════════════════════════════════
if ($Source -eq 'pixiv') {
  function Expand-List([string[]]$v) {
    if (-not $v) { return @() }
    $r = @()
    foreach ($x in $v) { $r += ($x -split '[,，]') }
    return @($r | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  }
  $Tags     = Expand-List $Tags
  $Queries  = Expand-List $Queries
  $Targets  = Expand-List $Targets
  $HQueries = Expand-List $HQueries

  # 检索单元：tag=标签全匹配；word=多词模糊匹配（★ 推荐用 word，别带「同人」二字）
  $units = [System.Collections.Generic.List[object]]::new()
  foreach ($t in $Tags) { $units.Add([pscustomobject]@{ Word = $t; Mode = 'tag' }) }
  foreach ($q in $Queries) { $units.Add([pscustomobject]@{ Word = $q; Mode = 'word' }) }
  if ($Auto) {
    $qs = if ($HQueries) { $HQueries } else { @('调教', '中出', '淫', '凌辱', '催眠') }
    $ts = if ($Targets) { $Targets }
          elseif ($Group) {
            switch ($Group) {
              'tudou'    { $Cfg.targetsTudou }
              'sanshao'  { $Cfg.targetsSanshao }
              'chendong' { $Cfg.targetsChendong }
              'works'    { $Cfg.works }
            }
          }
          else { $Cfg.targets }
    foreach ($t in $ts) { foreach ($h in $qs) { $units.Add([pscustomobject]@{ Word = "$t $h"; Mode = 'word' }) } }
  }
  if ($units.Count -eq 0) {
    foreach ($t in $Cfg.pixiv.DefaultTags) { $units.Add([pscustomobject]@{ Word = $t; Mode = 'tag' }) }
  }

  $total = $units.Count * $Pages
  $done  = 0
  foreach ($u in $units) {
    $tag = $u.Word
    for ($p = 1; $p -le $Pages; $p++) {
      $done++
      Write-Host ("[{0}/{1}] {2}={3} page={4}" -f $done, $total, $u.Mode, $tag, $p) -ForegroundColor Cyan
      $enc = [uri]::EscapeDataString($tag)
      $sMode = if ($u.Mode -eq 'tag') { 's_tag_full' } else { 's_tag' }
      $searchUrl = ($Cfg.pixiv.SearchUrl -f $enc, $p) -replace 'order=[^&]+', "order=$Order" -replace 's_mode=[^&]+', "s_mode=$sMode"
      $j = Get-Json -Url $searchUrl -Referer $Cfg.pixiv.Referer
      if (-not $j -or $j.error) { Write-Warning "搜索失败：$tag p$p"; continue }
      $items = $j.body.novel.data
      if (-not $items) { continue }
      $nTake = if ($u.Mode -eq 'word' -and $PerQuery -gt 0) { [Math]::Min($PerQuery, $items.Count) } else { $items.Count }
      $items = @($items)[0..($nTake - 1)]
      if ($nTake -eq 0) { continue }

      foreach ($it in $items) {
        $id = $it.id
        $title = $it.title
        $novelUrl = "https://www.pixiv.net/novel/show.php?id=$id"
        if ($seen.Contains($novelUrl)) { $skip++; continue }
        $tagStr = if ($it.tags) { ($it.tags -join ',') } else { '' }
        Start-Sleep -Milliseconds $SleepMs

        $d = Get-Json -Url ($Cfg.pixiv.NovelUrl -f $id) -Referer $Cfg.pixiv.Referer
        if (-not $d -or $d.error) { $skip++; continue }
        $text = Unescape-Html $d.body.content
        $chars = ($text -replace '\s', '').Length
        if ($chars -lt $MinChars) { $skip++; continue }

        $h = Get-HScore -Text $text -Tags $tagStr
        if ($h -lt $HMin) {
          Write-Host ("  跳过(非H) {0} H={1}" -f $title, $h) -ForegroundColor DarkGray
          $skip++; continue
        }

        $head = if ($text.Length -gt 2000) { $text.Substring(0, 2000) } else { $text }
        $ip = Resolve-Ip -Name ($title + ' ' + $tagStr) -Head $head
        $body = "【$title】`r`n`r`n" + $text.Trim() + "`r`n"
        $file = Save-Raw -Ip $ip -Name ("pixiv-$id-$title") -Text $body
        Write-Host ("  OK {0,-40} {1,7}字 H={2}" -f $title, $chars, $h) -ForegroundColor Green
        Write-Log ([pscustomobject]@{
            Time = (Get-Date).ToString('s'); Source = 'pixiv'; Id = $id; Title = $title; Ip = $ip
            Tags = $tagStr; Chars = $chars; HScore = $h
            Url = $novelUrl; File = $file
          })
        [void]$seen.Add($novelUrl)
        $ok++
        Start-Sleep -Milliseconds $SleepMs
      }
    }
  }
}

# ══════════════════════════════════ qbtr ═══════════════════════════════════
if ($Source -eq 'qbtr') {
  if (-not $Ids) { Write-Warning 'qbtr 源需要 -Ids'; return }
  $Base = $Cfg.qbtr.BaseUrl
  foreach ($id in $Ids) {
    try {
      $h = @{ 'User-Agent' = $UA; 'Referer' = "$Base/tongren/" }
      $bh = (Invoke-WebRequest "$Base/tongren/$id.html" -UseBasicParsing -Headers $h -TimeoutSec 30).Content
      $tm = [regex]::Match($bh, '<title>([^<(]{1,80})')
      $title = if ($tm.Success) { $tm.Groups[1].Value.Trim() } else { "book$id" }
      $tp = (Invoke-WebRequest "$Base/txt/2-$id-0.html" -UseBasicParsing -Headers $h -TimeoutSec 30).Content
      $pm = [regex]::Match($tp, 'doaction\.php\?enews=DownSoft&classid=2&id=(\d+)&pathid=0&pass=([0-9a-f]+)')
      if (-not $pm.Success) { throw '无下载令牌' }
      $dl = "$Base/e/DownSys/doaction.php?enews=DownSoft&classid=2&id=$id&pathid=0&pass=$($pm.Groups[2].Value)&p=::::::"
      $resp = Invoke-WebRequest $dl -UseBasicParsing -Headers $h -TimeoutSec 90
      $bytes = $resp.RawContentStream.ToArray()
      if ($bytes.Length -lt 5000) { throw '内容过小' }
      $text = [System.Text.Encoding]::UTF8.GetString($bytes)
      $chars = ($text -replace '\s', '').Length
      $ip = Resolve-Ip -Name $title -Head $text.Substring(0, [Math]::Min(2000, $text.Length))
      $file = Save-Raw -Ip $ip -Name ("qbtr-$id-$title") -Text $text
      $hScore = Get-HScore -Text $text -Tags ''
      Write-Log ([pscustomobject]@{
          Time = (Get-Date).ToString('s'); Source = 'qbtr'; Id = $id; Title = $title; Ip = $ip
          Tags = ''; Chars = $chars; HScore = $hScore
          Url = "$Base/tongren/$id.html"; File = $file
        })
      Write-Host ("OK  {0,-32} {1,8}字 H={2}" -f $title, $chars, $hScore) -ForegroundColor Green
      $ok++
      Start-Sleep -Milliseconds $SleepMs
    } catch {
      Write-Warning ("FAIL {0} — {1}" -f $id, $_.Exception.Message)
      $skip++
    }
  }
}

Write-Host ""
Write-Host ("搜集完成：成功 {0}，跳过 {1}。原始文件在 {2}" -f $ok, $skip, $RawRoot) -ForegroundColor Cyan
Write-Host "下一步：pwsh -File _采集\入库.ps1" -ForegroundColor DarkCyan
