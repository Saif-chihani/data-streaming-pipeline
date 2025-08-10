#!/bin/bash

# Script de génération PDF professionnel
# Utilise pandoc avec la police IBM Plex Sans Arabic

echo "🔄 Génération du PDF professionnel..."

# Vérifier si pandoc est installé
if ! command -v pandoc &> /dev/null; then
    echo "❌ Pandoc n'est pas installé. Installation requise:"
    echo "   Windows: winget install JohnMacFarlane.Pandoc"
    echo "   Mac: brew install pandoc"
    exit 1
fi

# Vérifier si xelatex est disponible
if ! command -v xelatex &> /dev/null; then
    echo "❌ XeLaTeX n'est pas installé. Installation requise:"
    echo "   Windows: MiKTeX ou TeX Live"
    echo "   Mac: brew install --cask mactex"
    exit 1
fi

# Copier la police dans le répertoire du projet
cp "../IBMPlexSansArabic-Bold.otf" "./IBMPlexSansArabic-Bold.otf"

# Générer le PDF
pandoc PRESENTATION.md \
    --pdf-engine=xelatex \
    --output="Saif_Chihani_Pipeline_Streaming_Donnees.pdf" \
    --template=eisvogel \
    --listings \
    --number-sections \
    --toc \
    --toc-depth=2 \
    --highlight-style=github \
    --variable=colorlinks:true \
    --variable=linkcolor:blue \
    --variable=urlcolor:blue \
    --variable=toccolor:gray \
    --variable=book:true \
    --variable=classoption:openany

if [ $? -eq 0 ]; then
    echo "✅ PDF généré avec succès: Saif_Chihani_Pipeline_Streaming_Donnees.pdf"
    echo "📄 Taille du fichier: $(du -h Saif_Chihani_Pipeline_Streaming_Donnees.pdf | cut -f1)"
    echo "📝 Police utilisée: IBM Plex Sans Arabic Bold"
else
    echo "❌ Erreur lors de la génération du PDF"
    exit 1
fi

# Nettoyer les fichiers temporaires
rm -f IBMPlexSansArabic-Bold.otf

echo "🎉 Génération terminée!"
