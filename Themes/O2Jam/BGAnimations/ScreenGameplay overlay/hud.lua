-- HUD: info card, record cells and energy, score, judgment table, rank, and every hit effect.
-- Hand-lettered comic fonts (white face, ink outline) are tinted with diffuse; the outline stays dark.

local k = O2.k
local W, H = SCREEN_WIDTH, SCREEN_HEIGHT
local c = O2.colors
local laneW = O2.laneWidth
local columns = 7

local state = O2State.new()
local shownScore = 0
local particleCount = 64
local nextParticle = 0

local song = GAMESTATE:GetCurrentSong()
local steps = GAMESTATE:GetCurrentSteps(PLAYER_1)

local function text(name, font, x, y, color, zoom, halign, extra)
    return LoadFont(font) .. {
        Name = name,
        InitCommand = function(self)
            self:xy(x, y):halign(halign or 0):valign(0):zoom(zoom or 1):diffuse(color)
            if extra then extra(self) end
        end,
    }
end

local function sprite(name, tex, x, y, w, h, extra)
    return Def.Sprite {
        Name = name,
        Texture = O2.gfx(tex),
        InitCommand = function(self)
            self:halign(0):valign(0):xy(x, y)
            if w then self:zoomto(w, h) end
            if extra then extra(self) end
        end,
    }
end

local function pickColor(name) return c[name] or c.cream end

local function accuracyText()
    local pct = O2State.accuracy(state) * 100
    if pct >= 99.95 then return "100%" end
    return string.format("%.1f%%", pct)
end

