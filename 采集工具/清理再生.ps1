#requires -Version 7.0
<#
  清理再生：校对.ps1 是从「原文」全量幂等重生成的，每次重跑都会把
  ① 已被 查重.ps1 移入 归档\重复_根级 的重复件
  ② 已被 合并.ps1 合并掉的单章源文件
  重新生成到「校对后文章」里。本脚本把这类「再生件」识别出来移走，
  只保留真正新增的文件。

  用法：
    pwsh -File 采集工具\清理再生.ps1            # 预览
    pwsh -File 采集工具\清理再生.ps1 -Apply     # 真移走（移到 归档\临时\再生件\）
#>
[CmdletBinding()]
param(
  [datetime]$Since = (Get-Date '2026-11-15 11:20'),
  [switch]$Apply
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Root = Split-Path -Parent $PSScriptRoot
$OutRoot  = Join-Path $Root '校对后文章'
$DupRoot  = Join-Path $Root '归档\重复_根级'
$FamPath  = Join-Path $PSScriptRoot 'families.psd1'
$Quarantine = Join-Path $Root '归档\临时\再生件'
$Fam = Import-PowerShellDataFile $FamPath

function Get-Bare { param([string]$n) return ($n -replace '[《》]', '') }

# 重复版本名单（BaseName）
$dupNames = [System.Collections.Generic.HashSet[string]]::new()
if (Test-Path $DupRoot) {
  foreach ($f in Get-ChildItem $DupRoot -Recurse -File -Filter *.txt) { [void]$dupNames.Add($f.BaseName) }
}

# 已合并源的名单：归档\备份_整合前 里放的就是被合并吃掉的源单章，BaseName 与校对重生成的完全一致
$mergedNames = [System.Collections.Generic.HashSet[string]]::new()
$BackupRoot = Join-Path $Root '归档\备份_校对后'
if (Test-Path $BackupRoot) {
  foreach ($f in Get-ChildItem $BackupRoot -Recurse -File -Filter *.txt) { [void]$mergedNames.Add($f.BaseName) }
}
Write-Host ("已合并源名单：{0} 个；重复件名单：{1} 个" -f $mergedNames.Count, $dupNames.Count) -ForegroundColor DarkGray

# 新增文件（跳过 _校勘版 等下划线目录）
$new = @(Get-ChildItem $OutRoot -Recurse -File -Filter *.txt |
  Where-Object { $_.LastWriteTime -gt $Since -and $_.FullName -notmatch '\\_[^\\]+\\' })

$keep = [System.Collections.Generic.List[object]]::new()
$kill = [System.Collections.Generic.List[object]]::new()

# 已合并族判别
#  A) 章节名式：裸标题去掉「-章号-字数」尾巴后，必须与关键词完全相等（避免「开始」「处理」这类泛词误杀新书）
#  B) 书名式：裸标题里包含该子串即命中
$exactKeys = @(
  '开始','处理','提议','唐昊','教皇','独孤博','灵猫','试探','测谎','彻底曝光','雷霆背刺','主动自爆',
  '自生自灭式培养','再烤蓝银草','再胜炽火','招灾','罢赛','预选第一','晋级赛最终战','恋爱脑',
  '“无冕圣女”','邪火','武魂城','供奉殿','千道流亲自招生','星罗皇家战队','亲若母女','告一段落',
  '解除婚约','薰儿借钱','佣兵晴叶','少女苓儿','并蒂双花','义姐义弟','佣兵雪岚','薰儿魅力','身份暴露',
  '迦南学院，活体广告','灵液拍卖','药材到手','进阶斗者','药老问心','薰儿震怒',
  '莫崖干医仙','惨遭凌辱的小医仙','小医仙之拍卖会','莫崖得手','淫宗银风'
)
$likeKeys = @(
  '，萧熏','，彩鳞','，紫研','，学院',
  '幽焰青莲·','云韵纳兰篇-','斗破凌辱纳兰之三年约前传','斗破纳兰嫣然之霸气催眠凌辱',
  '斗破苍穹·美杜莎篇','苏萱的凌辱调教','域外邪族干洛神','璃丶潇篇','璃·潇篇',
  '遮天有爱番外篇','遮天番外','李卿婵战败成精盆','斗罗催眠！','从斗罗开始收取性奴的诸天之旅'
)

foreach ($f in $new) {
  $bare = Get-Bare $f.BaseName
  # 去掉尾部「-章号(-章号)-字数」
  $head = $bare -replace '-\d+(-\d+)?-.*$', ''
  $why = $null
  if ($dupNames.Contains($f.BaseName)) { $why = '重复件再生' }
  elseif ($mergedNames.Contains($f.BaseName)) { $why = '已合并源再生' }
  else {
    foreach ($k in $exactKeys) {
      if ($head -eq $k) { $why = "已合并族($k)"; break }
    }
    if (-not $why) {
      foreach ($k in $likeKeys) {
        if ($bare.Contains($k)) { $why = "已合并族($k)"; break }
      }
    }
  }
  if ($why) { $kill.Add([pscustomobject]@{ File = $f; Why = $why }) } else { $keep.Add($f) }
}

Write-Host ("新增 {0} 份：保留 {1}，再生 {2}" -f $new.Count, $keep.Count, $kill.Count) -ForegroundColor Cyan
Write-Host "`n--- 再生件（将被移走）---" -ForegroundColor Yellow
$kill | Group-Object Why | ForEach-Object {
  Write-Host ("[{0}] {1} 份" -f $_.Name, $_.Count) -ForegroundColor DarkGray
  $_.Group | ForEach-Object { Write-Host ("   " + $_.File.Name) -ForegroundColor DarkGray }
}
Write-Host "`n--- 保留件 ---" -ForegroundColor Green
$keep | ForEach-Object { Write-Host ("   " + $_.Name) }

if ($Apply -and $kill.Count -gt 0) {
  $logPath = Join-Path $PSScriptRoot '记录\再生清理.csv'
  foreach ($k in $kill) {
    $ip = Split-Path $k.File.DirectoryName -Leaf
    $dstDir = Join-Path $Quarantine $ip
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    Move-Item -LiteralPath $k.File.FullName -Destination (Join-Path $dstDir $k.File.Name) -Force
    [pscustomobject]@{
      Time = (Get-Date).ToString('s'); Ip = $ip; File = $k.File.Name; Why = $k.Why
    } | Export-Csv $logPath -NoTypeInformation -Encoding utf8BOM -Append:((Test-Path $logPath))
  }
  Write-Host ("`n已移走 {0} 份 → {1}" -f $kill.Count, $Quarantine) -ForegroundColor Green
  Write-Host "记录：采集工具\记录\再生清理.csv" -ForegroundColor DarkCyan
} elseif (-not $Apply) {
  Write-Host "`n（预览模式，未动文件；加 -Apply 执行）" -ForegroundColor Yellow
}
