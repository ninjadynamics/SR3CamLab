param([string]$Dir, [string]$Out)
Add-Type -AssemblyName System.Speech
$phrases = @(
 "thirty","fifty","seventy","one hundred","one fifty","one hundred fifty","two hundred","three hundred","four hundred","five hundred","six hundred","seven hundred","eight hundred","nine hundred",
 "three","two","one","go","finish","congratulations","checkpoint","check point","turn around","crest","small crest","small crest jump","long crest","caution very long crest","jump","wide","tight kink","kink","bump","small bump",
 "keep left","keep right","hazard","slippery","ice","beautiful","concentrate","excellent","great","hurry up","no","oh","oh no","outstanding","perfect","watch out","well done","wow","you are","sega rally two","sega rally","front","rear","left","right",
 "crest jump","narrow","bridge","in gravel","into gravel","on gravel","gravel","water","in tarmac","into tarmac","on tarmac","tarmac","tightens","tighten","double tightens","dont tighten","tightens dangerously","opens","open","over crest","over bump","caution","game over","time over")
$lens = @("","long ","very long ","very very long ")
$sev = @("easy","medium","hard","sharp","tight","kink","square","acute","fast","slow","flat","ninety","hairpin","open hairpin","wide hairpin")
foreach($l in $lens){ foreach($s in $sev){ foreach($d in @("left","right")){ $phrases += "$l$s $d"; $phrases += "$l$s $d maybe" } } }
$choices = New-Object System.Speech.Recognition.Choices
$choices.Add([string[]]$phrases)
$gb = New-Object System.Speech.Recognition.GrammarBuilder
$gb.Culture = [System.Globalization.CultureInfo]::GetCultureInfo("en-US")
$gb.Append($choices)
$g = New-Object System.Speech.Recognition.Grammar($gb)
$res = @()
Get-ChildItem -Path $Dir -Filter *.wav | Sort-Object Name | ForEach-Object {
  $e = New-Object System.Speech.Recognition.SpeechRecognitionEngine([System.Globalization.CultureInfo]::GetCultureInfo("en-US"))
  $e.LoadGrammar($g)
  $e.SetInputToWaveFile($_.FullName)
  $txt = ""; $conf = 0; $alts = ""
  try { $r = $e.Recognize(); if ($r -ne $null) { $txt = $r.Text; $conf = $r.Confidence; $alts = (($r.Alternates | Select-Object -First 3 | ForEach-Object { $_.Text + ":" + [math]::Round($_.Confidence,2) }) -join " / ") } } catch { $txt = "ERR " + $_.Exception.Message }
  $e.Dispose()
  $res += [pscustomobject]@{ file = $_.Name; text = $txt; confidence = [math]::Round($conf,3); alternates = $alts }
}
$res | Export-Csv -Path $Out -NoTypeInformation -Encoding UTF8
