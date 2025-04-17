# Fájl neve lehet pl.: auto_push.ps1

cd C:\projekt

# Git hozzáadás
git add .

# Dátumalapú üzenet
$time = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
git commit -m "Auto backup $time"

# Push a GitHub repóra
git push origin main
