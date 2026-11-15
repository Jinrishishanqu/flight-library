# 截图.ps1 —— 用 Edge 无头模式把网页截成 PNG（给「爬不到文字」的站用）
# 用法：
#   pwsh -File 采集工具\截图.ps1 -Url "https://..." -OutFile "归档\临时\shot\a.png"
#   pwsh -File 采集工具\截图.ps1 -Url "https://..." -OutFile "...\a.png" -FullPage
#   pwsh -File 采集工具\截图.ps1 -Urls @("u1","u2") -OutDir "归档\临时\shot"
#   pwsh -File 采集工具\截图.ps1 -FromFile urls.txt -OutDir "归档\临时\shot"
param(
  [string]$Url,
  [string[]]$Urls,
  [string]$FromFile,
  [string]$OutFile,
  [string]$OutDir,
  [int]$Width = 1200,
  [int]$Height = 2400,
  [switch]$FullPage,            # 用超长视口抓整页（高度按 -FullPageHeight）
  [int]$FullPageHeight = 30000,
  [int]$WaitMs = 1500,          # 页面渲染等待（--virtual-time-budget）
  [string]$Proxy,
  [string]$EdgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$profileDir = Join-Path $root '归档\临时\edgeprof'
if (-not (Test-Path -LiteralPath $profileDir)) { New-Item -ItemType Directory -Path $profileDir -Force | Out-Null }

if (-not (Test-Path -LiteralPath $EdgePath)) { throw "找不到 Edge：$EdgePath" }

# ---- 组装任务列表 ----
$jobs = @()
if ($Url) { $jobs += [pscustomobject]@{ Url = $Url; Out = $OutFile } }
if ($Urls) { foreach ($u in $Urls) { $jobs += [pscustomobject]@{ Url = $u; Out = $null } } }
if ($FromFile) {
  if (-not (Test-Path -LiteralPath $FromFile)) { throw "找不到 URL 列表：$FromFile" }
  Get-Content -LiteralPath $FromFile -Encoding UTF8 | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') } |
    ForEach-Object { $jobs += [pscustomobject]@{ Url = $_.Trim(); Out = $null } }
}
if ($jobs.Count -eq 0) { throw '没有目标 URL：用 -Url / -Urls / -FromFile' }

if ($OutDir -and -not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

function Get-SafeFileName([string]$u, [int]$i) {
  $name = $u -replace '^https?://', '' -replace '[\\/:*?"<>|&=?]', '_'
  if ($name.Length -gt 80) { $name = $name.Substring(0, 80) }
  return ('{0:d3}-{1}.png' -f $i, $name)
}

$h = if ($FullPage) { $FullPageHeight } else { $Height }
$i = 0
$made = @()
foreach ($j in $jobs) {
  $i++
  $target = if ($j.Out) {
    $j.Out
  } elseif ($OutDir) {
    Join-Path $OutDir (Get-SafeFileName $j.Url $i)
  } else {
    Join-Path $root ('归档\临时\shot\' + (Get-SafeFileName $j.Url $i))
  }
  # Edge 的相对路径不按当前工作目录解析，必须先转绝对路径，否则截图落到别处
  if (-not [System.IO.Path]::IsPathRooted($target)) { $target = Join-Path $root $target }
  $target = [System.IO.Path]::GetFullPath($target)
  $dir = Split-Path $target -Parent
  if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }

  $argv = @(
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--disable-sync', '--mute-audio',
    ("--user-data-dir=" + $profileDir),
    ("--window-size=" + $Width + ',' + $h),
    ("--virtual-time-budget=" + $WaitMs),
    ("--screenshot=" + $target)
  )
  if ($Proxy) { $argv += ("--proxy-server=" + $Proxy) }
  $argv += $j.Url

  if (-not $Quiet) { Write-Host ("[$i/$($jobs.Count)] " + $j.Url) -ForegroundColor Cyan }
  & $EdgePath @argv 2>$null | Out-Null
  Start-Sleep -Milliseconds 300
  if (Test-Path -LiteralPath $target) {
    $kb = [Math]::Round((Get-Item -LiteralPath $target).Length / 1KB, 1)
    $made += [pscustomobject]@{ Url = $j.Url; File = $target; KB = $kb }
    if (-not $Quiet) { Write-Host ("    → " + $target + "  " + $kb + " KB") -ForegroundColor DarkGray }
  } else {
    if (-not $Quiet) { Write-Host ("    × 截图失败") -ForegroundColor Yellow }
  }
}

if (-not $Quiet) { Write-Host ("完成 " + $made.Count + "/" + $jobs.Count + " 张") -ForegroundColor Green }
$made | ForEach-Object { $_.File }
