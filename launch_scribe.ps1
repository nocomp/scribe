# Définition des encodages 
$OutputEncoding = [console]::InputEncoding = [console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$env:PYTHONUTF8 = 1
$env:PYTHONIOENCODING = "utf-8"   

# Définir le titre de la fenêtre
$Host.UI.RawUI.WindowTitle = "SCRIBE - Supervision + Pilotage d'instances"

#Set-ExecutionPolicy RemoteSigned -Scope CurrentUser   
Set-ExecutionPolicy Unrestricted -Scope CurrentUser   

# Se placer dans le répertoire du script
Set-Location -Path (Split-Path $MyInvocation.MyCommand.Path) 

Write-Host ""
Write-Host "  SCRIBE - Lancement avec environnement Python"
Write-Host ""
Write-Host ""
Start-Sleep -Seconds 2

# Définition des chemins : 
$parentPath = Split-Path -Path $PSScriptRoot -Parent -Resolve
$source_config_etb = Join-Path $parentPath "SCRIBE_config_etablissement.xlsx"
$collecteurPath = Join-Path $PSScriptRoot "collecteur"
$profilePath = Join-Path $PSScriptRoot "master\profil_base.xlsx"
$masterOnboardingPath = Join-Path $PSScriptRoot "master\.onboarding_done"
$masterInstancesPath = Join-Path $PSScriptRoot "master\master_instances.json"
$masterInstancesExoPath = Join-Path $PSScriptRoot "master\master_instances_exercice.json"
$python_vEnv_name = ".venv"
$python_vEnv_executablePath = Join-Path $PSScriptRoot "$python_vEnv_name\Scripts\python.exe"


# Vérifier la présence de Python
if (!(Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host " X Python non trouve. Installez Python 3.10+."
    Pause
    Exit 1
}
# Activation du vEnv pour Python - Windows
Write-Host "Activation du vEnv Python"
$activateScript = Join-Path $PSScriptRoot "$python_vEnv_name\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
	"Activation du vEnv Python - OK"
} else {
    Write-Warning "Environnement virtuel non trouvé. Lancement 'python -m venv $python_vEnv_name'."
	python -m venv $python_vEnv_name
	. $activateScript
	"Creation et activation du vEnv Python OK"
}


if (!(Test-Path $python_vEnv_executablePath)) {
	Write-Host "Executable Python introuvable dans le vEnv. Utilisation du python par defaut"
	$python_vEnv_executablePath = "python"
	Start-Sleep -Seconds 2
}


# Afficher l'en-tête
Write-Host ""
Write-Host " ==============================================================="
Write-Host "  SCRIBE - Supervision avec pilotage d'instances"
Write-Host ""
Write-Host "  http://localhost:9000  -- Onglet `"INSTANCES`""
Write-Host ""
Write-Host "  Lancez/configurez vos instances depuis l'admin web."
Write-Host "  Ctrl+C pour arreter (toutes les instances filles aussi)."
Write-Host " ==============================================================="
Write-Host ""

# Vérifier et installer les dépendances
Write-Host " [info] Verification des dependances..."
if (Test-Path "requirements.txt") {
    #python -m pip install -q -r requirements.txt 2>$null
	Start-Process -FilePath $python_vEnv_executablePath -ArgumentList "-m pip install -q -r requirements.txt" -NoNewWindow -Wait -RedirectStandardError (Join-Path $PSScriptRoot "pip_install_error.log")
	Write-Host " [info] Dependance Python - main : OK"
}
if (Test-Path "collecteur\collecteur_requirements.txt") {
    #$python_vEnv_executablePath -m pip install -q -r collecteur\collecteur_requirements.txt 2>$null
	Start-Process -FilePath $python_vEnv_executablePath -ArgumentList "-m pip install -q -r collecteur\collecteur_requirements.txt" -NoNewWindow -Wait -RedirectStandardError (Join-Path $PSScriptRoot "pip_install_error.log")
	Write-Host " [info] Dependance Python - Collecteur : OK"
}

# Copier le profil de base si nécessaire
if ((Test-Path $profilePath)) {
	$reponse = Read-Host "Voulez-vous demarrer une nouvelle configuration ? (O/Y/N)"
	if ($reponse -eq "O"  -or $reponse -eq "o" -or $reponse -eq "Y" -or $reponse -eq "y") {
		Remove-Item -Path $profilePath -Force
		Remove-Item -Path $masterInstancesPath -Force
		Remove-Item -Path $masterInstancesExoPath -Force
		if ((Test-Path $masterOnboardingPath)) {
			Remove-Item -Path $masterOnboardingPath -Force
		}
		Remove-Item -Path "data\instances" -Force -Recurse
		Write-Host "Donnees supprimees."
	} else {
		# assurer que le marqueur onboarding est bien créé
		if (!(Test-Path $masterOnboardingPath)) {
			New-Item -Path $masterOnboardingPath -ItemType File
		}
	}
} else {
	Write-Host " [setup] Copie du profil de base..."
	if (Test-Path $source_config_etb) {
		Copy-Item $source_config_etb $profilePath -Force
		Write-Host " [setup] Copie du profil de base - OK..."
	}
}

# Créer les répertoires nécessaires
if (!(Test-Path "data\instances")) {
    New-Item -ItemType Directory -Path "data\instances" | Out-Null
}
if (!(Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}


Write-Host ""
Write-Host " >> Demarrage du navigateur en arriere plan"
Write-Host ""

$edgeProcess = Start-Process msedge -ArgumentList "--inprivate", "http://localhost:9000" -PassThru


Write-Host ""
Write-Host " >> Demarrage de la supervision sur :9000..."
Write-Host ""

# Changer de répertoire et lancer le collecteur
Set-Location $collecteurPath
Start-Process $python_vEnv_executablePath -ArgumentList "collecteur.py" -NoNewWindow

