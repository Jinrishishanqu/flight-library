param(
  [Parameter(Mandatory=$true)][string]$File,
  [string]$Anchor = 'inn-singular__post__body__content',
  [int]$Max = 6000
)
# 从抓下来的 HTML 里剥出正文纯文本（去 script/style，定位锚点容器后去标签）
$h = Get-Content -LiteralPath $File -Raw -Encoding UTF8
$h = [regex]::Replace($h, '(?s)<script.*?</script>', '')
$h = [regex]::Replace($h, '(?s)<style.*?</style>', '')
$h = [regex]::Replace($h, '(?s)<noscript.*?</noscript>', '')

$idx = $h.IndexOf($Anchor)
if ($idx -lt 0) { $idx = 0 } else { $idx = $h.IndexOf('>', $idx) + 1 }
$seg = $h.Substring($idx, [Math]::Min($Max * 12, $h.Length - $idx))

# 只取到评论区分界为止
foreach ($stop in @('inn-comment__list', 'inn-singular__post__footer', '相关推荐', 'inn-related')) {
  $p = $seg.IndexOf($stop)
  if ($p -gt 200) { $seg = $seg.Substring(0, $p) }
}

$seg = [regex]::Replace($seg, '(?i)<br\s*/?>', "`n")
$seg = [regex]::Replace($seg, '(?i)</(p|div|li|h\d|tr)>', "`n")
$seg = [regex]::Replace($seg, '(?s)<[^>]+>', '')
$seg = [System.Net.WebUtility]::HtmlDecode($seg)
$lines = $seg -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
$out = ($lines -join "`n")
if ($out.Length -gt $Max) { $out = $out.Substring(0, $Max) }
$out
