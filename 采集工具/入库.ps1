#requires -Version 7.0
<#
  入库：把 _采集\raw 下的原始文件收进「原文库」，只做三件事——判重、归类、记账。
  ★ 不修改一个字符（校对是下一步 校对.ps1 的事），只按 IP 落目录并写溯源信息。

  用法：
    pwsh -File _采集\入库.ps1 -DryRun
    pwsh -File _采集\入库.ps1
    pwsh -File _采集\入库.ps1 -KeepRaw    # 入库后保留 raw 原件（默认可删）
#>
[CmdletBinding()]
param(
  [string]$RawRoot  = (Join-Path $PSScriptRoot 'raw'),
  [string]$StageRoot = '',
  [switch]$DryRun,
  [switch]$KeepRaw
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Cfg = Import-PowerShellDataFile (Join-Path $PSScriptRoot 'sources.psd1')
$Root = Split-Path -Parent $PSScriptRoot
if (-not $StageRoot) { $StageRoot = Join-Path $Root '原文' }
$LogDir = Join-Path $PSScriptRoot '记录'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$ManifestPath = Join-Path $LogDir '入库清单.csv'

$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$Gbk       = [System.Text.Encoding]::GetEncoding(936)
$Strict    = [System.Text.UTF8Encoding]::new($false, $true)

function Read-Text {
  param([string]$Path)
  $b = [System.IO.File]::ReadAllBytes($Path)
  if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
    return $Utf8NoBom.GetString($b, 3, $b.Length - 3)
  }
  try { return $Strict.GetString($b) } catch { return $Gbk.GetString($b) }
}

function Get-TitleKey {
  param([string]$Name)
  $k = $Name -replace '（[^）]*）|\([^)]*\)|【[^】]*】|「[^」]*」|\[[^\]]*\]', ''
  $k = $k -replace '^pixiv-\d+-|^qbtr-\d+-', ''
  $k = $k -replace '第[一二三四五六七八九十百\d]+[章节篇回]', ''
  $k = $k -replace '[\s\-_~·、。，,.!！?？:：;；"''“”‘’]', ''
  $k = $k -replace '(全本|合集|完结|精校版?|番外篇?|同人|h文|txt)', ''
  return $k.ToLowerInvariant()
}

function Get-Fp {
  param([string]$Text)
  $t = $Text -replace '\s', ''
  if ($t.Length -lt 40) { return $t }
  return $t.Substring(0, [Math]::Min(200, $t.Length))
}

function Resolve-Ip {
  param([string]$Name, [string]$Head)
  # 计分：文件名命中权重 3，正文前 2000 字命中权重 1；取最高分（并列时按规则表顺序）
  $best = '待归类'; $bestScore = 0
  foreach ($k in $Cfg.ipRules.Keys) {
    $pat = $Cfg.ipRules[$k]
    $s = 0
    $s += 3 * ([regex]::Matches($Name, $pat)).Count
    if ($Head) { $s += [regex]::Matches($Head, $pat).Count }
    if ($s -gt $bestScore) { $bestScore = $s; $best = $k }
  }
  return $best
}

# ── 已入库指纹（原文库 + 老库各 IP 目录）────────────────────────────────────
$hashSet = [System.Collections.Generic.HashSet[string]]::new()
$keySet  = [System.Collections.Generic.HashSet[string]]::new()
$fpSet   = [System.Collections.Generic.HashSet[string]]::new()

$scanDirs = @()
if (Test-Path $StageRoot) { $scanDirs += Get-ChildItem $StageRoot -Directory }
$scanDirs += Get-ChildItem $Root -Directory | Where-Object {
  $_.Name -notin @('采集工具', '原文', '校对后文章') -and $_.Name -notlike '.*'
}
foreach ($d in $scanDirs) {
  foreach ($f in Get-ChildItem $d.FullName -File -Filter *.txt -ErrorAction SilentlyContinue) {
    [void]$hashSet.Add((Get-FileHash -LiteralPath $f.FullName -Algorithm MD5).Hash)
    [void]$keySet.Add((Get-TitleKey $f.BaseName))
    $t = Read-Text $f.FullName
    [void]$fpSet.Add((Get-Fp $t))
  }
}
Write-Host ("已入库基线：{0} 个文件" -f $hashSet.Count) -ForegroundColor DarkGray

