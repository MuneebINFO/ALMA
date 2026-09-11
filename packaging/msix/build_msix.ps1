<#
.SYNOPSIS
    Construit Alma.msix : compile Alma.exe, genere les images du Store,
    remplit le manifeste avec votre identite Partner Center, et empaquette
    le tout en .msix.

.PARAMETER Sideload
    En plus du build, cree un certificat de test local et installe le
    paquet sur CETTE machine (Add-AppxPackage), pour verifier qu'il
    s'installe et se lance avant de le soumettre au Store.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\msix\build_msix.ps1
    powershell -ExecutionPolicy Bypass -File packaging\msix\build_msix.ps1 -Sideload

.NOTES
    Prealables : voir packaging/msix/README.md
      - Python + les dependances du projet (pip install -r requirements-build.txt)
      - identity.local.json rempli (copie de identity.example.json)
      - le Windows SDK (makeappx.exe, signtool.exe) -- installe avec
        Visual Studio, ou seul : winget install Microsoft.WindowsSDK
#>

param(
    [switch]$Sideload
)

$ErrorActionPreference = "Stop"
$Racine = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$MsixDir = $PSScriptRoot
$Layout = Join-Path $MsixDir "PackageLayout"

# Le "python" du PATH peut etre n'importe quel interpreteur global installe
# sur la machine, avec n'importe quoi dedans -- constate a l usage : un
# Alma.exe de 427 Mo, parce que PyInstaller a suivi le "python" global et
# embarque pandas/scipy/scikit-learn/Jupyter, installes ici pour tout autre
# chose. Le .venv du projet, lui, ne contient que ce qu ALMA declare dans
# requirements*.txt : c est TOUJOURS lui qu il faut utiliser pour construire.
$VenvPython = Join-Path $Racine ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "ATTENTION : $VenvPython introuvable -- repli sur le python du PATH, qui peut contenir n'importe quoi d'autre installe sur cette machine et gonfler Alma.exe. Creez le venv du projet (python -m venv .venv) et installez requirements-build.txt dedans." -ForegroundColor Yellow
    $VenvPython = "python"
}

function Trouver-OutilSdk([string]$Nom) {
    <#
    Cherche un outil du Windows SDK (makeappx.exe, signtool.exe) : d'abord
    dans le PATH, sinon dans le dossier standard d'installation du SDK, en
    prenant la version la plus recente installee.
    #>
    $surLePath = Get-Command $Nom -ErrorAction SilentlyContinue
    if ($surLePath) { return $surLePath.Source }

    $baseSdk = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path $baseSdk) {
        $version = Get-ChildItem $baseSdk -Directory |
            Where-Object { $_.Name -match "^\d+\.\d+\.\d+\.\d+$" } |
            Sort-Object Name -Descending | Select-Object -First 1
        if ($version) {
            $candidat = Join-Path $version.FullName "x64\$Nom"
            if (Test-Path $candidat) { return $candidat }
        }
    }
    return $null
}

Write-Host "== 1/5 : compilation d'Alma.exe (via $VenvPython) ==" -ForegroundColor Cyan
Push-Location $Racine
try {
    & $VenvPython build_exe.py
    if ($LASTEXITCODE -ne 0) { throw "build_exe.py a echoue." }
}
finally { Pop-Location }

Write-Host "== 2/5 : images du Store ==" -ForegroundColor Cyan
& $VenvPython (Join-Path $MsixDir "make_store_assets.py")
if ($LASTEXITCODE -ne 0) { throw "make_store_assets.py a echoue." }

Write-Host "== 3/5 : manifeste ==" -ForegroundColor Cyan
& $VenvPython (Join-Path $MsixDir "render_manifest.py")
if ($LASTEXITCODE -ne 0) { throw "render_manifest.py a echoue (voir le message ci-dessus)." }

Write-Host "== 4/5 : mise en page du paquet ==" -ForegroundColor Cyan
$ExeSource = Join-Path $Racine "dist\Alma.exe"
if (-not (Test-Path $ExeSource)) { throw "Introuvable : $ExeSource" }
Copy-Item $ExeSource (Join-Path $Layout "Alma.exe") -Force

Write-Host "== 5/5 : empaquetage (.msix) ==" -ForegroundColor Cyan
$MakeAppx = Trouver-OutilSdk "makeappx.exe"
if (-not $MakeAppx) {
    throw "makeappx.exe introuvable. Installez le Windows SDK : " +
          "winget install Microsoft.WindowsSDK -- puis relancez ce script."
}
$MsixSortie = Join-Path $MsixDir "Alma.msix"
if (Test-Path $MsixSortie) { Remove-Item $MsixSortie -Force }
& $MakeAppx pack /d $Layout /p $MsixSortie
if ($LASTEXITCODE -ne 0) { throw "makeappx a echoue." }

Write-Host "`nPaquet cree : $MsixSortie" -ForegroundColor Green

if ($Sideload) {
    Write-Host "`n== Test local (Sideload) ==" -ForegroundColor Cyan
    $SignTool = Trouver-OutilSdk "signtool.exe"
    if (-not $SignTool) {
        throw "signtool.exe introuvable (meme installation que makeappx.exe)."
    }

    # L'identite du certificat DOIT correspondre exactement au champ
    # "Publisher" du manifeste (identity.local.json -> "publisher").
    $Identite = Get-Content (Join-Path $MsixDir "identity.local.json") | ConvertFrom-Json
    $SujetCert = $Identite.publisher
    $CheminPfx = Join-Path $MsixDir "test-signing.pfx"

    $Cert = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object { $_.Subject -eq $SujetCert } | Select-Object -First 1
    if (-not $Cert) {
        Write-Host "Creation d'un certificat de test (usage LOCAL uniquement, jamais pour le Store)..."
        $Cert = New-SelfSignedCertificate -Type Custom -Subject $SujetCert `
            -KeyUsage DigitalSignature -FriendlyName "Alma - test local" `
            -CertStoreLocation "Cert:\CurrentUser\My" `
            -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
    }
    $MotDePasse = ConvertTo-SecureString -String "alma-test" -Force -AsPlainText
    Export-PfxCertificate -Cert $Cert -FilePath $CheminPfx -Password $MotDePasse | Out-Null

    & $SignTool sign /fd SHA256 /f $CheminPfx /p "alma-test" $MsixSortie
    if ($LASTEXITCODE -ne 0) { throw "signtool a echoue." }

    Write-Host "Pour que Windows fasse confiance a ce paquet de TEST, faites confiance " `
        "une fois au certificat (Windows le proposera a l'installation), puis :" -ForegroundColor Yellow
    Write-Host "  Add-AppxPackage -Path `"$MsixSortie`"" -ForegroundColor Yellow
}
else {
    Write-Host "Ajoutez -Sideload pour tester l'installation sur cette machine avant" `
        "de soumettre le paquet au Partner Center." -ForegroundColor DarkGray
}
