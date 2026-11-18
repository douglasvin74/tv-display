param($txt, $wav)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Maria Desktop')
$s.SetOutputToWaveFile($wav)
$s.Speak((Get-Content -Raw -Encoding UTF8 $txt))
$s.Dispose()
