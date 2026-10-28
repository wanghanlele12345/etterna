-- O2Jam theme: layout constants and palette of the hand-inked "record shop" look. The screen is
-- 960x720 (4:3); everything below is in that space, multiplied by k when the window is another size.
-- Values here must agree with [ScreenGameplay]/[Player] in metrics.ini.

O2 = {}

local k = SCREEN_HEIGHT / 720
O2.k = k

-- warm, muted flats under thick near-black ink
O2.colors = {
    ink = color("#1d1424"),
    bg0 = color("#281f3a"),
    bg1 = color("#3a2d52"),
    bg2 = color("#503f6c"),
    cream = color("#f4ead2"),
    mustard = color("#f0b840"),
    coral = color("#e8758a"),
    teal = color("#5fb4c9"),
    mint = color("#8fd19e"),
    orange = color("#ef8a4b"),
    red = color("#d9544d"),
    lav = color("#a79ad6"),
    gray = color("#9d90b8"),
}
-- the combo tiers in O2State are named after the old palette; map them onto the new one
O2.colors.white = O2.colors.cream
O2.colors.cyan = O2.colors.teal
O2.colors.yellow = O2.colors.mustard
O2.colors.magenta = O2.colors.coral
O2.colors.green = O2.colors.mint

-- plain: small labels; bold: numbers and words; poster: banners
O2.fonts = { plain = "Marker", bold = "Scrawl", poster = "Poster", cjk = "_chinese 24px" }

-- the lanes: 48px each, the 64px noteskin columns drawn at zoom 0.75
O2.laneWidth = 48 * k
O2.noteColumnWidth = 64
O2.playerZoom = O2.laneWidth / O2.noteColumnWidth
O2.fieldLeft = 30 * k
O2.fieldCenterX = O2.fieldLeft + 3.5 * O2.laneWidth
O2.receptorY = 570 * k
O2.regionBottom = 624 * k
O2.barHeight = SCREEN_HEIGHT - O2.regionBottom
O2.energyX = 402 * k -- centre of the power-cell / energy column
O2.stripX = 426 * k

-- the right column: info card, video window, judgment table
O2.info = { x = 462 * k, y = 12 * k, w = 486 * k, h = 96 * k }
O2.video = { x = 465 * k, y = 123 * k, w = 480 * k, h = 270 * k }
O2.stats = { x = 462 * k, y = 408 * k, w = 486 * k, h = 204 * k }

-- where in the lanes things appear (world y)
O2.comboLabelY = 14 * k
O2.comboNumberY = 44 * k
O2.judgmentY = 178 * k
O2.bannerY = 96 * k -- milestone banners sit above the combo

-- lane colours: the noteskin's white keys are teal, blue keys coral, the thumb key mustard
local laneColorNames = { "teal", "coral", "teal", "mustard", "teal", "coral", "teal" }
function O2.laneColorName(lane)
    return laneColorNames[lane] or "teal"
end
function O2.laneColor(lane)
    return O2.colors[O2.laneColorName(lane)]
end
function O2.laneCenterX(lane)
    return O2.fieldLeft + (lane - 0.5) * O2.laneWidth
end

-- world coordinates to the zoomed player's local space (kept for any player-relative actor)
function O2.toPlayerX(x) return (x - O2.fieldCenterX) / O2.playerZoom end
function O2.toPlayerY(y) return (y - SCREEN_CENTER_Y) / O2.playerZoom end

-- zoom/x/y that put the song background's video exactly inside O2.video. The background is a
-- 16:9 picture letterboxed on the screen, so it is as wide as the screen, centred.
function O2.videoTransform()
    local z = O2.video.w / SCREEN_WIDTH
    local cx = O2.video.x + O2.video.w / 2
    local cy = O2.video.y + O2.video.h / 2
    return z, cx - SCREEN_CENTER_X * z, cy - SCREEN_CENTER_Y * z
end

-- Etterna's five windows collapse onto four judgments.
O2.judge = {
    TapNoteScore_W1 = { kind = "cool", label = "COOL", color = "teal", beam = 0.95, sparks = 12 },
    TapNoteScore_W2 = { kind = "cool", label = "COOL", color = "teal", beam = 0.95, sparks = 12 },
    TapNoteScore_W3 = { kind = "good", label = "GOOD", color = "mint", beam = 0.65, sparks = 7 },
    TapNoteScore_W4 = { kind = "good", label = "GOOD", color = "mint", beam = 0.65, sparks = 7 },
    TapNoteScore_W5 = { kind = "bad", label = "BAD", color = "orange", beam = 0.4, sparks = 4 },
    TapNoteScore_Miss = { kind = "miss", label = "MISS", color = "red", beam = 0, sparks = 0 },
}

O2.difficultyColors = {
    Difficulty_Beginner = "teal",
    Difficulty_Easy = "mint",
    Difficulty_Medium = "mustard",
    Difficulty_Hard = "orange",
    Difficulty_Challenge = "coral",
    Difficulty_Edit = "gray",
}

function O2.gfx(name)
    return THEME:GetPathG("", "ink/" .. name)
end
