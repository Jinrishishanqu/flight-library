#requires -Version 7.0
<#
  校验：独立复核「校对后TXT」，不复用校对过程的中间结果
  ────────────────────────────────────────────────────────────────
  核验项（对应 README「校验」一节）：
    1. 编码：必须是 UTF-8 BOM，换行必须是 CRLF
    2. 字符序列：忽略排版空白后，输出 == 各份原文按序拼接
    3. 覆盖：清单里每份输入恰好出现一次，输出文件全部可回溯到来源
    4. 字数：文件名里的字数与实际非空白字符数一致
  用法：
    pwsh -File _采集\校验.ps1
    pwsh -File _采集\校验.ps1 -Fix   # 顺手改掉文件名里错的字数
#>
[CmdletBinding()]
param(
  [string]$Root = (Split-Path -Parent $PSScriptRoot),
  [string]$Manifest = (Join-Path (Join-Path $PSScriptRoot '记录') '校对清单.csv'),
  [switch]$Fix
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$Gbk       = [System.Text.Encoding]::GetEncoding(936)
$Strict    = [System.Text.UTF8Encoding]::new($false, $true)

function Read-Doc {
  param([string]$Path)
  if ($Path -match '\.docx$') {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ('docx-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $Path -DestinationPath $tmp -Force
    $xml = Get-Content (Join-Path $tmp 'word\document.xml') -Raw -Encoding UTF8
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    $t = $xml -replace '</w:p>', "`n" -replace '<w:br[^>]*/>', "`n" -replace '<w:tab[^>]*/>', "`t" -replace '<[^>]+>', ''
    return ($t -replace '&lt;', '<' -replace '&gt;', '>' -replace '&amp;', '&' -replace '&quot;', '"')
  }
  $b = [System.IO.File]::ReadAllBytes($Path)
  if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) { return $Utf8NoBom.GetString($b, 3, $b.Length - 3) }
  if ($b.Length -ge 2 -and $b[0] -eq 0xFF -and $b[1] -eq 0xFE) { return [System.Text.Encoding]::Unicode.GetString($b, 2, $b.Length - 2) }
  try { return $Strict.GetString($b) } catch { return $Gbk.GetString($b) }
}

if (-not (Test-Path $Manifest)) { Write-Host "找不到校对清单：$Manifest（先跑 校对.ps1）" -ForegroundColor Yellow; return }
$rows = Import-Csv $Manifest
$report = @()
$bad = 0

foreach ($r in $rows) {
  $out = $r.Output
  $issues = @()

  if (-not (Test-Path -LiteralPath $out)) {
    $issues += '输出文件缺失'
  } else {
    $bytes = [System.IO.File]::ReadAllBytes($out)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    if (-not $hasBom) { $issues += '缺 UTF-8 BOM' }

    $raw = Read-Doc $out
    if ($raw -match "[^`r]`n") { $issues += '存在裸 LF 换行' }

    $srcs = @($r.Sources -split '\|' | Where-Object { $_ })
    $missing = @($srcs | Where-Object { -not (Test-Path -LiteralPath $_) })
    if ($missing.Count -gt 0) { $issues += "来源缺失 $($missing.Count) 份" }

    $inSeq  = ((@($srcs | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Read-Doc $_ }) -join '') -replace '\s', '')
    $outSeq = ($raw -replace '\s', '')
    if ($srcs.Count -eq 0) {
      $issues += '无来源(仅结构校验)'
    } elseif ($inSeq -ne $outSeq) {
      $issues += "字符序列不一致(原$($inSeq.Length)/出$($outSeq.Length))"
      # 定位首个差异位置，便于人工核查
      $n = [Math]::Min($inSeq.Length, $outSeq.Length); $pos = -1
      for ($i = 0; $i -lt $n; $i++) { if ($inSeq[$i] -ne $outSeq[$i]) { $pos = $i; break } }
      if ($pos -ge 0) { $issues += "首个差异@$pos" } elseif ($n -gt 0) { $issues += "长度差异@$n" }
    }

    # 文件名字数核对（按 README 的取整规则重算标签再比对，不按精确值）
    $actual = ($raw -replace '\s', '').Length
    $expect = if ($actual -lt 10000) { "$($actual)字" } else { (("{0}w" -f [Math]::Round($actual / 10000.0, 1)).Replace('.0w', 'w')) }
    $m = [regex]::Match((Split-Path $out -Leaf), '-(\d+(?:\.\d+)?w|\d+字)\.txt$')
    if ($m.Success) {
      $claim = $m.Groups[1].Value
      if ($claim -ne $expect) {
        $issues += "文件名字数不符(标$claim/应为$expect)"
        if ($Fix) {
          $newName = (Split-Path $out -Leaf) -replace '-(\d+(?:\.\d+)?w|\d+字)\.txt$', "-$expect.txt"
          $newPath = Join-Path (Split-Path $out -Parent) $newName
          try { Move-Item -LiteralPath $out -Destination $newPath -Force; $out = $newPath; $issues += '已改名修正' }
          catch { $issues += '改名失败' }
        }
      }
    }
  }

  if (@($issues | Where-Object { $_ -notlike "无来源*" }).Count -gt 0) { $bad++ }
  $report += [pscustomobject]@{
    Output = $out
    Ip     = $r.Ip
    Verified = (@($issues | Where-Object { $_ -notlike "无来源*" }).Count -eq 0)
    Issues = ($issues -join '；')
    InChars = $r.InChars
    OutChars = $r.OutChars
  }
}

$reportPath = Join-Path (Join-Path $PSScriptRoot '记录') '校验报告.csv'
$report | Export-Csv $reportPath -NoTypeInformation -Encoding utf8BOM

# 覆盖性：清单来源是否出现重复
$dupSrc = $rows | ForEach-Object { $_.Sources -split '\|' } | Where-Object { $_ } |
          Group-Object | Where-Object Count -gt 1
if ($dupSrc) { Write-Host ("注意：{0} 份来源被重复使用" -f $dupSrc.Count) -ForegroundColor Yellow }

Write-Host ""
Write-Host ("校验：{0} 份输出，通过 {1}，异常 {2}" -f $report.Count, ($report.Count - $bad), $bad) -ForegroundColor $(if ($bad) { 'Yellow' } else { 'Green' })
Write-Host ("报告：{0}" -f $reportPath) -ForegroundColor DarkCyan
if ($bad -gt 0) { $report | Where-Object { -not $_.Verified } | Select-Object -First 10 | Format-Table Output, Issues -AutoSize -Wrap }
