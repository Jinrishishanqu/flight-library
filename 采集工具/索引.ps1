# 索引.ps1 —— 重建 文档\书目索引.csv（扫描 原文\**\*.txt）
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$src  = Join-Path $root '原文'
$doc  = Join-Path $root '文档'
if (-not (Test-Path -LiteralPath $doc)) { New-Item -ItemType Directory -Path $doc -Force | Out-Null }
$out  = Join-Path $doc '书目索引.csv'

$rows = foreach ($f in Get-ChildItem -LiteralPath $src -Recurse -File -Filter *.txt) {
    $bytes = [IO.File]::ReadAllBytes($f.FullName)
    $enc = 'UTF8'
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) { $enc = 'UTF16' }
    elseif ($bytes -match [byte]0) { $enc = 'GBK?' }
    $txt = [IO.File]::ReadAllText($f.FullName, [Text.Encoding]::UTF8)
    [pscustomobject]@{
        Group = $f.Directory.Name
        File  = [IO.Path]::GetFileNameWithoutExtension($f.Name)
        Chars = $txt.Length
        KB    = [math]::Round($f.Length / 1KB, 1)
        Enc   = $enc
    }
}

$rows | Sort-Object Group, File | Export-Csv -LiteralPath $out -NoTypeInformation -Encoding UTF8
"索引：$($rows.Count) 条 → $out"
