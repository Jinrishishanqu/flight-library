#requires -Version 7.0
<#
  入库规范化：转码 → 清洗 → 判重 → 重命名 → 归档到 IP 目录 → 更新书目索引
  用法：
    pwsh -File _采集\入库规范化.ps1 -DryRun          # 只出报告，不动文件
    pwsh -File _采集\入库规范化.ps1                  # 正式执行
    pwsh -File _采集\入库规范化.ps1 -Source D:\dl    # 指定其他源目录
    pwsh -File _采集\入库规范化.ps1 -Reindex         # 只重建书目索引，不处理新文件
#>
[CmdletBinding()]
param(
  [string]$Root   = (Split-Path -Parent $PSScriptRoot),
  [string]$Source = (Join-Path $PSScriptRoot 'raw'),
  [switch]$DryRun,
  [switch]$Reindex
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$Utf8Bom   = [System.Text.UTF8Encoding]::new($true)
$Gbk       = [System.Text.Encoding]::GetEncoding(936)
$Strict    = [System.Text.UTF8Encoding]::new($false, $true)

$LogPath   = Join-Path $PSScriptRoot '采集日志.csv'
$IndexPath = Join-Path $Root '文档\书目索引.csv'

# ── 归属判定：文件名或正文头部命中关键词即归入该 IP ────────────────────────────
$IpRules = [ordered]@{
  '斗破'         = '斗破|萧炎|薰儿|美杜莎|彩鳞|小医仙|云韵|纳兰嫣然|紫研|紫妍|青鳞|凤清儿|迦南学院|加玛帝国'
  '斗罗'         = '斗罗|绝世唐门|唐三|小舞|霍雨浩|王冬儿|唐舞桐|千仞雪|比比东|史莱克|邪魂师|帝天|雪帝'
  '大主宰'       = '大主宰|牧尘|洛璃|洛神族|九幽|应欢欢|温清璇|大千世界'
  '武动乾坤'     = '武动乾坤|林动|绫清竹|应笑笑|林琅天|青檀|大炎王朝|百朝大战'
  '凡人修仙传'   = '凡人修仙|韩立|南宫婉|紫灵|银月|乱星海|大晋|落云宗|元瑶'
  '神印王座'     = '神印王座|龙皓晨|圣采儿|月夜|阿加雷斯|猎魔团'
  '仙逆'         = '仙逆|王林|木冰眉|李慕婉|朱雀星|界外'
  '元尊'         = '元尊|周元|夭夭|苏幼薇|武瑶|圣州|大武王朝'
  '辰东'         = '遮天|完美世界|神墓|圣墟|不死不灭|叶凡|姬紫月|石昊|火灵儿|清漪|辰南|狠人|荒天帝'
  '完美世界'     = '完美世界|石昊|火灵儿|清漪|王曦|仙古'
  '圣墟'         = '圣墟|楚风|九道一|映晓晓'
  '诛仙'         = '诛仙|张小凡|碧瑶|陆雪琪|鬼厉'
  '择天记'       = '择天记|陈长生|徐有容|落落'
  '诡秘之主'     = '诡秘之主|克莱恩|奥黛丽|正义小姐|序列'
  '大奉打更人'   = '大奉打更人|许七安|慕南栀|临安'
  '剑来'         = '剑来|陈平安|宁姚|阮秀'
  '星辰变'       = '星辰变|秦羽|姜莉莉'
  '吞噬星空'     = '吞噬星空|罗峰|徐欣'
  '万相之王'     = '万相之王|李洛|姜青娥'
  '一念永恒'     = '一念永恒|白小纯|青莲'
}

function Get-TextWithEncoding {
  param([string]$Path)
  $b = [System.IO.File]::ReadAllBytes($Path)
  if ($b.Length -eq 0) { return [pscustomobject]@{ Text = ''; Enc = 'EMPTY' } }
  # UTF-8 BOM / UTF-16 BOM
  if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
    return [pscustomobject]@{ Text = $Utf8NoBom.GetString($b, 3, $b.Length - 3); Enc = 'UTF8-BOM' }
  }
  if ($b.Length -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) {
    return [pscustomobject]@{ Text = [System.Text.Encoding]::Unicode.GetString($b, 2, $b.Length - 2); Enc = 'UTF16-LE' }
  }
  try { return [pscustomobject]@{ Text = $Strict.GetString($b); Enc = 'UTF8' } }
  catch { return [pscustomobject]@{ Text = $Gbk.GetString($b); Enc = 'GBK' } }
}

