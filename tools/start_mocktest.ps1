# Runs patch.ps1's START logic without a game: Step-Start (a short press = a screenshot when it is let go, a long one =
# leave the race) on made-up button and menu timelines, then Request-RaceExit / Step-RaceExit against a fake game memory
# that plays the game's part (the race update taking the flag, the states that follow). Same method as switch_mocktest.ps1:
# the script is cut before its launch part and the game's memory is a dictionary. Counts on the last line.
$src = Get-Content (Join-Path $PSScriptRoot '..\patch.ps1') -Raw
$cut = $src.IndexOf('# ---- launch (unless')
$body = $src.Substring(0, $cut).Replace('[Sr3Mem]::Write', '[MockRace]::Write').Replace('[Sr3Mem]::Read', '[MockRace]::Read').Replace('. (Join-Path $PSScriptRoot ''setup.ps1'')', ". '" + (Join-Path $PSScriptRoot '..\setup.ps1') + "'")
Add-Type @"
using System; using System.Collections.Generic;
public static class MockRace {
    public static Dictionary<long, byte> M = new Dictionary<long, byte>();
    public static List<string> Writes = new List<string>();
    public static int StateReads = 0, FlipAfter = -1, FlipTo = 0;      // a state that changes between two reads
    public static void Write(IntPtr h, long va, byte[] b, bool w) { for (int i = 0; i < b.Length; i++) M[va + i] = b[i]; Writes.Add(String.Format("{0:X}+{1}", va, b.Length)); }
    public static byte[] Read(IntPtr h, long va, int n) {
        if (va == 0x7ECE10 && FlipAfter >= 0 && StateReads++ == FlipAfter) { PutI(0x7ECE10, FlipTo); PutI(0x7ECE14, FlipTo); }
        var b = new byte[n]; for (int i = 0; i < n; i++) { byte v; if (!M.TryGetValue(va + i, out v)) return null; b[i] = v; } return b;
    }
    public static int I(long a) { return M[a] | (M[a + 1] << 8) | (M[a + 2] << 16) | (M[a + 3] << 24); }
    public static void PutI(long a, int v) { for (int i = 0; i < 4; i++) M[a + i] = (byte)(v >> (8 * i)); }
    public static void PutL(long a, long v) { for (int i = 0; i < 8; i++) M[a + i] = (byte)(v >> (8 * i)); }
    public static long L(long a) { long v = 0; for (int i = 7; i >= 0; i--) v = (v << 8) | M[a + i]; return v; }
    public static float F(long a) { return BitConverter.ToSingle(new byte[] { M[a], M[a + 1], M[a + 2], M[a + 3] }, 0); }
}
"@
$body += @'

$script:pass = 0; $script:fail = 0; $script:Logged = New-Object System.Collections.ArrayList
function Log($m) { [void]$script:Logged.Add($m) }
function Check([string]$what, [bool]$ok, [string]$got) {
    if ($ok) { $script:pass++; $v = 'ok    ' } else { $script:fail++; $v = 'FAILED' }
    '  {0} {1}{2}' -f $v, $what, $(if ($got) { ": $got" } else { '' })
}

