# OCR.ps1 —— 截图转文字（Windows.Media.Ocr / WinRT）
# 必须在 Windows PowerShell 5.1 下运行：powershell -File OCR.ps1 ...
# 用法：
#   powershell -File 采集工具\OCR.ps1 -Path 图.png -OutFile 输出.txt
#   powershell -File 采集工具\OCR.ps1 -Path 截图目录 -Merge -OutFile 输出.txt
#   powershell -File 采集工具\OCR.ps1 -Path 截图目录 -OutDir ..\归档\临时\ocr
param(
  [Parameter(Mandatory = $true)][string]$Path,
  [string]$Lang = 'zh-Hans-CN',
  [string]$OutFile,
  [string]$OutDir,
  [int]$SliceHeight = 1800,      # 长图按此高度切片（0 = 不切）
  [int]$SliceOverlap = 100,      # 切片重叠像素，避免切断行
  [double]$Scale = 2.0,          # 放大倍数，小字提升识别率
  [switch]$Merge,
  [switch]$JoinLines,            # 默认保留换行（交给 校对.ps1 接行）；加此开关则整段拼接
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Drawing

$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

# ---- WinRT 异步等待 ----
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
  })[0]

function Await($op, $type) {
  $t = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
  $t.Wait(-1) | Out-Null
  $t.Result
}

