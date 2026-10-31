# Run in Windows PowerShell 5.1+ with Git and GitHub CLI installed.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Установите Git for Windows.' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Установите GitHub CLI и выполните gh auth login.' }
& gh auth status 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Выполните gh auth login.' }
$owner = (& gh api user --jq .login).Trim()
if ($LASTEXITCODE -ne 0 -or -not $owner) { throw 'Не удалось получить GitHub login.' }
$repo = "$owner/yandex-downloader"
if (-not (Test-Path .git)) { & git init -b main; if ($LASTEXITCODE -ne 0) { throw 'git init завершился с ошибкой' } }
$origin = & git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    if ($origin -notin @("https://github.com/$repo.git", "git@github.com:$repo.git")) {
        throw "origin указывает на другой репозиторий: $origin"
    }
}
& git add README.md app.py downloader.py requirements.txt requirements-build.txt assets/ .github/ tests/ .gitignore *.sh *.bat *.ps1
if ($LASTEXITCODE -ne 0) { throw 'git add завершился с ошибкой' }
& git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    & git commit -m 'Release Yandex Downloader v1.0.1'
    if ($LASTEXITCODE -ne 0) { throw 'git commit завершился с ошибкой. Настройте git user.name и user.email.' }
}
& gh repo view $repo *> $null
if ($LASTEXITCODE -eq 0) {
    & git remote get-url origin *> $null
    if ($LASTEXITCODE -ne 0) { & git remote add origin "https://github.com/$repo.git" }
    & git push -u origin main
} else {
    & gh repo create $repo --public --source=. --remote=origin --push --description 'Yandex Music desktop downloader for Windows and Omarchy Linux'
}
if ($LASTEXITCODE -ne 0) { throw 'Не удалось отправить проект на GitHub.' }
Write-Host "Репозиторий: https://github.com/$repo"
Write-Host "Сборки: https://github.com/$repo/actions"
Write-Host "Релиз после успешной сборки: https://github.com/$repo/releases"