# SSB Group — ssbgroup.uz domenini bir marta ulash (Cloudflare Tunnel).
# deploy\ULASH.bat orqali ishga tushiriladi.
# cloudflared o'z xabarlarini stderr'ga yozadi; Windows PowerShell 5 da 'Stop' bunda xato deb to'xtab qoladi.
param([switch]$Auto)
$ErrorActionPreference = 'Continue'
$Domain  = 'ssbgroup.uz'
$Hosts   = @('ssbgroup.uz', 'www.ssbgroup.uz')
$Tunnel  = 'ssb-group'
$Root    = Split-Path -Parent $PSScriptRoot
$Deploy  = Join-Path $Root 'deploy'
$Bin     = Join-Path $Deploy 'bin'
$Cf      = Join-Path $Bin 'cloudflared.exe'
$CfHome  = Join-Path $env:USERPROFILE '.cloudflared'
$Config  = Join-Path $Deploy 'cloudflared.yml'
$Port    = 8080

function Step($n, $text) { Write-Host ""; Write-Host " [$n/5] $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "       OK  $text" -ForegroundColor Green }
function Warn($text) { Write-Host "       !   $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host ""; Write-Host " XATO: $text" -ForegroundColor Red; Write-Host ""; if ($Auto) { try { Stop-Transcript | Out-Null } catch {}; exit 1 }; Read-Host " Chiqish uchun Enter bosing"; exit 1 }
if ($Auto) {
    $tl = Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) 'deploy') 'logs'
    New-Item -ItemType Directory -Force -Path $tl | Out-Null
    try { Start-Transcript -Path (Join-Path $tl 'ulash-run.log') -Force | Out-Null } catch {}
}

Clear-Host
Write-Host ""
Write-Host "  ================================================" -ForegroundColor White
Write-Host "     SSB Group  ->  https://$Domain  ulash" -ForegroundColor White
Write-Host "  ================================================" -ForegroundColor White

# ---------------------------------------------------------------- 1
Step 1 "Cloudflare dasturi (cloudflared)"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
if (-not (Test-Path $Cf)) {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $Cf -ErrorAction Stop
    } catch { Fail "cloudflared.exe yuklanmadi. Internetni tekshiring." }
}
Ok ((& $Cf --version) -join ' ')

# ---------------------------------------------------------------- 2
Step 2 "Domen Cloudflare hisobidami?"
$ns = @()
try { $ns = (Resolve-DnsName -Type NS $Domain -ErrorAction Stop | Where-Object { $_.NameHost }).NameHost } catch {}
if ($ns -match 'ns\.cloudflare\.com') {
    Ok "Nameserverlar Cloudflare'da: $($ns -join ', ')"
} else {
    Warn "Domen hali Cloudflare'ga o'tmagan (hozirgi NS: $(if ($ns) { $ns -join ', ' } else { 'topilmadi' }))."
    Write-Host ""
    Write-Host "       Brauzer ochiladi. U yerda:" -ForegroundColor White
    Write-Host "         1) Ro'yxatdan o'ting yoki kiring (bepul)."
    Write-Host "         2) 'Add a domain' -> $Domain -> Free rejani tanlang."
    Write-Host "         3) Cloudflare bergan 2 ta nameserverni domen olgan saytingiz panelida"
    Write-Host "            (DNS serverlar / NS bo'limi) eski serverlar o'rniga yozing."
    Write-Host "       Nameserverlar 1-24 soatda kuchga kiradi, lekin ulashni hozir davom ettirsa bo'ladi."
    Start-Process "https://dash.cloudflare.com/?to=/:account/add-site"
    Write-Host ""
    if (-not $Auto) { Read-Host "       Domenni Cloudflare'ga qo'shgach, shu yerga qaytib Enter bosing" }
}

