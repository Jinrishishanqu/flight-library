# 流水线.ps1 —— 采集自动化流水线（爬文字 / 截图+OCR 两条路线 + 后处理全链）
# 用法：
#   pwsh -File 采集工具\流水线.ps1 -Mode crawl -Queries "斗破苍穹,斗罗大陆" -MaxBooks 6
#   pwsh -File 采集工具\流水线.ps1 -Mode shot -Urls "https://..." -Title "某书"
#   pwsh -File 采集工具\流水线.ps1 -Mode ocr  -Images "归档\临时\shot\某书" -Title "某书"
#   pwsh -File 采集工具\流水线.ps1 -Mode post                 # 只跑后处理链
#   pwsh -File 采集工具\流水线.ps1 -Mode full -Queries "斗破苍穹" -Urls "https://..." -Title "某书"
param(
  [ValidateSet('crawl', 'shot', 'ocr', 'post', 'full')][string]$Mode = 'post',
  [string[]]$Queries,
  [string[]]$Urls,
  [string]$FromFile,
  [string]$Images,
  [string]$Title,
  [int]$MaxBooks = 6,
  [int]$MaxChapters = 250,
  [int]$MinChars = 800,
  [int]$DelayMs = 250,
  [int]$ShotWidth = 1200,
  [int]$ShotHeight = 2400,
  [switch]$FullPage,
  [int]$OcrScale = 2.0,
  [string]$Proxy,
  [switch]$SkipPost,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tools = $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$logFile = Join-Path $root '采集工具\记录\流水线.csv'
$logDir = Split-Path $logFile -Parent
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

function Write-Log([string]$step, [string]$note, [double]$sec, [string]$status = 'ok') {
  $line = '{0},{1},{2},{3},{4},{5}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Mode, $step, $status, ([Math]::Round($sec, 1)), ($note -replace '[,\r\n]', ' ')
  if (-not (Test-Path -LiteralPath $logFile)) { [System.IO.File]::WriteAllText($logFile, "Time,Mode,Step,Status,Sec,Note`r`n", (New-Object System.Text.UTF8Encoding($true))) }
  [System.IO.File]::AppendAllText($logFile, $line + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-Step([string]$name, [scriptblock]$body) {
  Write-Host ''
  Write-Host ("=== " + $name + " ===") -ForegroundColor Magenta
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    & $body
    $sw.Stop()
    Write-Log $name '' $sw.Elapsed.TotalSeconds 'ok'
    Write-Host ("    [ok] " + [Math]::Round($sw.Elapsed.TotalSeconds, 1) + "s") -ForegroundColor Green
  } catch {
    $sw.Stop()
    Write-Log $name $_.Exception.Message $sw.Elapsed.TotalSeconds 'fail'
    Write-Host ("    [fail] " + $_.Exception.Message) -ForegroundColor Red
    throw
  }
}

$pwsh = (Get-Process -Id $PID).Path
$ps5 = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $ps5)) { $ps5 = 'powershell.exe' }
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) { $py = $null }

Write-Host ("流水线模式：" + $Mode + "   根目录：" + $root) -ForegroundColor Cyan

# ---------------- 路线 A：爬文字 ----------------
if ($Mode -in @('crawl', 'full')) {
  if (-not $Queries -or $Queries.Count -eq 0) { throw 'crawl 模式需要 -Queries' }
  Invoke-Step '版主爬（第一版主）' {
    $a = @('-NoProfile', '-File', (Join-Path $tools '版主爬.ps1'),
      '-Queries', ($Queries -join ','), '-MaxBooks', $MaxBooks, '-MaxChapters', $MaxChapters,
      '-MinChars', $MinChars, '-DelayMs', $DelayMs)
    if ($Proxy) { $a += @('-Proxy', $Proxy) }
    if ($DryRun) { $a += '-DryRun' }
    & $pwsh @a
  }
}

