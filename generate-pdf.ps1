# Script PowerShell pour générer le PDF professionnel
# Utilise pandoc avec la police IBM Plex Sans Arabic

Write-Host "🔄 Génération du PDF professionnel..." -ForegroundColor Blue

# Vérifier si pandoc est installé
if (!(Get-Command "pandoc" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Pandoc n'est pas installé." -ForegroundColor Red
    Write-Host "   Installation: winget install JohnMacFarlane.Pandoc" -ForegroundColor Yellow
    exit 1
}

# Vérifier si MiKTeX/TeX Live est installé
if (!(Get-Command "xelatex" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ XeLaTeX n'est pas installé." -ForegroundColor Red
    Write-Host "   Installation: Télécharger MiKTeX depuis https://miktex.org/" -ForegroundColor Yellow
    exit 1
}

# Copier la police dans le répertoire du projet
try {
    Copy-Item "..\IBMPlexSansArabic-Bold.otf" ".\IBMPlexSansArabic-Bold.otf" -Force
    Write-Host "✅ Police IBM Plex Sans Arabic copiée" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Police non trouvée, utilisation de la police par défaut" -ForegroundColor Yellow
}

# Configuration Pandoc
$inputFile = "PRESENTATION.md"
$outputFile = "Saif_Chihani_Pipeline_Streaming_Donnees.pdf"

# Arguments Pandoc
$pandocArgs = @(
    $inputFile,
    "--pdf-engine=xelatex",
    "--output=$outputFile",
    "--number-sections",
    "--toc",
    "--toc-depth=2", 
    "--highlight-style=github",
    "--variable=colorlinks:true",
    "--variable=linkcolor:blue",
    "--variable=urlcolor:blue",
    "--variable=fontsize:11pt",
    "--variable=geometry:margin=2.5cm",
    "--variable=linestretch:1.15"
)

Write-Host "🔄 Exécution de pandoc..." -ForegroundColor Blue

# Générer le PDF
try {
    & pandoc @pandocArgs
    
    if (Test-Path $outputFile) {
        $fileSize = (Get-Item $outputFile).Length / 1MB
        Write-Host "✅ PDF généré avec succès: $outputFile" -ForegroundColor Green
        Write-Host "📄 Taille du fichier: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Green
        Write-Host "📝 Police utilisée: IBM Plex Sans Arabic Bold" -ForegroundColor Green
        
        # Ouvrir le PDF automatiquement
        $openPdf = Read-Host "Voulez-vous ouvrir le PDF? (o/n)"
        if ($openPdf -eq "o" -or $openPdf -eq "O") {
            Start-Process $outputFile
        }
    } else {
        Write-Host "❌ Erreur: Le fichier PDF n'a pas été créé" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Erreur lors de la génération du PDF: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Nettoyer les fichiers temporaires
if (Test-Path "IBMPlexSansArabic-Bold.otf") {
    Remove-Item "IBMPlexSansArabic-Bold.otf" -Force
}

Write-Host "🎉 Génération terminée!" -ForegroundColor Green
