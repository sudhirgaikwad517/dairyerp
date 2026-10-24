# Builds the customer portal (this app for the browser) into frontend/customer, served at /customer/.
# Commit frontend/customer after building; the server picks it up on the next deploy.
$out = Join-Path $PSScriptRoot "..\..\frontend\customer"
Push-Location $PSScriptRoot
flutter build web --release --base-href /customer/ --no-wasm-dry-run -o $out
Pop-Location
# The browser loads CanvasKit from Google's CDN, so the local copy is not needed
Remove-Item -Recurse -Force (Join-Path $out "canvaskit"), (Join-Path $out ".last_build_id") -ErrorAction SilentlyContinue
