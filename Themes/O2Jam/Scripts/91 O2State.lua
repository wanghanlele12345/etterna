-- Score, combo and rank rules for the HUD. Pure data in, data out (no actors), so it
-- can be tested with plain luajit.

O2State = {}

local POINTS = { cool = 400, good = 200, bad = 50, miss = 0 }
local HOLD_POINTS = 200
local FEVER_LENGTH = 25 -- consecutive COOLs for one FEVER
local FEVER_BONUS = 1000
local COMBO_BONUS_CAP = 100 -- combo bonus grows to this many combo steps
local MILESTONE_EVERY = 25
local CELLS = 5

O2State.FEVER_LENGTH = FEVER_LENGTH
O2State.CELLS = CELLS
O2State.MILESTONE_EVERY = MILESTONE_EVERY

-- accuracy weight of each judgment, and the rank thresholds (share of the best possible)
local WEIGHT = { cool = 1.0, good = 0.6, bad = 0.2, miss = 0.0 }
local RANKS = { { 0.95, "S" }, { 0.85, "A" }, { 0.70, "B" }, { 0.55, "C" } }

function O2State.new()
    return {
        score = 0, cool = 0, good = 0, bad = 0, miss = 0,
        combo = 0, maxCombo = 0, streak = 0, fever = 0, tapNotes = 0,
    }
end

-- Apply one tap judgment ("cool" | "good" | "bad" | "miss"). Returns what just happened:
-- { milestone = combo reached a multiple of 25 or nil, fever = true when a FEVER completed }
function O2State.apply(state, kind)
    local events = {}
    state[kind] = state[kind] + 1
    state.tapNotes = state.tapNotes + 1
    local base = POINTS[kind]
    if kind == "cool" or kind == "good" then
        state.combo = state.combo + 1
        if state.combo > state.maxCombo then
            state.maxCombo = state.combo
        end
        base = base + math.min(state.combo, COMBO_BONUS_CAP) * 2
        if state.combo % MILESTONE_EVERY == 0 then
            events.milestone = state.combo
        end
    else
        state.combo = 0
    end
    if kind == "cool" then
        state.streak = state.streak + 1
        if state.streak % FEVER_LENGTH == 0 then
            state.fever = state.fever + 1
            base = base + FEVER_BONUS
            events.fever = true
        end
    else
        state.streak = 0
    end
    state.score = state.score + base
    return events
end

-- Apply a hold result: true when it was held to the end.
function O2State.applyHold(state, held)
    if held then
        state.score = state.score + HOLD_POINTS
    else
        state.streak = 0
    end
end

-- How many of the power cells are lit (one per FEVER_LENGTH / CELLS consecutive COOLs).
function O2State.litCells(state)
    local per = FEVER_LENGTH / CELLS
    return math.floor((state.streak % FEVER_LENGTH) / per)
end

-- Share of the best possible score for the notes judged so far (0..1).
function O2State.accuracy(state)
    if state.tapNotes == 0 then
        return 1.0
    end
    local got = state.cool * WEIGHT.cool + state.good * WEIGHT.good + state.bad * WEIGHT.bad
    return got / state.tapNotes
end

function O2State.rank(state)
    if state.tapNotes == 0 then
        return "-"
    end
    local accuracy = O2State.accuracy(state)
    for _, entry in ipairs(RANKS) do
        if accuracy >= entry[1] then
            return entry[2]
        end
    end
    return "D"
end

-- Visual tier of a combo: bigger numbers and hotter colours as it grows.
-- Returns { name, zoom, pop } where `pop` is how much the number jumps on each hit.
local TIERS = {
    { 200, "rainbow", 3 },
    { 100, "magenta", 3 },
    { 50, "orange", 2 },
    { 25, "yellow", 2 },
    { 10, "cyan", 2 },
    { 0, "white", 2 },
}
function O2State.comboTier(combo)
    for _, tier in ipairs(TIERS) do
        if combo >= tier[1] then
            return { name = tier[2], zoom = tier[3] }
        end
    end
    return { name = "white", zoom = 2 }
end

-- "1:05" style clock text.
function O2State.clock(seconds)
    seconds = math.max(0, math.floor(seconds))
    return string.format("%d:%02d", math.floor(seconds / 60), seconds % 60)
end
