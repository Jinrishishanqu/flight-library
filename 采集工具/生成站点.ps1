# 生成站点数据：扫 原文 / 校对后文章 / 记录，输出 站点\data.js
# 用法：pwsh -NoProfile -File 采集工具\生成站点.ps1
param(
  [string]$Root = '',
  [string]$SiteDir = ''
)
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
if (-not $SiteDir) { $SiteDir = Join-Path $Root '站点' }
if (-not (Test-Path $SiteDir)) { New-Item -ItemType Directory -Path $SiteDir -Force | Out-Null }

$out = [ordered]@{
  generated = (Get-Date).ToString('yyyy-MM-dd HH:mm')
  yuanwen   = 0
  yuanwenMB = 0
  jiaodui   = 0
  jiaoduiMB = 0
  chars     = 0
  verified  = 0
  verifiedBad = 0
  indexRows = 0
  merged    = 0
  dedup     = 0
  regen     = 0
  groups    = @()
  records   = @()
  batches   = @()
}

# ---- 原文 ----
$ywDir = Join-Path $Root '原文'
if (Test-Path $ywDir) {
  $yw = @(Get-ChildItem -LiteralPath $ywDir -Recurse -File -Filter *.txt)
  $out.yuanwen = $yw.Count
  $out.yuanwenMB = [Math]::Round((($yw | Measure-Object Length -Sum).Sum / 1MB), 1)
}

# ---- 校对后文章（排除 _开头的备份目录）----
$jdDir = Join-Path $Root '校对后文章'
$groups = @()
if (Test-Path $jdDir) {
  $all = @(Get-ChildItem -LiteralPath $jdDir -Recurse -File -Filter *.txt | Where-Object { $_.FullName -notmatch '\\_[^\\]+\\' })
  $out.jiaodui = $all.Count
  $out.jiaoduiMB = [Math]::Round((($all | Measure-Object Length -Sum).Sum / 1MB), 1)

  $groups = @($all | Group-Object { Split-Path (Split-Path $_.FullName -Parent) -Leaf } | ForEach-Object {
      $gChars = 0
      foreach ($f in $_.Group) { $gChars += $f.Length }
      [pscustomobject]@{ name = $_.Name; files = $_.Count; bytes = $gChars }
    } | Sort-Object files -Descending)
  $out.groups = $groups
}

# ---- 记录目录 ----
$logDir = Join-Path $Root '采集工具\记录'
function Get-Count($name) {
  $p = Join-Path $logDir $name
  if (-not (Test-Path $p)) { return 0 }
  $n = @(Import-Csv -LiteralPath $p -Encoding UTF8).Count
  return $n
}
$out.merged = Get-Count '合并记录.csv'
$out.dedup  = Get-Count '重复候选.csv'
$out.regen  = Get-Count '再生清理.csv'
$out.indexRows = Get-Count '校对清单.csv'

# 校验
$vp = Join-Path $logDir '校验v2.csv'
if (Test-Path $vp) {
  $rep = @(Import-Csv -LiteralPath $vp -Encoding UTF8)
  $out.verified = @($rep | Where-Object { $_.issues -eq 'OK' }).Count
  $out.verifiedBad = $rep.Count - $out.verified
}

# 总字数
$cp = Join-Path $logDir '校对清单.csv'
if (Test-Path $cp) {
  $sum = (Import-Csv -LiteralPath $cp -Encoding UTF8 | ForEach-Object { [int64]$_.OutChars } | Measure-Object -Sum).Sum
  $out.chars = [int64]$sum
}

# 记录文件清单
if (Test-Path $logDir) {
  $out.records = @(Get-ChildItem -LiteralPath $logDir -File | Sort-Object Name | ForEach-Object {
      $lines = 0
      if ($_.Extension -eq '.csv') { $lines = [Math]::Max(0, (@(Get-Content -LiteralPath $_.FullName -Encoding UTF8).Count - 1)) }
      elseif ($_.Extension -eq '.txt') { $lines = @(Get-Content -LiteralPath $_.FullName -Encoding UTF8).Count }
      [pscustomobject]@{ name = $_.Name; size = $_.Length; rows = $lines; time = $_.LastWriteTime.ToString('MM-dd HH:mm') }
    })
}

$json = $out | ConvertTo-Json -Depth 6 -Compress
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $SiteDir 'data.js'), ("window.DATA = " + $json + ";"), $utf8)

Write-Host ("站点数据已更新：原文 {0} 篇 / 校对 {1} 篇 / {2} 万字 / 校验通过 {3}" -f `
  $out.yuanwen, $out.jiaodui, [Math]::Round($out.chars / 10000), $out.verified) -ForegroundColor Green
Write-Host ("输出：{0}" -f (Join-Path $SiteDir 'data.js'))
