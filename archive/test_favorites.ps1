# Автотест системы избранного
# Запустить: .\test_favorites.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AUTO-TEST FAVORITES SYSTEM" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$URL = "https://hyperstls.pythonanywhere.com"
$errors = 0
$warnings = 0

# 1. Test /workers page
Write-Host "1. Testing /workers page" -ForegroundColor Yellow
Write-Host "------------------------" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "$URL/workers" -UseBasicParsing
    $html = $response.Content
    
    # Check for favorite button
    if ($html -like "*В избранное*") {
        Write-Host "[PASS] 'Add to favorites' button found" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] 'Add to favorites' button NOT found" -ForegroundColor Red
        $errors++
    }
    
    # Check for toggleFavorite
    if ($html -like '*onclick="toggleFavorite*') {
        Write-Host "[PASS] toggleFavorite function is called" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] toggleFavorite function NOT called" -ForegroundColor Red
        $errors++
    }
    
    # Check for stopPropagation
    if ($html -like "*stopPropagation*") {
        Write-Host "[PASS] stopPropagation found" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] stopPropagation NOT found" -ForegroundColor Red
        $warnings++
    }
    
} catch {
    Write-Host "[ERROR] Failed to load /workers: $($_.Exception.Message)" -ForegroundColor Red
    $errors++
}

Write-Host ""

# 2. Test API endpoints
Write-Host "2. Testing API endpoints" -ForegroundColor Yellow
Write-Host "------------------------" -ForegroundColor Yellow

# Test /api/favorites/add
try {
    $body = @{ worker_id = "test-worker-123" } | ConvertTo-Json
    $response = Invoke-WebRequest -Uri "$URL/api/favorites/add" -Method POST -ContentType "application/json" -Body $body -UseBasicParsing
    Write-Host "[PASS] /api/favorites/add OK (Status: $($response.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] /api/favorites/add error: $($_.Exception.Message)" -ForegroundColor Red
    $errors++
}

# Test /api/favorites/check
try {
    $body = @{ worker_id = "test-worker-123" } | ConvertTo-Json
    $response = Invoke-WebRequest -Uri "$URL/api/favorites/check" -Method POST -ContentType "application/json" -Body $body -UseBasicParsing
    Write-Host "[PASS] /api/favorites/check OK (Status: $($response.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] /api/favorites/check error: $($_.Exception.Message)" -ForegroundColor Red
    $errors++
}

Write-Host ""

# 3. Test /favorites page
Write-Host "3. Testing /favorites page" -ForegroundColor Yellow
Write-Host "--------------------------" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "$URL/favorites" -UseBasicParsing
    $html = $response.Content
    
    if ($html -like "*Удалить из избранного*") {
        Write-Host "[PASS] 'Remove from favorites' button found" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] 'Remove from favorites' button NOT found" -ForegroundColor Red
        $errors++
    }
    
} catch {
    Write-Host "[ERROR] Failed to load /favorites: $($_.Exception.Message)" -ForegroundColor Red
    $errors++
}

Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Errors: $errors" -ForegroundColor $(if ($errors -eq 0) { "Green" } else { "Red" })
Write-Host "Warnings: $warnings" -ForegroundColor Yellow

if ($errors -eq 0) {
    Write-Host ""
    Write-Host "SUCCESS! All tests passed." -ForegroundColor Green
    Write-Host ""
    Write-Host "Deploy to PythonAnywhere:" -ForegroundColor Cyan
    Write-Host "  cd ~/mysite && git pull && touch /var/www/hyperstls_pythonanywhere_com_wsgi.py" -ForegroundColor White
    exit 0
} else {
    Write-Host ""
    Write-Host "ERRORS FOUND! Check output above." -ForegroundColor Red
    exit 1
}
