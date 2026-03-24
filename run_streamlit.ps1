Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $py) {
    & $py -m streamlit run app.py
} else {
    py -m streamlit run app.py
}
