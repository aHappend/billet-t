param(
    [switch]$CompileOnly,
    [string]$ExpectedMagic,
    [string]$ExpectedWorkloadSha256,
    [string]$ExpectedScriptSha256,
    [string]$RunIdentity,
    [string]$DevicePath,
    [string]$InputPath,
    [string]$ExpectedInputSha256,
    [string]$TracePath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)

function Read-BoundFile([string]$Path, [string]$ExpectedHash) {
    if ($ExpectedHash -cnotmatch '^[0-9a-f]{64}$') { throw "Invalid SHA-256 binding for $Path" }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { $actual = [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
    if ($actual -cne $ExpectedHash) { throw "SHA-256 mismatch for $Path" }
    return ,$bytes
}

$null = Read-BoundFile $PSCommandPath $ExpectedScriptSha256
$companionPath = Join-Path $PSScriptRoot 'Workload.cs'
$source = Read-BoundFile $companionPath $ExpectedWorkloadSha256
Add-Type -TypeDefinition ($utf8.GetString($source)) -Language CSharp
if ($CompileOnly) {
    [Console]::Write('{"passed":true,"hardware_access":false,"compile_only":true}')
    exit 0
}

if ($ExpectedMagic -cne '0x42494c4c45545431' -or
    [string]::IsNullOrWhiteSpace($RunIdentity) -or [string]::IsNullOrWhiteSpace($TracePath)) {
    throw 'Missing managed campaign identity, trace, or exact Billet-T1 magic.'
}
$inputBytes = Read-BoundFile $InputPath $ExpectedInputSha256
$payload = ConvertFrom-Json -InputObject ($utf8.GetString($inputBytes))
# The offline contract verifies these increments against the independently bound input frames.
$clampPlan = ConvertFrom-Json -InputObject @'
[
  {"id":"impulse","increments":[0]},
  {"id":"tone","increments":[0]},
  {"id":"broadband","increments":[0]},
  {"id":"dc","increments":[0]},
  {"id":"nyquist","increments":[0]},
  {"id":"tone_bin_1","increments":[0]},
  {"id":"tone_bin_7","increments":[0]},
  {"id":"tone_bin_63","increments":[0]},
  {"id":"tone_bin_127","increments":[0]},
  {"id":"adjacent_31_32","increments":[0]},
  {"id":"quadrature","increments":[0]},
  {"id":"chirp","increments":[0]},
  {"id":"rails","increments":[58]},
  {"id":"conjugate_symmetry","increments":[0]},
  {"id":"serialized_16","increments":[0,0,0,0,0,0,42,0,0,0,0,0,0,0,0,0]}
]
'@
if ($payload.schema -ne 1 -or $payload.workload_protocol -cne 'softreg-readback/v1' -or @($payload.runs).Count -ne 3) {
    throw 'Invalid managed soft-register vector envelope.'
}
foreach ($run in $payload.runs) {
    if (@($run.vectors).Count -ne $clampPlan.Count) { throw 'Invalid spectral vector count.' }
    for ($i = 0; $i -lt $clampPlan.Count; $i++) {
        $vector = $run.vectors[$i]
        $expected = $clampPlan[$i]
        if ($vector.id -cne $expected.id -or @($vector.inputs).Count -ne 256 * $expected.increments.Count) {
            throw "Unexpected vector ID, vector order, or sample count at index $i."
        }
        foreach ($sample in $vector.inputs) {
            if (($sample -isnot [int] -and $sample -isnot [long]) -or $sample -lt 0 -or $sample -gt [uint32]::MaxValue) {
                throw "Vector $($vector.id) contains a sample outside unsigned packed Q1.15."
            }
        }
    }
}

$device = [BilletT1.SoftRegisters]::new($DevicePath)
try {
    $identityObservations = @($device.VerifyIdentity($ExpectedMagic))
    $clock = [System.Diagnostics.Stopwatch]::StartNew()
    $runs = [System.Collections.Generic.List[object]]::new()
    $comparisons = 0
    foreach ($run in $payload.runs) {
        $vectors = [System.Collections.Generic.List[object]]::new()
        for ($i = 0; $i -lt $clampPlan.Count; $i++) {
            $vector = $run.vectors[$i]
            $result = $device.RunVector($vector.id, [uint32[]]$vector.inputs, [uint32[]]$clampPlan[$i].increments, $clock)
            $vectors.Add($result)
            $comparisons += $vector.inputs.Count + 4 * $result.frames.Length
        }
        $runs.Add(@{ vectors = @($vectors.ToArray()) })
    }
    # Runtime compares the full output bytes to its separately bound oracle, then restores App1.
    $trace = [ordered]@{
        workload_protocol = 'softreg-readback/v1'; passed = $true; hardware_access = $true
        run_identity = $RunIdentity; device_path = $DevicePath; input_sha256 = $ExpectedInputSha256
        expected_magic = $ExpectedMagic; observed_magic = $identityObservations[0].ValueHex
        comparisons = $comparisons; mismatches = 0; observations = $identityObservations
        host_stopwatch_frequency_hz = [System.Diagnostics.Stopwatch]::Frequency
        transaction_encoding = 'r=read word, w=write word, v=unsigned 64-bit value'
        runs = @($runs.ToArray())
    }
} finally {
    $device.Dispose()
}

$json = ConvertTo-Json -InputObject $trace -Depth 12 -Compress
$encoded = $utf8.GetBytes($json)
if ($encoded.Length -gt 4MB) { throw 'Complete trace exceeds the managed business capture limit.' }
$file = [System.IO.File]::Open($TracePath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
try { $file.Write($encoded, 0, $encoded.Length) }
finally { $file.Dispose() }
$stdout = [Console]::OpenStandardOutput()
$stdout.Write($encoded, 0, $encoded.Length)
$stdout.Flush()
exit 0
