-- Run: luajit tools/lua/test_state.lua   (from the theme directory)
dofile("Scripts/91 O2State.lua")
local failures = 0
local function check(name, ok)
    if not ok then failures = failures + 1 print("FAIL " .. name) end
end

local s = O2State.new()
for i = 1, 24 do O2State.apply(s, "cool") end
check("no fever before 25", s.fever == 0 and s.combo == 24)
local ev = O2State.apply(s, "cool")
check("25th cool is a milestone and a fever", ev.milestone == 25 and ev.fever == true and s.fever == 1)
check("fever bonus is scored", s.score > 25 * 400 + 1000)
check("miss resets combo and streak", (function() O2State.apply(s, "miss"); return s.combo == 0 and s.streak == 0 and s.maxCombo == 25 end)())
check("good keeps the combo but ends the fever streak", (function()
    local t = O2State.new(); O2State.apply(t, "cool"); O2State.apply(t, "good")
    return t.combo == 2 and t.streak == 0 end)())
check("bad breaks the combo", (function()
    local t = O2State.new(); O2State.apply(t, "cool"); O2State.apply(t, "bad"); return t.combo == 0 end)())
check("milestones every 25", (function()
    local t = O2State.new(); local got = {}
    for i = 1, 100 do local e = O2State.apply(t, "good"); if e.milestone then got[#got + 1] = e.milestone end end
    return #got == 4 and got[1] == 25 and got[4] == 100 end)())
check("lit cells follow the streak", (function()
    local t = O2State.new()
    for i = 1, 12 do O2State.apply(t, "cool") end
    return O2State.litCells(t) == 2 end)())
check("lit cells restart after a fever", (function()
    local t = O2State.new(); for i = 1, 26 do O2State.apply(t, "cool") end
    return O2State.litCells(t) == 0 end)())
check("accuracy of all cool is 1", (function()
    local t = O2State.new(); for i = 1, 10 do O2State.apply(t, "cool") end
    return O2State.accuracy(t) == 1.0 and O2State.rank(t) == "S" end)())
check("accuracy mixes weights", (function()
    local t = O2State.new(); O2State.apply(t, "cool"); O2State.apply(t, "good"); O2State.apply(t, "bad"); O2State.apply(t, "miss")
    return math.abs(O2State.accuracy(t) - (1 + 0.6 + 0.2) / 4) < 1e-9 end)())
check("rank thresholds", (function()
    local function rankFor(cool, miss)
        local t = O2State.new()
        for i = 1, cool do O2State.apply(t, "cool") end
        for i = 1, miss do O2State.apply(t, "miss") end
        return O2State.rank(t)
    end
    return rankFor(96, 4) == "S" and rankFor(90, 10) == "A" and rankFor(75, 25) == "B"
        and rankFor(60, 40) == "C" and rankFor(30, 70) == "D" end)())
check("rank before any note", O2State.rank(O2State.new()) == "-" and O2State.accuracy(O2State.new()) == 1.0)
check("combo tiers", O2State.comboTier(5).name == "white" and O2State.comboTier(10).name == "cyan"
    and O2State.comboTier(25).name == "yellow" and O2State.comboTier(60).name == "orange"
    and O2State.comboTier(100).name == "magenta" and O2State.comboTier(500).name == "rainbow")
check("tier zoom grows", O2State.comboTier(150).zoom >= O2State.comboTier(5).zoom)
check("hold scores", (function()
    local t = O2State.new(); O2State.applyHold(t, true)
    local after = t.score; O2State.apply(t, "cool"); O2State.applyHold(t, false)
    return after == 200 and t.streak == 0 end)())
check("clock", O2State.clock(65) == "1:05" and O2State.clock(-3) == "0:00" and O2State.clock(214.6) == "3:34")
if failures == 0 then print("all state tests passed") else os.exit(1) end