local t = Def.ActorFrame {
    Name = "O2HUD",
    OnCommand = function(self)
        state = O2State.new()
        shownScore = 0
        self:playcommand("Refresh")
        self:SetUpdateFunction(function(frame) frame:playcommand("Tick") end)
    end,
    DoneLoadingNextSongMessageCommand = function(self)
        state = O2State.new()
        shownScore = 0
        self:playcommand("Refresh")
    end,

    ----------------------------------------------------------------------------------------
    -- judgments
    ----------------------------------------------------------------------------------------
    JudgmentMessageCommand = function(self, param)
        if param.FromReplay or param.Type == "Mine" then
            return
        end
        if param.HoldNoteScore then
            O2State.applyHold(state, param.HoldNoteScore == "HoldNoteScore_Held")
            self:playcommand("Refresh")
            return
        end
        local judge = O2.judge[param.TapNoteScore]
        if not judge then
            return
        end
        local events = O2State.apply(state, judge.kind)
        self:playcommand("Refresh")
        self:playcommand("Hit", { judge = judge, lane = (param.FirstTrack or 3) + 1, events = events })
    end,

    RefreshCommand = function(self)
        local n = self:GetChildren()
        n.Score:settext(string.format("%07d", math.floor(shownScore)))
        n.Cool:settext(tostring(state.cool))
        n.Good:settext(tostring(state.good))
        n.Bad:settext(tostring(state.bad))
        n.Miss:settext(tostring(state.miss))
        local total = math.max(state.tapNotes, 1)
        n.CoolBar:cropright(1 - state.cool / total)
        n.GoodBar:cropright(1 - state.good / total)
        n.BadBar:cropright(1 - state.bad / total)
        n.MissBar:cropright(1 - state.miss / total)
        n.MaxCombo:settext(tostring(state.maxCombo))
        n.Accuracy:settext(accuracyText())
        n.Rank:settext(O2State.rank(state))
    end,

    TickCommand = function(self)
        local n = self:GetChildren()
        local screen = SCREENMAN:GetTopScreen()
        local position = GAMESTATE:GetPlayerState():GetSongPosition()
        local seconds = position:GetMusicSeconds()
        if song then
            local length = song:MusicLengthSeconds()
            if length > 0 then
                n.ProgressFill:cropright(1 - clamp(seconds / length, 0, 1))
                n.Clock:settext(O2State.clock(seconds) .. "/" .. O2State.clock(length))
            end
        end
        if screen and screen.GetLifeMeter then
            local life = screen:GetLifeMeter(PLAYER_1)
            if life then
                n.EnergyFill:croptop(1 - clamp(life:GetLife(), 0, 1))
            end
        end
        -- the score rolls up to its true value
        if shownScore < state.score then
            shownScore = math.min(state.score, shownScore + math.max(3, (state.score - shownScore) * 0.25))
            n.Score:settext(string.format("%07d", math.floor(shownScore)))
        end
        -- the divider pulses on the beat
        local beat = position:GetSongBeat()
        local frac = beat - math.floor(beat)
        n.Pulse:diffusealpha(0.45 * (1 - frac) * (1 - frac))
    end,

    ----------------------------------------------------------------------------------------
    -- the effects of one hit
    ----------------------------------------------------------------------------------------
    HitCommand = function(self, p)
        local n = self:GetChildren()
        local judge, lane, events = p.judge, p.lane, p.events
        local color = pickColor(judge.color)
        local x = O2.laneCenterX(lane)
        local y = O2.receptorY

        -- light beam up the lane, a star flash on the key, and a ring
        if judge.beam > 0 then
            local beam = n["Beam" .. lane]
            beam:stoptweening():croptop(0.55):diffuse(judge.kind == "cool" and c.cream or color):diffusealpha(judge.beam * 0.85)
            beam:decelerate(0.12):croptop(0):accelerate(0.28):diffusealpha(0)
            local star = n["Star" .. lane]
            star:stoptweening():diffuse(color):diffusealpha(1):zoom(laneW / 192 * 1.1)
            star:linear(0.2):zoom(laneW / 192 * (judge.kind == "cool" and 2.4 or 1.8)):diffusealpha(0)
            local ring = n["Ring" .. lane]
            ring:stoptweening():diffuse(color):diffusealpha(1):zoom(laneW / 96 * 0.9)
            ring:linear(0.24):zoom(laneW / 96 * 2.6):diffusealpha(0)
        end

        -- confetti
        for i = 1, judge.sparks do
            nextParticle = nextParticle % particleCount + 1
            local spark = n["P" .. nextParticle]
            local angle = (-math.pi * 0.95) + math.random() * math.pi * 0.9
            local speed = (judge.kind == "cool" and 170 or 100) * k * (0.5 + math.random() * 0.9)
            local size = math.random(12, 22) * k
            local tint = color
            if judge.kind == "cool" then
                local r = math.random(3)
                tint = r == 1 and c.cream or (r == 2 and c.mustard or c.teal)
            end
            spark:stoptweening():xy(x, y):zoomto(size, size):rotationz(math.random(0, 360)):diffuse(tint):diffusealpha(1)
            spark:decelerate(0.55):xy(x + math.cos(angle) * speed, y + math.sin(angle) * speed + 30 * k)
            spark:rotationz(math.random(-200, 200)):diffusealpha(0)
        end

        -- the judgment, in a speech bubble
        local word, bubble = n.Judgment, n.JudgmentBubble
        local bubbleColor = judge.kind == "cool" and c.teal or color
        bubble:stoptweening():diffuse(bubbleColor):diffusealpha(1):x(O2.fieldCenterX):y(O2.judgmentY - 4 * k)
        bubble:zoom(0.8)
        word:stoptweening():stopeffect():settext(judge.label):diffuse(c.cream):diffusealpha(1)
        word:x(O2.fieldCenterX):y(O2.judgmentY - 14 * k):zoom(0.95)
        local shake = judge.kind == "miss"
        if shake then
            n.Flash:stoptweening():diffuse(c.red):diffusealpha(0.25):linear(0.25):diffusealpha(0)
            for _, a in ipairs({ bubble, word }) do
                a:linear(0.04):zoom(a == bubble and 0.7 or 0.8):addx(-9 * k):linear(0.04):addx(18 * k)
                a:linear(0.04):addx(-9 * k):sleep(0.25):linear(0.18):diffusealpha(0):addy(24 * k)
            end
        else
            bubble:linear(0.05):zoom(0.68):sleep(0.25):linear(0.4):diffusealpha(0):addy(-28 * k)
            word:linear(0.05):zoom(0.8):sleep(0.25):linear(0.4):diffusealpha(0):addy(-28 * k)
        end

        -- the combo number
        local number, label = n.ComboNumber, n.ComboLabel
        if judge.kind == "cool" or judge.kind == "good" then
            local tier = O2State.comboTier(state.combo)
            number:stoptweening():settext(tostring(state.combo)):visible(true)
            number:x(O2.fieldCenterX):y(O2.comboNumberY)
            if tier.name == "rainbow" then
                number:diffuseshift():effectcolor1(c.coral):effectcolor2(c.mustard):effectperiod(0.4)
            else
                number:stopeffect():diffuse(pickColor(tier.name))
            end
            number:zoom(tier.zoom * 0.5 + 0.35):linear(0.06):zoom(tier.zoom * 0.5)
            label:visible(state.combo >= 2):diffuse(tier.name == "rainbow" and c.cream or pickColor(tier.name))
        else
            if state.tapNotes > 0 and number:GetVisible() then
                number:stoptweening():stopeffect():diffuse(c.red):linear(0.05):x(O2.fieldCenterX - 9 * k)
                number:linear(0.05):x(O2.fieldCenterX + 9 * k):linear(0.05):x(O2.fieldCenterX):linear(0.15):diffusealpha(0)
                number:queuecommand("HideCombo")
            end
            label:visible(false)
        end

        -- every 25 combo deserves a small show, kept high so the falling notes stay readable
        if events.milestone then
            self:playcommand("Milestone", { combo = events.milestone })
        end
    end,

    MilestoneCommand = function(self, p)
        local n = self:GetChildren()
        local big = p.combo % 100 == 0
        local banner, burst = n.Banner, n.BannerBurst
        local tier = O2State.comboTier(p.combo)
        local color = tier.name == "rainbow" and c.cream or pickColor(tier.name)
        burst:stoptweening():y(O2.bannerY):diffuse(color):diffusealpha(0.7):zoom(0.45):rotationz(math.random(-12, 12))
        burst:linear(0.12):zoom(big and 1.0 or 0.85):sleep(0.3):linear(0.4):diffusealpha(0):addy(-20 * k)
        local word = n.BannerWord
        banner:stoptweening():y(O2.bannerY):settext(tostring(p.combo)):diffuse(c.cream):diffusealpha(1):zoom(0.7)
        banner:linear(0.07):zoom(0.55):sleep(0.5):linear(0.5):diffusealpha(0):addy(-24 * k)
        word:stoptweening():y(O2.bannerY + 46 * k):diffuse(c.cream):diffusealpha(1):zoom(0.6)
        word:linear(0.07):zoom(0.5):sleep(0.5):linear(0.5):diffusealpha(0):addy(-24 * k)
        for i = 1, 16 do
            nextParticle = nextParticle % particleCount + 1
            local spark = n["P" .. nextParticle]
            local angle = math.random() * math.pi * 2
            local speed = (70 + math.random() * 80) * k
            local size = math.random(12, 20) * k
            spark:stoptweening():xy(O2.fieldCenterX, O2.bannerY):zoomto(size, size):rotationz(math.random(0, 360))
            spark:diffuse(math.random() < 0.5 and color or c.cream):diffusealpha(1)
            spark:decelerate(0.7):xy(O2.fieldCenterX + math.cos(angle) * speed, O2.bannerY + math.sin(angle) * speed)
            spark:rotationz(math.random(-240, 240)):diffusealpha(0)
        end
    end,

    HideComboCommand = function(self)
        self:GetChildren().ComboNumber:visible(false):diffusealpha(1)
    end,
}

