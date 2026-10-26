$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ('onepro-usb-tests-' + [guid]::NewGuid())
[System.IO.Directory]::CreateDirectory($temporary) | Out-Null
try {
    $support = (Join-Path $PSScriptRoot 'UsbCdcTestSupport.hpp').Replace('\', '/')
    foreach ($header in @('FreeRTOS.h', 'task.h', 'semphr.h', 'cmsis_os.h', 'cmsis_os2.h', 'usb_device.h', 'usbd_cdc_if.h', 'usbd_cdc.h', 'usbd_core.h')) {
        [System.IO.File]::WriteAllText((Join-Path $temporary $header), "#include `"$support`"`n")
    }
    $executable = Join-Path $temporary 'usb-tests.exe'
    & g++ -std=gnu++14 -Wall -Wextra -Werror -Wno-missing-field-initializers -include "$support" "-I$temporary" "-I$root/Application" "-I$PSScriptRoot" `
        "$PSScriptRoot/UsbCdcTransportTests.cpp" "$root/Application/UsbCdcTransport.cpp" `
        "$root/Application/Comm.cpp" "$root/Application/MutexLock.cpp" "$root/USB_DEVICE/App/usbd_cdc_if.c" -o $executable
    if ($LASTEXITCODE -ne 0) { throw 'USB host test compilation failed' }
    & $executable
    if ($LASTEXITCODE -ne 0) { throw 'USB host tests failed' }
    Push-Location $root
    try {
        $baseline = (& git show 'HEAD:Application/App.cpp') -join "`n"
        if ($LASTEXITCODE -ne 0) { throw 'Cannot load dispatcher baseline' }
        $current = [System.IO.File]::ReadAllText((Join-Path $root 'Application/App.cpp'))
        $baseline = $baseline.Substring($baseline.IndexOf('void App::HandleCommand'))
        $current = $current.Substring($current.IndexOf('void App::HandleCommand'))
        $literalPattern = '"(?:\\.|[^"\\])*"'
        $oldLiterals = ([regex]::Matches($baseline, $literalPattern) | ForEach-Object { $_.Value }) -join "`n"
        $newLiterals = ([regex]::Matches($current, $literalPattern) | ForEach-Object { $_.Value }) -join "`n"
        if ($oldLiterals -cne $newLiterals) { throw 'Command or response literals changed' }
        if ($current.Contains('_comm.SendResponse')) { throw 'Dispatcher contains hardcoded UART reply' }
        $helpBytes = 4
        foreach ($match in [regex]::Matches($current, 'helpPrinter << "((?:\\.|[^"\\])*)"')) {
            $helpBytes += [regex]::Unescape($match.Groups[1].Value).Length
        }
        if ($helpBytes -gt 2048) { throw 'Help exceeds USB response reservation' }
        & git diff --quiet HEAD -- Application/Uart.cpp Application/Uart.hpp Core/Src/usart.c Core/Src/dma.c
        if ($LASTEXITCODE -ne 0) { throw 'UART driver or DMA differs from baseline' }
        Write-Output "PASS: command/response literals unchanged, source-only dispatcher, help=$helpBytes bytes, UART driver/DMA unchanged"
    }
    finally { Pop-Location }
}
finally {
    Remove-Item -Recurse -Force $temporary
}