if (-not (Test-Path $RawRoot)) { New-Item -ItemType Directory -Path $RawRoot -Force | Out-Null }
$files = @(Get-ChildItem $RawRoot -Recurse -File -Filter *.txt)
if ($files.Count -eq 0) { Write-Host "raw 为空：$RawRoot" -ForegroundColor Yellow; return }

$ok = 0; $dup = 0; $short = 0
foreach ($f in $files) {
  $text = Read-Text $f.FullName
  $chars = ($text -replace '\s', '').Length
  if ($chars -lt 300) { Write-Warning "过短跳过：$($f.Name)"; $short++; continue }

  $md5 = (Get-FileHash -LiteralPath $f.FullName -Algorithm MD5).Hash
  $key = Get-TitleKey $f.BaseName
  $fp  = Get-Fp $text
  $why = if ($hashSet.Contains($md5)) { 'MD5重复' }
         elseif ($keySet.Contains($key)) { '标题重复' }
         elseif ($fpSet.Contains($fp)) { '正文重复' }

  # 已带 IP 目录的沿用（搜集阶段已归类）
  $ip = if ($f.DirectoryName -ne $RawRoot -and $f.Directory.Name -ne 'raw') { $f.Directory.Name } else { '待归类' }
  if (-not $why -and ($ip -eq '待归类')) {
    $ip = Resolve-Ip -Name $f.BaseName -Head $text.Substring(0, [Math]::Min(2000, $text.Length))
  }

  if ($why) {
    # 标题重复但新件字数更多 → 视为「更完整的版本」，替换旧件（旧件备份到 归档\临时\旧版备份）
    if ($why -eq '标题重复' -and -not $DryRun) {
      $old = $null
      foreach ($c in (Get-ChildItem -LiteralPath $StageRoot -Recurse -Filter *.txt -File)) {
        if ((Get-TitleKey $c.BaseName) -eq $key) { $old = $c; break }
      }
      if ($old) {
        $oldChars = ((Read-Text $old.FullName) -replace '\s', '').Length
        if ($chars -gt $oldChars) {
          $bak = Join-Path $Root '归档\临时\旧版备份'
          New-Item -ItemType Directory -Force -Path $bak | Out-Null
          Copy-Item -LiteralPath $old.FullName -Destination (Join-Path $bak ($old.BaseName + '.txt')) -Force
          Copy-Item -LiteralPath $f.FullName -Destination $old.FullName -Force
          Write-Host ("REPL {0,-46} {1}字 > {2}字" -f $f.BaseName, $chars, $oldChars) -ForegroundColor Green
          $ok++
          continue
        }
      }
    }
    Write-Host ("DUP  {0,-46} {1}" -f $f.BaseName, $why) -ForegroundColor DarkGray
    $dup++
    continue
  }

  $destDir = Join-Path $StageRoot $ip
  $dest = Join-Path $destDir ($f.BaseName + '.txt')
  Write-Host ("IN   {0,-46} → {1}" -f $f.BaseName, $ip) -ForegroundColor Cyan
  if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Copy-Item -LiteralPath $f.FullName -Destination $dest -Force
    [void]$hashSet.Add($md5); [void]$keySet.Add($key); [void]$fpSet.Add($fp)
    [pscustomobject]@{
      Time = (Get-Date).ToString('s'); Ip = $ip; File = $dest
      Chars = $chars; Bytes = $f.Length; MD5 = $md5
    } | Export-Csv $ManifestPath -NoTypeInformation -Encoding utf8BOM -Append:((Test-Path $ManifestPath))
  }
  $ok++
}

if (-not $KeepRaw -and -not $DryRun) {
  Remove-Item (Join-Path $RawRoot '*') -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host ("入库 {0}，判重跳过 {1}，过短 {2}。" -f $ok, $dup, $short) -ForegroundColor Green
if ($DryRun) { Write-Host "（-DryRun：未写盘、未清 raw）" -ForegroundColor Yellow }
else { Write-Host "下一步：pwsh -File _采集\校对.ps1" -ForegroundColor DarkCyan }
