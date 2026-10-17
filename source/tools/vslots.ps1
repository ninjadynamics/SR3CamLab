$src = Get-Content "$PSScriptRoot\pvs.ps1" -Raw; $cut = $src.IndexOf('[PV]::Open'); Invoke-Expression $src.Substring($src.IndexOf('Add-Type'), $cut - $src.IndexOf('Add-Type'))
[PV]::Open((Get-Process Rally).Id)
for ($i = 0; $i -lt 20; $i++) {
  $s = 0xAD2F90 + 0x16C * $i; $b = [PV]::R($s, 0x16C)
  $u = { param($o) [BitConverter]::ToUInt32($b, $o) }
  $name = [Text.Encoding]::ASCII.GetString($b, 0xC, 0x100).Split([char]0)[0]
  '{0,2}: playing {1} tex {2:X8} graph {3:X8} ctl {4:X8} ev {5:X8} 128 {6:X8} src {7:X8} rnd {8:X8}  {9}' -f $i, (& $u 0), (& $u 4), (& $u 0x11C), (& $u 0x120), (& $u 0x124), (& $u 0x128), (& $u 0x12C), (& $u 0x130), $name
}