function Convert-DocxToText {
  param([string]$Path)
  try {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("docx-" + [guid]::NewGuid())
    Expand-Archive -LiteralPath $Path -DestinationPath $tmp -Force
    $xml = Get-Content (Join-Path $tmp 'word\document.xml') -Raw -Encoding UTF8
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    $t = $xml -replace '</w:p>', "`n" -replace '<w:tab[^>]*/>', "`t" -replace '<[^>]+>', ''
    return ($t -replace '&lt;', '<' -replace '&gt;', '>' -replace '&amp;', '&')
  } catch { return $null }
}

function Clear-Text {
  param([string]$Text)
  $t = $Text
  $t = $t -replace "`0", ''
  $t = $t -replace '[\u200B-\u200F\u202A-\u202E\uFEFF]', ''          # 零宽/方向控制符
  $t = $t -replace '(?m)^\s*(?:本章未完[^\r\n]*|请收藏[^\r\n]*|手机用户请[^\r\n]*|www\.[^\s]+|https?://\S+)\s*$', ''
  $t = $t -replace '(?m)^\s*[-=*_—]{4,}\s*$', ''                     # 分隔线
  $t = $t -replace "(?m)^[ \t\u3000]+", ''                          # 行首缩进
  $t = $t -replace "[ \t\u3000]+\r?\n", "`n"                        # 行尾空白
  $t = $t -replace '(?:\r?\n){3,}', "`n`n"                          # 压缩空行
  return $t.Trim()
}

function Get-TitleKey {
  param([string]$Name)
  $k = $Name -replace '（[^）]*）|\([^)]*\)|【[^】]*】|「[^」]*」|\[[^\]]*\]', ''
  $k = $k -replace '^\d+\s*[-~、.]\s*', '' -replace '^第[一二三四五六七八九十百\d]+[章节篇]\s*', ''
  $k = $k -replace '[~\-\s_]?\d+\s*[-~]\s*\d+\s*$', ''
  $k = $k -replace '[\s\-_~·、。，,.!！?？:：;；"''“”‘’]', ''
  $k = $k -replace '(全本|合集|完结|精校版?|番外篇?|同人|txt|h文)', ''
  return $k.ToLowerInvariant()
}

function Get-SafeName {
  param([string]$Name)
  ($Name -replace '[\\/:*?"<>|\r\n]', '_').Trim()
}

function Get-CharCount {
  param([string]$Text)
  ($Text -replace '\s', '').Length
}