--------------------------------------------------------------------------------------------
-- layout
--------------------------------------------------------------------------------------------

-- info card
local info = O2.info
t[#t + 1] = text("NowPlaying", O2.fonts.plain, info.x + 18 * k, info.y + 8 * k, c.coral, 0.8, 0, function(self)
    self:settext("Now playing")
end)
local title = song and song:GetDisplayMainTitle() or ""
local artist = song and song:GetDisplayArtist() or ""
local songDir = song and song:GetSongDir() or ""

-- The engine's CJK font misses many characters, so video2sm pre-renders title.png / artist.png
-- in the comic lettering; fall back to text when they are absent.
local function cardText(name, file, x, y, color, zoom, fallbackText, maxwidth)
    if songDir ~= "" and FILEMAN:DoesFileExist(songDir .. file) then
        return Def.Sprite {
            Name = name,
            Texture = songDir .. file,
            InitCommand = function(self)
                self:halign(0):valign(0):xy(x, y):diffuse(color)
            end,
        }
    end
    return LoadFont(O2.fonts.cjk) .. {
        Name = name,
        InitCommand = function(self)
            self:xy(x, y):halign(0):valign(0):zoom(zoom):maxwidth(maxwidth)
            self:settext(fallbackText):diffuse(color)
        end,
    }
