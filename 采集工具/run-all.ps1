#requires -Version 7.0
<#
  一条命令跑完整链路：搜集 → 入库 → 校对 → 校验
  ────────────────────────────────────────────────────────────
  pwsh -File _采集\run-all.ps1 -Tags 斗破苍穹,斗罗大陆 -Pages 2
  pwsh -File _采集\run-all.ps1 -Source qbtr -Ids 10209
  pwsh -File _采集\run-all.ps1 -SkipCollect        # 只跑后三步
#>
[CmdletBinding()]
param(
  [ValidateSet('pixiv', 'qbtr')][string]$Source = 'pixiv',
  [string[]]$Tags,
  [int]$Pages = 1,
  [int[]]$Ids,
  [int]$HMin = 12,
  [switch]$SkipCollect,
  [switch]$SkipVerify
)

$ErrorActionPreference = 'Continue'
$H = $PSCmdlet.MyInvocation.BoundParameters

function Step($n, $t) { Write-Host "`n═══ [$n] $t ═══" -ForegroundColor Magenta }

if (-not $SkipCollect) {
  Step 1 '搜集'
  $a = @{ Source = $Source; HMin = $HMin }
  if ($Tags) { $a.Tags = $Tags }
  if ($Pages) { $a.Pages = $Pages }
  if ($Ids) { $a.Ids = $Ids }
  & (Join-Path $PSScriptRoot '搜集.ps1') @a
} else { Step 1 '搜集（跳过）' }

Step 2 '入库'
& (Join-Path $PSScriptRoot '入库.ps1')

Step 3 '校对'
& (Join-Path $PSScriptRoot '校对.ps1')

if (-not $SkipVerify) {
  Step 4 '校验'
  & (Join-Path $PSScriptRoot '校验.ps1')
}

Write-Host "`n链路完成。" -ForegroundColor Green