# ── 建索引：现有库（含 校对后TXT）────────────────────────────────────────────
function Build-Index {
  $rows = foreach ($f in Get-ChildItem $Root -Recurse -File -Filter *.txt |
                   Where-Object { $_.FullName -notlike "*$([IO.Path]::DirectorySeparatorChar)_采集*" }) {
    $r = Get-TextWithEncoding -Path $f.FullName
    [pscustomobject]@{
      Group = $f.DirectoryName.Substring($Root.Length).Trim('\')
      File  = $f.BaseName
      Chars = Get-CharCount $r.Text
      KB    = [math]::Round($f.Length / 1KB, 1)
      Enc   = $r.Enc
      MD5   = (Get-FileHash $f.FullName -Algorithm MD5).Hash
    }
  }
  $rows = @($rows)
  $target = $IndexPath
  $sorted = $rows | Sort-Object Group, File
  try {
    $sorted | Export-Csv $target -NoTypeInformation -Encoding utf8BOM
  } catch {
    # 索引被 Excel 占用时写副本，不中断采集
    $target = [IO.Path]::ChangeExtension($IndexPath, $null).TrimEnd('.') + '_' + (Get-Date -Format 'HHmmss') + '.csv'
    $sorted | Export-Csv $target -NoTypeInformation -Encoding utf8BOM
    Write-Warning ("原索引被占用，已写副本：$target")
  }
  Write-Host ("索引已更新：{0} 条 → {1}" -f $rows.Count, $target) -ForegroundColor Green
  return $rows
}

$existing = @(Build-Index)
if ($Reindex) { return }

# ── 扫描新文件 ───────────────────────────────────────────────────────────────
if (-not (Test-Path $Source)) { New-Item -ItemType Directory -Path $Source -Force | Out-Null }
$newFiles = @(Get-ChildItem $Source -Recurse -File -Include *.txt, *.docx, *.md | Where-Object { $_.Name -notlike '~$*' })
if ($newFiles.Count -eq 0) {
  Write-Host "没有待处理文件：$Source（把抓到的 txt/docx 丢进去再跑）" -ForegroundColor Yellow
  return
}

$hashSet  = [System.Collections.Generic.HashSet[string]]::new()
$keySet   = [System.Collections.Generic.HashSet[string]]::new()
$fpSet    = [System.Collections.Generic.HashSet[string]]::new()
foreach ($e in $existing) {
  [void]$hashSet.Add($e.MD5)
  [void]$keySet.Add((Get-TitleKey $e.File))
}
foreach ($e in $existing) {  # 正文指纹
  $p = Join-Path $Root ($e.Group + '\' + $e.File + '.txt')
  if (Test-Path -LiteralPath $p) {
    $t = (Clear-Text (Get-TextWithEncoding -Path $p).Text) -replace '\s', ''
    if ($t.Length -ge 40) { [void]$fpSet.Add($t.Substring(0, [Math]::Min(200, $t.Length))) }
  }
}

$log = [System.Collections.Generic.List[object]]::new()
$nOk = 0; $nSkip = 0

foreach ($f in $newFiles) {
  $raw = if ($f.Extension -eq '.docx') { Convert-DocxToText $f.FullName } else { (Get-TextWithEncoding -Path $f.FullName).Text }
  if ([string]::IsNullOrWhiteSpace($raw)) { Write-Warning "空/无法解析：$($f.Name)"; $nSkip++; continue }

  $text = Clear-Text $raw
  $chars = Get-CharCount $text
  if ($chars -lt 300) { Write-Warning "过短(<300字)跳过：$($f.Name)"; $nSkip++; continue }

  $md5 = (Get-FileHash $f.FullName -Algorithm MD5).Hash
  $key = Get-TitleKey $f.BaseName
  $fp  = ($text -replace '\s', '')
  $fp  = $fp.Substring(0, [Math]::Min(200, $fp.Length))

  $dupReason = if ($hashSet.Contains($md5)) { '完全重复(MD5)' }
               elseif ($keySet.Contains($key)) { '标题重复' }
               elseif ($fpSet.Contains($fp)) { '正文重复(前200字)' }

  # 归属判定：文件名优先，其次正文前 3000 字
  $ip = $null
  foreach ($k in $IpRules.Keys) {
    if ($f.BaseName -match $IpRules[$k]) { $ip = $k; break }
  }
  if (-not $ip) {
    $head = $text.Substring(0, [Math]::Min(3000, $text.Length))
    foreach ($k in $IpRules.Keys) { if ($head -match $IpRules[$k]) { $ip = $k; break } }
  }
  if (-not $ip) { $ip = '待归类' }

  $kind = if ($f.BaseName -match '(篇-\d|第[一二三四五六七八九十\d]+[章篇]|\d+~\d+)') { '分篇' } else { '全篇' }
  $newName = "《$(Get-SafeName $f.BaseName)》-$kind-$($chars)字.txt"
  $destDir = Join-Path $Root $ip
  $dest = Join-Path $destDir $newName
  $i = 1
  while (Test-Path -LiteralPath $dest) { $dest = Join-Path $destDir ("《$(Get-SafeName $f.BaseName)》-$kind-$($chars)字-($i).txt"); $i++ }

  $status = if ($dupReason) { "跳过：$dupReason" }
            else { if ($DryRun) { "待入库→$ip" } else { "已入库→$ip" } }

  Write-Host ("{0,-24} {1,7}字  {2}" -f $f.BaseName, $chars, $status) -ForegroundColor $(if ($dupReason) { 'DarkGray' } else { 'Cyan' })

  if (-not $dupReason) {
    if (-not $DryRun) {
      New-Item -ItemType Directory -Path $destDir -Force | Out-Null
      [System.IO.File]::WriteAllText($dest, $text + "`n", $Utf8NoBom)
      [void]$hashSet.Add($md5); [void]$keySet.Add($key); [void]$fpSet.Add($fp)
      $nOk++
    }
  } else { $nSkip++ }

  $log.Add([pscustomobject]@{
    Time = (Get-Date).ToString('s'); Src = $f.Name; Ip = $ip; Chars = $chars
    Enc = $f.Extension; Dest = if ($dupReason) { '' } else { $dest }; Status = $status
  })
}

if (-not $DryRun -and $log.Count -gt 0) {
  $header = -not (Test-Path $LogPath)
  $log | Export-Csv $LogPath -NoTypeInformation -Encoding utf8BOM -Append:$(-not $header)
  Build-Index | Out-Null
}

Write-Host ""
Write-Host ("完成：入库 {0}，跳过 {1}，共扫描 {2}" -f $nOk, $nSkip, $newFiles.Count) -ForegroundColor Green
if ($DryRun) { Write-Host "当前是 -DryRun，未改动任何文件。" -ForegroundColor Yellow }