# ---- Step-Start on timelines: ticks of 15 ms like Watch-Tracks; START is down inside the press windows, the menus are up
# inside the menu windows. Prints what came out and when.
function Timeline([double]$end, $presses, $menus) {
    $s = New-StartState; $t0 = [datetime]'2026-10-14 12:00:00'; $out = @()
    for ($ms = 0; $ms -le $end * 1000; $ms += 15) {
        $t = $ms / 1000.0
        $down = [bool](@($presses | Where-Object { $t -ge $_[0] -and $t -lt $_[1] }).Count)
        $menu = [bool](@($menus | Where-Object { $t -ge $_[0] -and $t -lt $_[1] }).Count)
        foreach ($a in (Step-Start $s $down $menu $t0.AddMilliseconds($ms))) { $out += ('{0}@{1:0.00}' -f $a, $t) }
    }
    return ,$out
}
function Near($out, [string]$act, [double]$at) { return [bool](@($out | Where-Object { $_ -match "^$act@" -and [Math]::Abs([double]($_ -split '@')[1] - $at) -le 0.031 }).Count) }
"1. START, short and long presses (hold for the exit: $StartHoldSeconds s)"
$o = Timeline 6 @(,@(2.0, 2.3)) @(,@(0, 1))
Check 'short press in a race: one picture when START is let go (2.3 s), saved 1.5 s later' ($o.Count -eq 2 -and (Near $o 'grab' 2.3) -and (Near $o 'save' 3.8)) ($o -join ' ')
$o = Timeline 6 @(,@(2.0, 4.0)) @(,@(0, 1))
Check 'long press in a race: the exit, once, at 1.2 s of the hold; no picture' ($o.Count -eq 1 -and (Near $o 'exit' 3.2)) ($o -join ' ')
$o = Timeline 14 @(,@(2.0, 12.0)) @(,@(0, 1))
Check 'held for 10 s: still one exit' ($o.Count -eq 1 -and (Near $o 'exit' 3.2)) ($o -join ' ')
$o = Timeline 6 @(@(1.0, 1.2), @(1.5, 3.5), @(4.0, 5.5)) @(,@(0, 6))
Check 'presses while the menus are up (short, long, longer): nothing' ($o.Count -eq 0) ($o -join ' ')
$o = Timeline 6 @(,@(2.0, 4.5)) @(,@(0, 3))
Check 'a press that began in the menus and is held into the race: nothing' ($o.Count -eq 0) ($o -join ' ')
$o = Timeline 4 @(,@(1.0, 1.1)) @()
Check 'before the menus were ever up (attract after launch): nothing' ($o.Count -eq 0) ($o -join ' ')
$o = Timeline 9 @(@(2.0, 2.2), @(2.6, 2.8), @(3.5, 3.7), @(4.5, 4.7)) @(,@(0, 1))
Check 'presses 0.6, 1.5 and 2.5 s after a picture: only the last one takes one (2 s apart)' ($o.Count -eq 4 -and (Near $o 'grab' 2.2) -and (Near $o 'save' 3.7) -and (Near $o 'grab' 4.7) -and (Near $o 'save' 6.2)) ($o -join ' ')
$o = Timeline 6 @(,@(2.0, 2.1)) @(@(0, 1), @(2.5, 6))
Check 'START began a game (the menus come up 0.4 s later): the picture is dropped, not saved' ($o.Count -eq 2 -and (Near $o 'grab' 2.1) -and (Near $o 'drop' 2.5)) ($o -join ' ')
$o = Timeline 7 @(,@(2.0, 6.0)) @(@(0, 1), @(4.0, 7))
Check 'a long press that left the race: the menus come up while START is still held, nothing more on letting go' ($o.Count -eq 1 -and (Near $o 'exit' 3.2)) ($o -join ' ')
$o = Timeline 8 @(@(2.0, 2.2), @(2.5, 4.0)) @(,@(0, 1))
Check 'a picture, then a long press while it is held back: the picture is saved, and the race left' ($o.Count -eq 3 -and (Near $o 'grab' 2.2) -and (Near $o 'exit' 3.7) -and (Near $o 'save' 3.7)) ($o -join ' ')
$o = Timeline 6 @(,@(2.0, 3.1)) @(,@(0, 1))
Check 'a press just under the hold time (1.1 s): a picture, no exit' ($o.Count -eq 2 -and (Near $o 'grab' 3.1)) ($o -join ' ')

