$base = "http://127.0.0.1:8000/api/v1"
$ErrorActionPreference = "Stop"

Write-Host "--- 1. Health ---"
(Invoke-RestMethod "$base/health") | ConvertTo-Json -Compress

Write-Host "--- 2. Admin login ---"
$login = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType "application/json" -Body '{"email":"admin@gmail.com","password":"admin123"}'
$H = @{ Authorization = "Bearer $($login.access_token)" }
Write-Host "token OK (len=$($login.access_token.Length))"

Write-Host "--- 3. /auth/me ---"
$me = Invoke-RestMethod -Uri "$base/auth/me" -Headers $H
Write-Host "user=$($me.email) role=$($me.role_name) perms=$($me.permissions.Count)"

Write-Host "--- 4. Roles & permissions seeded ---"
$roles = Invoke-RestMethod -Uri "$base/roles" -Headers $H
$perms = Invoke-RestMethod -Uri "$base/permissions?limit=500" -Headers $H
Write-Host "roles=$($roles.role_name -join ', ') | permissions=$($perms.Count)"

Write-Host "--- 5. Organization CRUD ---"
$org = Invoke-RestMethod -Method Post -Uri "$base/organizations" -Headers $H -ContentType "application/json" -Body '{"name":"Demo Organization","description":"Primary NMS tenant"}'
Write-Host "created org id=$($org.id)"
$org2 = Invoke-RestMethod -Method Patch -Uri "$base/organizations/$($org.id)" -Headers $H -ContentType "application/json" -Body '{"description":"updated"}'
Write-Host "updated org desc=$($org2.description)"

Write-Host "--- 6. Site + Device CRUD ---"
$site = Invoke-RestMethod -Method Post -Uri "$base/sites" -Headers $H -ContentType "application/json" -Body ('{"organization_id":' + $org.id + ',"name":"Head Office","city":"Delhi","state":"Delhi","latitude":28.6139,"longitude":77.209}')
$dev = Invoke-RestMethod -Method Post -Uri "$base/devices" -Headers $H -ContentType "application/json" -Body ('{"site_id":' + $site.id + ',"hostname":"core-switch-01","ip_address":"192.168.1.10","model":"Catalyst","status":"online","monitoring_status":true}')
Write-Host "site id=$($site.id), device id=$($dev.id)"
$null = Invoke-RestMethod -Method Post -Uri "$base/devices/$($dev.id)/monitoring/false" -Headers $H
Write-Host "monitoring disabled OK"

Write-Host "--- 7. Metric + Alert flow ---"
$metric = Invoke-RestMethod -Method Post -Uri "$base/device-metrics" -Headers $H -ContentType "application/json" -Body ('{"device_id":' + $dev.id + ',"cpu_usage":45.5,"memory_usage":62.0,"latency":12.4}')
$alert = Invoke-RestMethod -Method Post -Uri "$base/alerts" -Headers $H -ContentType "application/json" -Body ('{"device_id":' + $dev.id + ',"severity":"critical","title":"Device Down","status":"open"}')
$null = Invoke-RestMethod -Method Post -Uri "$base/alerts/$($alert.id)/acknowledge" -Headers $H
$res = Invoke-RestMethod -Method Post -Uri "$base/alerts/$($alert.id)/resolve" -Headers $H
Write-Host "metric id=$($metric.id), alert id=$($alert.id) final status=$($res.status)"

Write-Host "--- 8. Create Viewer user & test RBAC ---"
$rolesList = Invoke-RestMethod -Uri "$base/roles" -Headers $H
$viewerRole = ($rolesList | Where-Object { $_.role_name -eq "Viewer" })
$null = Invoke-RestMethod -Method Post -Uri "$base/users" -Headers $H -ContentType "application/json" -Body ('{"name":"Viewer User","email":"viewer@gmail.com","password":"viewer123","role_id":' + $viewerRole.id + ',"status":"active"}')
$vLogin = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType "application/json" -Body '{"email":"viewer@gmail.com","password":"viewer123"}'
$VH = @{ Authorization = "Bearer $($vLogin.access_token)" }
$devices = Invoke-RestMethod -Uri "$base/devices" -Headers $VH
Write-Host "viewer can READ devices: count=$($devices.Count)"
try {
    Invoke-RestMethod -Method Post -Uri "$base/devices" -Headers $VH -ContentType "application/json" -Body '{"hostname":"x","ip_address":"10.0.0.99"}'
    Write-Host "RBAC FAILED: viewer created a device!"
} catch {
    Write-Host "viewer CREATE device blocked -> $($_.Exception.Response.StatusCode.value__) (expected 403)"
}
try {
    Invoke-RestMethod -Uri "$base/devices" | Out-Null
    Write-Host "AUTH FAILED: anonymous read allowed!"
} catch {
    Write-Host "anonymous request blocked -> $($_.Exception.Response.StatusCode.value__) (expected 401/403)"
}

Write-Host "--- 9. Dashboard + audit logs ---"
$dash = Invoke-RestMethod -Uri "$base/dashboard/summary" -Headers $H
Write-Host ("dashboard: " + ($dash | ConvertTo-Json -Compress))
$logs = Invoke-RestMethod -Uri "$base/audit-logs?limit=5" -Headers $H
Write-Host "audit logs recorded: $($logs.Count) (latest: $($logs[0].action) $($logs[0].resource_name))"

Write-Host "--- 10. Cleanup delete (CRUD delete) ---"
$null = Invoke-RestMethod -Method Delete -Uri "$base/device-metrics/$($metric.id)" -Headers $H
$null = Invoke-RestMethod -Method Delete -Uri "$base/alerts/$($alert.id)" -Headers $H
Write-Host "deletes OK"

Write-Host "=== ALL CHECKS PASSED ==="