# ---- OCR 引擎 ----
$engine = $null
try {
  $language = New-Object Windows.Globalization.Language $Lang
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
} catch { $engine = $null }
if ($null -eq $engine) {
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if ($null -eq $engine) { throw "没有可用的 OCR 语言包（尝试过 $Lang）。请在系统设置里安装「中文(简体)」OCR 组件。" }
if (-not $Quiet) {
  Write-Host ("OCR 语言：" + $engine.RecognizerLanguage.LanguageTag + "  最大边长：" + [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) -ForegroundColor Cyan
}

# ---- 图片预处理：放大 + 切片，写到临时目录 ----
$tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('ocr-slice-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null

function Get-Slices([string]$imagePath) {
  $out = @()
  $img = [System.Drawing.Image]::FromFile($imagePath)
  try {
    $w = $img.Width; $h = $img.Height
    $sw = [int]($w * $Scale); $sh = [int]($h * $Scale)
    $step = if ($SliceHeight -gt 0) { [int]($SliceHeight * $Scale) } else { $sh }
    $ov = [int]($SliceOverlap * $Scale)
    $y = 0; $idx = 0
    while ($y -lt $sh) {
      $ch = [Math]::Min($step, $sh - $y)
      $bmp = New-Object System.Drawing.Bitmap($sw, $ch)
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
      $srcRect = New-Object System.Drawing.Rectangle(0, [int]($y / $Scale), $w, [Math]::Min([int]($ch / $Scale) + 2, $h - [int]($y / $Scale)))
      $dstRect = New-Object System.Drawing.Rectangle(0, 0, $sw, $ch)
      $g.DrawImage($img, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
      $g.Dispose()
      $p = Join-Path $tmpRoot ("s{0:d3}.png" -f $idx)
      $bmp.Save($p, [System.Drawing.Imaging.ImageFormat]::Png)
      $bmp.Dispose()
      $out += $p
      $idx++
      if ($y + $ch -ge $sh) { break }
      $y += ($step - $ov)
    }
  } finally { $img.Dispose() }
  return $out
}

function Get-OcrLines([string]$imagePath) {
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($imagePath)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  try {
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @()
    foreach ($l in $result.Lines) { $lines += $l.Text }
    return , $lines
  } finally { $stream.Dispose() }
}

# WinRT 中文 OCR 会把每个字/词当独立 token 用空格隔开，这里把汉字之间、汉字与标点之间的空格收回
function Normalize-Cn([string]$text) {
  if (-not $text) { return $text }
  $cn = '\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff'
  $punct = '\u3000-\u303f\uff00-\uffef'
  $t = $text
  # 汉字 + 空格 + 汉字 → 去掉空格（重复两次处理连续多空格）
  for ($i = 0; $i -lt 2; $i++) {
    $t = [regex]::Replace($t, "(?<=[$cn])\s+(?=[$cn])", '')
    $t = [regex]::Replace($t, "(?<=[$cn])\s+(?=[$punct])", '')
    $t = [regex]::Replace($t, "(?<=[$punct])\s*(?=[$cn])", '')
  }
  # 全角标点两侧留白过宽的处理
  $t = [regex]::Replace($t, '[\u3040-\u30ff]{2,}', { param($m) $m.Value })
  $t = $t -replace '\s{2,}', ' '
  return $t.Trim()
}

# ---- 收集待处理图片 ----
$images = @()
if (Test-Path -LiteralPath $Path -PathType Container) {
  $images = @(Get-ChildItem -LiteralPath $Path -File |
    Where-Object { $_.Extension -match '^\.(png|jpg|jpeg|bmp|gif|tif|tiff)$' } |
    Sort-Object Name | ForEach-Object { $_.FullName })
} elseif (Test-Path -LiteralPath $Path) {
  $images = @((Resolve-Path -LiteralPath $Path).Path)
} else {
  throw "找不到路径：$Path"
}
if ($images.Count -eq 0) { throw "没有可用图片（webp 需先转 png）。目录：$Path" }

if (-not $Quiet) { Write-Host ("待识别 " + $images.Count + " 张图") -ForegroundColor Cyan }

$allBlocks = @()
$n = 0
foreach ($img in $images) {
  $n++
  $slices = Get-Slices $img
  $pageLines = @()
  foreach ($s in $slices) {
    $lines = Get-OcrLines $s
    foreach ($line in $lines) {
      $t = Normalize-Cn $line
      if (-not $t) { continue }
      # 切片重叠去重：与已有最后几行完全相同的跳过
      $dup = $false
      for ($k = [Math]::Max(0, $pageLines.Count - 3); $k -lt $pageLines.Count; $k++) {
        if ($pageLines[$k] -eq $t) { $dup = $true; break }
      }
      if (-not $dup) { $pageLines += $t }
    }
  }
  Remove-Item -LiteralPath $slices -Force -ErrorAction SilentlyContinue
  $text = if ($JoinLines) { $pageLines -join '' } else { $pageLines -join "`r`n" }
  $allBlocks += [pscustomobject]@{ File = $img; Lines = $pageLines.Count; Text = $text }
  if (-not $Quiet) {
    Write-Host ("  [{0}/{1}] {2} → {3} 行 / {4} 字" -f $n, $images.Count, (Split-Path $img -Leaf), $pageLines.Count, $text.Length) -ForegroundColor DarkGray
  }
}
Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue

$utf8 = New-Object System.Text.UTF8Encoding($true)

if ($OutFile) {
  $body = if ($Merge -or $images.Count -eq 1) {
    if ($JoinLines) { ($allBlocks | ForEach-Object { $_.Text }) -join '' }
    else { ($allBlocks | ForEach-Object { $_.Text }) -join '' }
  } else {
    ($allBlocks | ForEach-Object { ($_.Text) -replace "`r?`n", "`r`n" }) -join "`r`n`r`n"
  }
  $dir = Split-Path $OutFile -Parent
  if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  [System.IO.File]::WriteAllText($OutFile, ($body -replace "`r?`n", "`r`n"), $utf8)
  if (-not $Quiet) { Write-Host ("已写出：" + $OutFile + "（" + $body.Length + " 字）") -ForegroundColor Green }
}

if ($OutDir) {
  if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
  foreach ($b in $allBlocks) {
    $base = [System.IO.Path]::GetFileNameWithoutExtension($b.File)
    $p = Join-Path $OutDir ($base + '.txt')
    [System.IO.File]::WriteAllText($p, ($b.Text -replace "`r?`n", "`r`n"), $utf8)
    if (-not $Quiet) { Write-Host ("  写出 " + $p) -ForegroundColor DarkGray }
  }
}

if (-not $OutFile -and -not $OutDir) {
  # 控制台输出
  foreach ($b in $allBlocks) {
    Write-Host ("=== " + (Split-Path $b.File -Leaf) + " ===") -ForegroundColor Cyan
    Write-Host $b.Text
  }
}

# 汇总
if (-not $Quiet) {
  $total = ($allBlocks | Measure-Object -Property Lines -Sum).Sum
  Write-Host ("完成：" + $images.Count + " 张图 / " + $total + " 行") -ForegroundColor Green
}