# ---------------------------------------------------------------- 3
Step 3 "Cloudflare hisobiga ruxsat"
$Cert = Join-Path $CfHome 'cert.pem'
function Find-Cert {
    if (Test-Path $Cert) { return $true }
    $alt = @(
        (Join-Path $env:USERPROFILE '.cloudflare-warp\cert.pem'),
        (Join-Path $env:USERPROFILE 'cloudflare-warp\cert.pem'),
        (Join-Path $Bin 'cert.pem'),
        (Join-Path $Root 'cert.pem')
    )
    # Brauzer sertifikatni "Yuklanmalar" (Downloads) papkasiga tushirgan bo'lishi mumkin
    $dl = @((Join-Path $env:USERPROFILE 'Downloads'))
    try { $dl += (New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path } catch {}
    foreach ($d in ($dl | Select-Object -Unique)) {
        if (Test-Path $d) {
            $f = Get-ChildItem -Path $d -Filter 'cert*.pem' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($f) { $alt += $f.FullName }
        }
    }
    foreach ($p in $alt) {
        if (Test-Path $p) {
            New-Item -ItemType Directory -Force -Path $CfHome | Out-Null
            Copy-Item $p $Cert -Force
            return $true
        }
    }
    return $false
}
$try = 0
while (-not (Find-Cert)) {
    $try++
    if ($try -gt 3) { Fail "Ruxsat 3 marta olinmadi. Ekranni rasmga olib yuboring." }
    Write-Host ""
    Write-Host "       Brauzerda Cloudflare sahifasi ochiladi:" -ForegroundColor White
    Write-Host "         1) Domen qo'shilgan Cloudflare hisobingizga kiring."
    Write-Host "         2) Ro'yxatdan '$Domain' ni bosing."
    Write-Host "         3) 'Authorize' tugmasini bosing va 'Success' yozuvini kuting."
    Write-Host "       Brauzer o'zi ochilmasa, pastda chiqqan https://dash.cloudflare.com/argotunnel?... havolani"
    Write-Host "       nusxalab brauzerga qo'ying. Shu oyna 'Success' chiqquncha OCHIQ tursin." -ForegroundColor Yellow
    Write-Host ""
    & $Cf tunnel login
    if (Find-Cert) { break }
    Write-Host ""
    Write-Host "       Agar brauzer 'Upload your Tunnel certificate' deb cert.pem faylini yuklab olgan bo'lsa," -ForegroundColor Yellow
    Write-Host "       yuklab olish tugashini kuting va shu yerda Enter bosing - fayl o'zi topiladi." -ForegroundColor Yellow
    if ($Auto) { Start-Sleep -Seconds 20 } else { Read-Host "       Enter" }
    if (Find-Cert) { break }
    Warn "Ruxsat olinmadi. Odatdagi sabablar:"
    Write-Host "         - 'Authorize' bosilmadi yoki sahifa yopib yuborildi;"
    Write-Host "         - brauzerda boshqa Cloudflare hisobi ochiq (ro'yxatda $Domain yo'q);"
    Write-Host "         - kutish vaqti tugadi (bir necha daqiqa)."
    if ($Auto) { $a = '' } else { $a = Read-Host "       Qayta urinamizmi? (Ha = Enter / Yo'q = n)" }
    if ($a -eq 'n') { Fail "Ruxsat berilmadi. ULASH.bat ni qayta bosing." }
}
Ok "Ruxsat bor"

# ---------------------------------------------------------------- 4
Step 4 "Tunnel '$Tunnel'"
function Get-Tunnel {
    $raw = (& $Cf tunnel list --output json 2>$null | Out-String).Trim()
    if (-not $raw -or $raw -eq 'null') { return $null }
    try { return (ConvertFrom-Json $raw) | Where-Object { $_.name -eq $Tunnel } | Select-Object -First 1 } catch { return $null }
}
$t = Get-Tunnel
if ($t -and -not (Test-Path (Join-Path $CfHome "$($t.id).json"))) {
    Warn "Tunnel bor, lekin kaliti bu kompyuterda yo'q - qayta yaratiladi."
    & $Cf tunnel cleanup $Tunnel 2>$null | Out-Null
    & $Cf tunnel delete -f $Tunnel | Out-Null
    $t = $null
}
if (-not $t) {
    & $Cf tunnel create $Tunnel | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Tunnel yaratilmadi." }
    $t = Get-Tunnel
}
if (-not $t) { Fail "Tunnel topilmadi." }
$cred = Join-Path $CfHome "$($t.id).json"
$yml = @"
tunnel: $($t.id)
credentials-file: $cred
no-autoupdate: true
ingress:
  - hostname: $($Hosts[0])
    service: http://localhost:$Port
  - hostname: $($Hosts[1])
    service: http://localhost:$Port
  - service: http_status:404
"@
[IO.File]::WriteAllText($Config, $yml, (New-Object Text.UTF8Encoding $false))
Ok "Tunnel: $($t.id)"

# ---------------------------------------------------------------- 5
Step 5 "Domen yozuvlari (DNS)"
$LogDir = Join-Path $Deploy 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'ulash.log'
"=== $(Get-Date) ===" | Out-File -FilePath $Log -Append -Encoding utf8

function Route-Dns($certPath) {
    foreach ($h in $Hosts) {
        $out = & $Cf tunnel --origincert $certPath route dns --overwrite-dns $t.id $h 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
        "[$certPath] $h -> exit $code" | Out-File -FilePath $Log -Append -Encoding utf8
        $out | Out-File -FilePath $Log -Append -Encoding utf8
        if ($code -ne 0) { Write-Host ("       " + (($out | Select-Object -Last 2) -join ' ')) -ForegroundColor DarkGray; return $false }
        Ok "$h -> tunnel"
    }
    return $true
}

$routed = Route-Dns $Cert
if (-not $routed) {
    # Brauzer yuklab olgan yangiroq sertifikatlar bilan urinib ko'ramiz
    $cands = @()
    foreach ($d in @((Join-Path $env:USERPROFILE 'Downloads'))) {
        if (Test-Path $d) { $cands += Get-ChildItem -Path $d -Filter 'cert*.pem' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending }
    }
    foreach ($c in $cands) {
        Warn "Boshqa ruxsat fayli bilan urinilmoqda: $($c.Name)"
        if (Route-Dns $c.FullName) { Copy-Item $c.FullName $Cert -Force; $routed = $true; break }
    }
}
if (-not $routed) {
    Fail "DNS yozuvi qo'shilmadi. deploy\logs\ulash.log faylini yuboring (unda maxfiy kalit yo'q)."
}

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Green
Write-Host "   ULANDI!  https://$Domain" -ForegroundColor Green
Write-Host "   Endi saytni yoqish: deploy\start.bat" -ForegroundColor Green
Write-Host "  ================================================" -ForegroundColor Green
if (-not ($ns -match 'ns\.cloudflare\.com')) {
    Warn "Nameserverlar kuchga kirmaguncha (1-24 soat) sayt domen orqali ochilmasligi mumkin."
}
Write-Host ""
if ($Auto) { $a = ''; try { Stop-Transcript | Out-Null } catch {} } else { $a = Read-Host " Saytni hozir yoqaymi? (Ha = Enter / Yo'q = n)" }
if ($a -ne 'n') { Start-Process -FilePath (Join-Path $Deploy 'start.bat') -WorkingDirectory $Root }
