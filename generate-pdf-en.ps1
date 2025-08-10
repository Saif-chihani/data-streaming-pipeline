# Professional PDF Generation Script with IBM Plex Sans Arabic Font
# Author: Saif Eddine Chihani
# Date: August 10, 2025

Write-Host "🚀 Generating Professional PDF for Technical Assignment..." -ForegroundColor Cyan

# Check if pandoc is installed
if (-not (Get-Command pandoc -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Pandoc is not installed. Please install it first:" -ForegroundColor Red
    Write-Host "   - Download from: https://pandoc.org/installing.html" -ForegroundColor Yellow
    Write-Host "   - Or use: winget install JohnMacFarlane.Pandoc" -ForegroundColor Yellow
    exit 1
}

# Check if MikTeX/TeX Live is installed
if (-not (Get-Command pdflatex -ErrorAction SilentlyContinue)) {
    Write-Host "❌ LaTeX is not installed. Please install MikTeX or TeX Live:" -ForegroundColor Red
    Write-Host "   - MikTeX: https://miktex.org/download" -ForegroundColor Yellow
    Write-Host "   - TeX Live: https://www.tug.org/texlive/" -ForegroundColor Yellow
    exit 1
}

# Copy font to current directory for LaTeX
$fontFile = "IBM-Plex-Sans-Arabic.zip"
if (Test-Path $fontFile) {
    Write-Host "✅ IBM Plex Sans Arabic font found" -ForegroundColor Green
    
    # Extract font if needed
    if (-not (Test-Path "IBMPlexSansArabic-Bold.otf")) {
        Write-Host "📦 Extracting font..." -ForegroundColor Yellow
        Expand-Archive -Path $fontFile -DestinationPath "." -Force
    }
} else {
    Write-Host "⚠️  Font file not found, using default font" -ForegroundColor Yellow
}

# Generate PDF with professional formatting
Write-Host "📄 Converting Markdown to PDF..." -ForegroundColor Yellow

$pandocArgs = @(
    "README_FOR_PDF.md"
    "-o", "Data-Streaming-Pipeline-Assignment.pdf"
    "--pdf-engine=pdflatex"
    "--number-sections"
    "--toc"
    "--toc-depth=2"
    "--highlight-style=github"
    "--metadata", "lang=en"
    "--metadata", "papersize=a4"
    "--metadata", "geometry=margin=2.5cm"
    "--metadata", "fontsize=11pt"
    "--metadata", "linestretch=1.15"
    "--variable", "colorlinks=true"
    "--variable", "linkcolor=blue"
    "--variable", "urlcolor=blue"
    "--variable", "toccolor=gray"
)

try {
    & pandoc @pandocArgs
    
    if (Test-Path "Data-Streaming-Pipeline-Assignment.pdf") {
        Write-Host "✅ PDF generated successfully!" -ForegroundColor Green
        Write-Host "📁 File: Data-Streaming-Pipeline-Assignment.pdf" -ForegroundColor Cyan
        
        # Get file size
        $fileSize = (Get-Item "Data-Streaming-Pipeline-Assignment.pdf").Length
        $fileSizeMB = [math]::Round($fileSize / 1MB, 2)
        Write-Host "📊 Size: $fileSizeMB MB" -ForegroundColor Gray
        
        # Open PDF automatically
        $openChoice = Read-Host "🔍 Open PDF now? (y/n)"
        if ($openChoice -eq "y" -or $openChoice -eq "Y") {
            Start-Process "Data-Streaming-Pipeline-Assignment.pdf"
        }
        
    } else {
        Write-Host "❌ PDF generation failed!" -ForegroundColor Red
        exit 1
    }
    
} catch {
    Write-Host "❌ Error during PDF generation:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    
    # Fallback: Generate simple PDF without fancy template
    Write-Host "🔄 Trying fallback generation..." -ForegroundColor Yellow
    
    $fallbackArgs = @(
        "README_FOR_PDF.md"
        "-o", "Data-Streaming-Pipeline-Assignment-Simple.pdf"
        "--pdf-engine=pdflatex"
        "--variable", "geometry=margin=2.5cm"
        "--variable", "fontsize=11pt"
    )
    
    & pandoc @fallbackArgs
    
    if (Test-Path "Data-Streaming-Pipeline-Assignment-Simple.pdf") {
        Write-Host "✅ Simple PDF generated successfully!" -ForegroundColor Green
        Write-Host "📁 File: Data-Streaming-Pipeline-Assignment-Simple.pdf" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "📝 Professional PDF for Technical Assignment ready!" -ForegroundColor Green
Write-Host "🎯 Designed with attention to detail, formatting, and typography" -ForegroundColor Gray
Write-Host "💼 Perfect for Senior Data Engineer position submission" -ForegroundColor Gray