# ---- the exit against a fake game ----
$h = [IntPtr]::Zero; $t0 = [datetime]'2026-10-14 12:00:00'
function Game([int]$state, [int]$next, [int]$mode, [int]$pos = 3, [int]$stage = 1, [int]$stages = 3) {
    [MockRace]::M.Clear(); [MockRace]::Writes.Clear(); [MockRace]::FlipAfter = -1; [MockRace]::StateReads = 0; $script:Logged.Clear(); $script:RaceExit = $null
    [MockRace]::PutI(0x7ECE10, $state); [MockRace]::PutI(0x7ECE14, $next); [MockRace]::PutI(0x728598, $mode); [MockRace]::PutI(0x9DB4F4, 0)
    for ($a = 0x9DB490; $a -lt 0x9DB4AC; $a += 4) { [MockRace]::PutI($a, 0) }
    [MockRace]::PutL(0x9DB490, 123456); [MockRace]::PutI(0x9DB498, 1); [MockRace]::PutI(0x9DB4A8, 0x43FA0000)   # a fade-in long done: start 123456 ms, in, 500.0
    [MockRace]::PutL(0x9C4A08, 987654321987)                                                                       # the game's clock, us
    [MockRace]::PutI(0x9DB820, $stage); [MockRace]::PutI(0x9DD61C, $pos)
    [MockRace]::PutI(0xB2A850, 0x31000000); [MockRace]::PutI(0x31000010, 0x31000100); [MockRace]::PutI(0x31000104, $stages)
}
function Flag { [MockRace]::I(0x9DB4F4) }
function Fade { 'start {0} ms, {1}, +C {2}, +10 {3}, {4} ms' -f [MockRace]::L(0x9DB490), $(if ([MockRace]::I(0x9DB498)) { 'in' } else { 'out' }), [MockRace]::I(0x9DB49C), [MockRace]::I(0x9DB4A0), [MockRace]::F(0x9DB4A8) }
function Steps([double]$from, [double]$to, [scriptblock]$game) {   # Step-RaceExit every 20 ms, the fake game moving on as $game says
    for ($ms = [int]($from * 1000); $ms -le $to * 1000 -and $script:RaceExit; $ms += 20) { & $game ($ms / 1000.0); Step-RaceExit $h $t0.AddMilliseconds($ms) }
}
$doneFade = 'start 987654321 ms, out, +C 1, +10 0, 500 ms'
"2. leaving a race (fake game)"
Game 0x27 0x27 5
Request-RaceExit $h $t0
Check 'Quick Race: the flag is set' ((Flag) -eq 1) "flag $(Flag)"
Check 'and the fade to black starts as the game starts it (clock / 1000, out, 500 ms)' ((Fade) -eq $doneFade) (Fade)
Check 'the fade block goes in one write, before the flag' (([MockRace]::Writes -join ' ') -eq '9DB490+28 9DB4F4+4') ([MockRace]::Writes -join ' ')
Check 'no championship values touched' ([MockRace]::I(0x9DB820) -eq 1 -and [MockRace]::I(0x9DD61C) -eq 3) ''
Steps 0.02 3 { param($t) if ($t -ge 0.05 -and (Flag)) { [MockRace]::PutI(0x9DB4F4, 0); [MockRace]::PutI(0x7ECE14, 0x1B) }   # the race update takes it
                            if ($t -ge 0.07) { [MockRace]::PutI(0x7ECE10, 0x1B); [MockRace]::PutI(0x7ECE14, 0x2A) }; if ($t -ge 0.09) { [MockRace]::PutI(0x7ECE10, 0x2A) }
                            if ($t -ge 0.6) { [MockRace]::PutI(0x7ECE10, 0x1D); [MockRace]::PutI(0x7ECE14, 0x1D) }; if ($t -ge 0.62) { [MockRace]::PutI(0x7ECE10, 2); [MockRace]::PutI(0x7ECE14, 2) } }
Check 'the game takes it and goes on to its menus: followed to the end' ($null -eq $script:RaceExit -and ($script:Logged -join ' | ') -match 'done, the game is on its way to the menus \(state 0x1D\)') ($script:Logged -join ' | ')

Game 0x27 0x27 6 1 1 3
Request-RaceExit $h $t0
Check 'Championship: the stage number is set to the number of stages (3), as the game''s own Quit does' ([MockRace]::I(0x9DB820) -eq 3 -and (Flag) -eq 1) "stage $([MockRace]::I(0x9DB820)), flag $(Flag)"
Check 'and the leader''s race position is left alone while the race still moves' ([MockRace]::I(0x9DD61C) -eq 1) "position $([MockRace]::I(0x9DD61C))"
Steps 0.02 0.04 { param($t) }
Check '(the request not taken yet: position still 1)' ([MockRace]::I(0x9DD61C) -eq 1) "position $([MockRace]::I(0x9DD61C))"
Steps 0.06 3 { param($t) if ($t -ge 0.06 -and (Flag)) { [MockRace]::PutI(0x9DB4F4, 0); [MockRace]::PutI(0x7ECE14, 0x1B) }
                            if ($t -ge 0.1) { [MockRace]::PutI(0x7ECE10, 0x1B); [MockRace]::PutI(0x7ECE14, 0x2A) }; if ($t -ge 0.12) { [MockRace]::PutI(0x7ECE10, 0x2A) }
                            if ($t -ge 0.7) { [MockRace]::PutI(0x7ECE10, 0x1D); [MockRace]::PutI(0x7ECE14, 0x1D) } }
Check 'once the race has stopped the leader reads 2, so the end of the championship goes to the menus, not the bonus stage' ([MockRace]::I(0x9DD61C) -eq 2 -and ($script:Logged -join ' | ') -match 'bonus stage is skipped') ($script:Logged -join ' | ')

Game 0x27 0x27 6 4 0 3
Request-RaceExit $h $t0
Steps 0.02 3 { param($t) if ($t -ge 0.04 -and (Flag)) { [MockRace]::PutI(0x9DB4F4, 0); [MockRace]::PutI(0x7ECE14, 0x1B) }; if ($t -ge 0.3) { [MockRace]::PutI(0x7ECE10, 0x1D); [MockRace]::PutI(0x7ECE14, 0x1D) } }
Check 'Championship, not leading: the position is not touched' ([MockRace]::I(0x9DD61C) -eq 4) "position $([MockRace]::I(0x9DD61C))"