end
t[#t + 1] = cardText("Title", "title.png", info.x + 18 * k, info.y + 28 * k, c.cream, 1, title, 300 * k)
t[#t + 1] = cardText("Artist", "artist.png", info.x + 18 * k, info.y + 64 * k, c.mint, 0.75, artist, 380 * k)
local difficulty = steps and steps:GetDifficulty() or "Difficulty_Easy"
local diffName = steps and ToEnumShortString(difficulty):upper() or ""
t[#t + 1] = sprite("Badge", "badge", info.x + 330 * k, info.y + 12 * k, 132 * k, 42 * k, function(self)
    self:diffuse(c[O2.difficultyColors[difficulty] or "teal"])
end)
t[#t + 1] = text("DifficultyName", O2.fonts.plain, info.x + 396 * k, info.y + 19 * k, c.ink, 0.85, 0.5, function(self)
    self:settext(diffName)
    self:maxwidth(120 * k)
end)
t[#t + 1] = text("Bpm", O2.fonts.plain, info.x + 468 * k, info.y + 62 * k, c.mustard, 0.9, 1, function(self)
    local bpm = song and song:GetDisplayBpms()[2] or 0
    self:settext(string.format("%d bpm", math.floor(bpm + 0.5)))
end)

-- the energy column
t[#t + 1] = sprite("EnergyBack", "energy_back", O2.energyX - 12 * k, 30 * k, 24 * k, 540 * k)
t[#t + 1] = sprite("EnergyFill", "energy_fill", O2.energyX - 9 * k, 36 * k, 18 * k, 528 * k)

-- the divider's beat pulse; drawn above the bottom bar, so it stops where the lanes do
t[#t + 1] = sprite("Pulse", "strip", O2.stripX, 0, 24 * k, H, function(self)
    self:blend("BlendMode_Add"):diffusealpha(0):cropbottom(1 - O2.regionBottom / H)
end)

-- judgment table
local stats = O2.stats
t[#t + 1] = text("StatsHeader", O2.fonts.plain, stats.x + 18 * k, stats.y + 10 * k, c.mustard, 0.85, 0, function(self)
    self:settext("Judgment")
end)
local rows = {
    { "Cool", "Cool", "teal" },
    { "Good", "Good", "mint" },
    { "Bad", "Bad", "orange" },
    { "Miss", "Miss", "red" },
}
for i, row in ipairs(rows) do
    local y = stats.y + 40 * k + (i - 1) * 33 * k
    local color = c[row[3]]
    t[#t + 1] = text(row[2] .. "Label", O2.fonts.plain, stats.x + 18 * k, y - 4 * k, color, 0.95, 0, function(self)
        self:settext(row[1])
    end)
    t[#t + 1] = sprite(row[2] .. "BarBack", "stat_back", stats.x + 114 * k, y + 3 * k, 210 * k, 15 * k)
    t[#t + 1] = sprite(row[2] .. "Bar", "stat_fill", stats.x + 114 * k, y + 3 * k, 210 * k, 15 * k, function(self)
        self:diffuse(color):cropright(1)
    end)
    t[#t + 1] = text(row[2], O2.fonts.plain, stats.x + stats.w - 18 * k, y - 4 * k, c.cream, 0.95, 1)
end
local footerY = stats.y + stats.h - 38 * k
t[#t + 1] = text("MaxLabel", O2.fonts.plain, stats.x + 18 * k, footerY, c.coral, 0.85, 0, function(self)
    self:settext("Max combo")
end)
t[#t + 1] = text("MaxCombo", O2.fonts.plain, stats.x + 204 * k, footerY, c.cream, 0.95, 0)

-- bottom bar
t[#t + 1] = text("ScoreLabel", O2.fonts.plain, 24 * k, 628 * k, c.teal, 0.8, 0, function(self) self:settext("Score") end)
t[#t + 1] = text("Score", O2.fonts.bold, 288 * k, 652 * k, c.cream, 0.6, 1)
t[#t + 1] = text("TimeLabel", O2.fonts.plain, 312 * k, 628 * k, c.mustard, 0.8, 0, function(self) self:settext("Stage") end)
t[#t + 1] = text("Clock", O2.fonts.plain, 642 * k, 628 * k, c.cream, 0.8, 1)
t[#t + 1] = sprite("ProgressBack", "progress_back", 309 * k, 672 * k, 336 * k, 18 * k)
t[#t + 1] = sprite("ProgressFill", "progress_fill", 309 * k, 672 * k, 336 * k, 18 * k, function(self)
    self:cropright(1)
end)
t[#t + 1] = text("AccLabel", O2.fonts.plain, 666 * k, 628 * k, c.coral, 0.8, 0, function(self) self:settext("Accuracy") end)
t[#t + 1] = text("Accuracy", O2.fonts.bold, 780 * k, 652 * k, c.cream, 0.6, 1, function(self) self:maxwidth(120 * k) end)
t[#t + 1] = sprite("RankRing", "grade_ring", 861 * k, 630 * k, 90 * k, 90 * k)
t[#t + 1] = text("Rank", O2.fonts.bold, 906 * k, 662 * k, c.mustard, 0.85, 0.5, function(self) self:valign(0.5) end)

-- hit effects: a halftone beam, a burst and a ring per lane, a pool of confetti, the bubble and the banners
for lane = 1, columns do
    t[#t + 1] = Def.Sprite {
        Name = "Beam" .. lane,
        Texture = O2.gfx("beam"),
        InitCommand = function(self)
            self:halign(0.5):valign(1):xy(O2.laneCenterX(lane), O2.receptorY + 12 * k)
            self:zoomto(laneW, 360 * k):diffusealpha(0)
        end,
    }
    t[#t + 1] = Def.Sprite {
        Name = "Star" .. lane,
        Texture = O2.gfx("burst"),
        InitCommand = function(self)
            self:xy(O2.laneCenterX(lane), O2.receptorY):diffusealpha(0)
        end,
    }
    t[#t + 1] = Def.Sprite {
        Name = "Ring" .. lane,
        Texture = O2.gfx("ring"),
        InitCommand = function(self)
            self:xy(O2.laneCenterX(lane), O2.receptorY):diffusealpha(0)
        end,
    }
end
local confetti = { "dot", "star", "chip" }
for i = 1, particleCount do
    t[#t + 1] = Def.Sprite {
        Name = "P" .. i,
        Texture = O2.gfx(confetti[i % 3 + 1]),
        InitCommand = function(self) self:diffusealpha(0) end,
    }
end
t[#t + 1] = Def.Quad {
    Name = "Flash",
    InitCommand = function(self)
        self:halign(0):valign(0):xy(O2.fieldLeft, 0):zoomto(7 * laneW, O2.regionBottom):diffusealpha(0)
    end,
}
t[#t + 1] = Def.Sprite {
    Name = "BannerBurst",
    Texture = O2.gfx("burst"),
    InitCommand = function(self)
        self:xy(O2.fieldCenterX, O2.bannerY):diffusealpha(0)
    end,
}
t[#t + 1] = text("Banner", O2.fonts.poster, O2.fieldCenterX, O2.bannerY, c.cream, 0.9, 0.5, function(self)
    self:valign(0.5):diffusealpha(0)
end)
t[#t + 1] = text("BannerWord", O2.fonts.bold, O2.fieldCenterX, O2.bannerY + 74 * k, c.cream, 0.8, 0.5, function(self)
    self:valign(0.5):settext("COMBO!"):diffusealpha(0)
end)
t[#t + 1] = text("ComboLabel", O2.fonts.plain, O2.fieldCenterX, O2.comboLabelY, c.cream, 0.9, 0.5, function(self)
    self:settext("combo"):visible(false)
end)
t[#t + 1] = text("ComboNumber", O2.fonts.bold, O2.fieldCenterX, O2.comboNumberY, c.cream, 1, 0.5, function(self)
    self:visible(false)
end)
t[#t + 1] = Def.Sprite {
    Name = "JudgmentBubble",
    Texture = O2.gfx("bubble"),
    InitCommand = function(self)
        self:xy(O2.fieldCenterX, O2.judgmentY):diffusealpha(0)
    end,
}
t[#t + 1] = text("Judgment", O2.fonts.bold, O2.fieldCenterX, O2.judgmentY, c.cream, 0.9, 0.5, function(self)
    self:valign(0.5):diffusealpha(0)
end)

-- paper grain over everything, and darkened corners
t[#t + 1] = Def.Sprite {
    Texture = O2.gfx("grain"),
    InitCommand = function(self)
        self:halign(0):valign(0):xy(0, 0):zoomto(W, H):texturewrapping(true)
        self:customtexturerect(0, 0, W / (256 * k), H / (256 * k))
    end,
}
t[#t + 1] = Def.Sprite {
    Texture = O2.gfx("vignette"),
    InitCommand = function(self)
        self:halign(0):valign(0):xy(0, 0):zoomto(W, H):diffusealpha(0.7)
    end,
}

return t