# ---------------- 路线 B：截图 ----------------
$shotDir = $null
if ($Mode -in @('shot', 'full')) {
  if (-not $Urls -and -not $FromFile) { throw 'shot 模式需要 -Urls 或 -FromFile（也可以用 -Images 指向已有截图目录）' }
  $slug = if ($Title) { ($Title -replace '[\\/:*?"<>|]', '_') } else { 'shots-' + (Get-Date -Format 'MMdd-HHmmss') }
  $shotDir = Join-Path $root ('归档\临时\shot\' + $slug)
  Invoke-Step '截图（Edge 无头）' {
    $a = @('-NoProfile', '-File', (Join-Path $tools '截图.ps1'),
      '-OutDir', $shotDir, '-Width', $ShotWidth, '-Height', $ShotHeight)
    if ($Urls) { $a += @('-Urls', ($Urls -join '|')) }
    if ($FromFile) { $a += @('-FromFile', $FromFile) }
    if ($FullPage) { $a += '-FullPage' }
    if ($Proxy) { $a += @('-Proxy', $Proxy) }
    & $pwsh @a
  }
}

# ---------------- 路线 B2：OCR ----------------
if ($Mode -in @('ocr', 'full')) {
  $srcDir = if ($Images) { $Images } else { $shotDir }
  if (-not $srcDir) { throw 'ocr 模式需要 -Images 或先用 shot 模式截图' }
  if (-not [System.IO.Path]::IsPathRooted($srcDir)) { $srcDir = Join-Path $root $srcDir }
  if (-not (Test-Path -LiteralPath $srcDir)) { throw "找不到截图目录：$srcDir" }
  $outName = if ($Title) { ($Title -replace '[\\/:*?"<>|]', '_') } else { Split-Path $srcDir -Leaf }
  $outTxt = Join-Path $root ('采集工具\raw\' + $outName + '.txt')
  Invoke-Step 'OCR 转文字（RapidOCR / onnxruntime）' {
    if ($py) {
      $a = @((Join-Path $tools 'py\ocr.py'), '--dir', $srcDir, '--out', $outTxt)
      & $py @a
    } else {
      $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $tools 'OCR.ps1'),
        '-Path', $srcDir, '-Merge', '-OutFile', $outTxt, '-Scale', $OcrScale)
      & $ps5 @a
    }
    if (-not (Test-Path -LiteralPath $outTxt)) { throw 'OCR 未产出文本' }
    $chars = (Get-Content -LiteralPath $outTxt -Raw -Encoding UTF8).Length
    Write-Host ("    OCR 产出：" + $outTxt + "  " + $chars + " 字") -ForegroundColor DarkGray
    if ($chars -lt 200) { Write-Host '    警告：识别字数偏少，检查截图是否空白/文字是否在 canvas 里' -ForegroundColor Yellow }
  }
}

# ---------------- 后处理链 ----------------
if (-not $SkipPost -and $Mode -in @('post', 'crawl', 'ocr', 'full')) {
  $since = (Get-Date).AddMinutes(-30).ToString('yyyy-MM-dd HH:mm')

  Invoke-Step '入库（判重 + 归类）' {
    & $pwsh -NoProfile -File (Join-Path $tools '入库.ps1')
  }
  Invoke-Step '校对（增量，不重跑已处理）' {
    & $pwsh -NoProfile -File (Join-Path $tools '校对.ps1')
  }
  Invoke-Step '清理再生（防止全量重跑回滚合并成果）' {
    & $pwsh -NoProfile -File (Join-Path $tools '清理再生.ps1') -Since $since -Apply
  }
  Invoke-Step '重建清单' {
    & $pwsh -NoProfile -File (Join-Path $tools '重建清单.ps1')
  }
  Invoke-Step '校验' {
    & $pwsh -NoProfile -File (Join-Path $tools '校验.ps1')
  }
  Invoke-Step '索引' {
    & $pwsh -NoProfile -File (Join-Path $tools '索引.ps1')
  }
  Invoke-Step '生成站点数据' {
    & $pwsh -NoProfile -File (Join-Path $tools '生成站点.ps1')
  }
}

Write-Host ''
Write-Host ("流水线结束。日志：" + $logFile) -ForegroundColor Green