foreach ($c in @(@(0x27, 0x27, 2, 'the attract demo (mode 2)'), @(0x27, 0x27, 3, '"Press START" (mode 3)'), @(0x1C, 0x1C, 5, 'the results / name entry (state 0x1C)'), @(0x1F, 0x1F, 5, 'a track loading (state 0x1F)'),
                 @(6, 6, 2, 'the attract race loading (state 6)'), @(0x27, 0x1B, 5, 'a race already ending (next state 0x1B)'), @(0x28, 0x28, 5, 'the pause state 0x28'))) {
    Game $c[0] $c[1] $c[2]
    Request-RaceExit $h $t0
    Check "refused in $($c[3]): nothing written" ([MockRace]::Writes.Count -eq 0 -and $null -eq $script:RaceExit -and ($script:Logged -join ' ') -match 'no race is running') ($script:Logged -join ' | ')
}
Game 0x27 0x27 6; [MockRace]::PutI(0xB2A850, 0)
Request-RaceExit $h $t0
Check 'Championship whose number of stages cannot be read: refused, nothing written' ([MockRace]::Writes.Count -eq 0 -and ($script:Logged -join ' ') -match 'could not be read') ($script:Logged -join ' | ')

Game 0x27 0x27 6 1 1 3; $fadeWas = [MockRace]::Read($h, 0x9DB490, 0x1C)
Request-RaceExit $h $t0
Steps 0.02 1.9 { param($t) }
Check 'a request the game does not take: still waiting at 1.9 s' ((Flag) -eq 1 -and $script:RaceExit) "flag $(Flag)"
Steps 2.0 2.1 { param($t) }
Check 'withdrawn at 2 s: flag 0, stage number and fade as they were' ((Flag) -eq 0 -and [MockRace]::I(0x9DB820) -eq 1 -and (Same ([MockRace]::Read($h, 0x9DB490, 0x1C)) $fadeWas) -and $null -eq $script:RaceExit -and ($script:Logged -join ' ') -match 'did not take the request within 2 s') ($script:Logged -join ' | ')

Game 0x27 0x27 5; $fadeWas = [MockRace]::Read($h, 0x9DB490, 0x1C)
Request-RaceExit $h $t0
Steps 0.02 1 { param($t) if ($t -ge 0.3) { [MockRace]::PutI(0x7ECE10, 0x1C); [MockRace]::PutI(0x7ECE14, 0x1C) } }   # the race finished (results) before the update read the flag
Check 'the race ends another way while the flag waits: withdrawn, flag 0, fade as it was' ((Flag) -eq 0 -and (Same ([MockRace]::Read($h, 0x9DB490, 0x1C)) $fadeWas) -and $null -eq $script:RaceExit -and ($script:Logged -join ' ') -match 'ended another way') ($script:Logged -join ' | ')

Game 0x27 0x27 6 1 1 3; $fadeWas = [MockRace]::Read($h, 0x9DB490, 0x1C); [MockRace]::FlipAfter = 1; [MockRace]::FlipTo = 0x1F
Request-RaceExit $h $t0
Check 'the state changes between the check and the flag (a load begins): no flag, stage number and fade put back' ((Flag) -eq 0 -and [MockRace]::I(0x9DB820) -eq 1 -and (Same ([MockRace]::Read($h, 0x9DB490, 0x1C)) $fadeWas) -and $null -eq $script:RaceExit -and ($script:Logged -join ' ') -match 'race ended just then') ($script:Logged -join ' | ')

Game 0x27 0x27 7
Request-RaceExit $h $t0
Steps 0.02 6 { param($t) if ($t -ge 0.04 -and (Flag)) { [MockRace]::PutI(0x9DB4F4, 0); [MockRace]::PutI(0x7ECE10, 0x2A); [MockRace]::PutI(0x7ECE14, 0x2A) }
                            if ([MockRace]::I(0x9DB498) -eq 1 -and $t -gt 1) { [MockRace]::PutI(0x7ECE10, 0x1D); [MockRace]::PutI(0x7ECE14, 0x1D) } }   # the teardown waits while the fade runs
Check 'Classic, a fade that never finishes: let go after 4 s, the game goes on' (($script:Logged -join ' ') -match 'fade to black did not finish' -and ($script:Logged -join ' ') -match 'done' -and $null -eq $script:RaceExit) ($script:Logged -join ' | ')

"START CHECKS: $script:pass passed, $script:fail failed"
'@
$dir = Join-Path $env:TEMP 'sr3startmock'; Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue; [void](New-Item -ItemType Directory -Path $dir)
$tmp = Join-Path $dir 'patch_cut.ps1'
Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
try { & $tmp 'Daytona' -ProfilesFile (Join-Path $PSScriptRoot '..\profiles.yaml') } finally { Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue }
