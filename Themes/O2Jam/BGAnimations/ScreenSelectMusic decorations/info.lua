-- Beside the crate: who made the record on top, its title, stars, the difficulties to pick from
-- and its facts; hints for the keys along the bottom.
-- Up / Down pick the difficulty; the wheel's own input handles left / right / Enter / Esc.
local k = O2.k
local c = O2.colors

local column = 575 * k
local maxChips = 5
local chipStep = 44 * k

local song, chartList = nil, {}

local t = Def.ActorFrame { Name = "SelectInfo" }

local function text(name, font, x, y, color, zoom, halign, extra)
    return LoadFont(font) .. {
        Name = name,
        InitCommand = function(self)
            self:xy(x, y):halign(halign or 0):valign(0):zoom(zoom or 1):diffuse(color)
            if extra then extra(self) end
        end,
    }
end

local function clock(seconds)
    seconds = math.floor(seconds + 0.5)
    return string.format("%d:%02d", math.floor(seconds / 60), seconds % 60)
end

-- a title / artist picture made by video2sm when it exists (the engine font lacks many CJK characters)
local function cardLine(name, file, x, y, zoom, fallbackZoom, color)
    return Def.ActorFrame {
        Name = name,
        InitCommand = function(self) self:xy(x, y) end,
        Def.Sprite {
            Name = "Image",
            InitCommand = function(self) self:halign(0):valign(0):zoom(zoom):diffuse(color) end,
        },
        LoadFont(O2.fonts.cjk) .. {
            Name = "Text",
            InitCommand = function(self)
                self:halign(0):valign(0):zoom(fallbackZoom):maxwidth(340 * k / fallbackZoom):diffuse(color)
            end,
        },
        SetCommand = function(self, params)
            local img, txt = self:GetChild("Image"), self:GetChild("Text")
            local dir = params.song and params.song:GetSongDir() or ""
            if dir ~= "" and FILEMAN:DoesFileExist(dir .. file) then
                img:Load(dir .. file)
                img:visible(true)
                txt:visible(false)
            else
                img:visible(false)
                txt:visible(params.song ~= nil)
                if params.song then
                    txt:settext(file == "title.png" and params.song:GetDisplayMainTitle() or params.song:GetDisplayArtist())
                end
            end
        end,
    }
end

local function changeSteps(delta)
    local steps = GAMESTATE:GetCurrentSteps()
    if not song or #chartList == 0 then return end
    local index = 1
    for i, chart in ipairs(chartList) do
        if chart == steps then index = i end
    end
    local target = clamp(index + delta, 1, #chartList)
    if target == index then return end
    local picked = chartList[target]
    GAMESTATE:SetPreferredDifficulty(PLAYER_1, picked:GetDifficulty())
    GAMESTATE:SetCurrentSteps(PLAYER_1, picked)
    MESSAGEMAN:Broadcast("ChangedSteps", { steps = picked })
end

t.OnCommand = function(self)
    local screen = SCREENMAN:GetTopScreen()
    local name = screen:GetName()
    screen:AddInputCallback(function(event)
        if event.type ~= "InputEventType_FirstPress" then return end
        if not CONTEXTMAN:CheckContextSet(name, "Main1") then return end
        if event.button == "Up" or event.button == "MenuUp" then
            changeSteps(-1)
        elseif event.button == "Down" or event.button == "MenuDown" then
            changeSteps(1)
        end
    end)
end

local function show(self, params)
    song = params.song
    chartList = song and WHEELDATA:GetChartsMatchingFilter(song) or {}
    self:stoptweening():diffusealpha(1)
    self:GetChild("Detail"):stoptweening():diffusealpha(1)
    self:playcommand("Set", { song = song, steps = params.steps or GAMESTATE:GetCurrentSteps(), hovered = params.hovered })
end

t.WheelSettledMessageCommand = function(self, params)
    show(self, params)
    self:GetChild("Position"):settext(string.format("%d / %d", params.index or 0, params.maxIndex or 0))
end
t.ChangedStepsMessageCommand = function(self, params)
    self:playcommand("Set", { song = song, steps = params.steps })
end
t.WheelIndexChangedMessageCommand = function(self, params)
    self:GetChild("Position"):settext(string.format("%d / %d", params.index or 0, params.maxIndex or 0))
    self:GetChild("Detail"):stoptweening():linear(0.08):diffusealpha(0.5)
end

t[#t + 1] = text("Position", O2.fonts.plain, 928 * k, 22 * k, c.cream, 0.9, 1)

-- everything about the record on top
local detail = Def.ActorFrame {
    Name = "Detail",
    InitCommand = function(self) self:xy(column, 0) end,
    cardLine("Artist", "artist.png", 0, 92 * k, 1.2, 0.9, c.mint),
    cardLine("Title", "title.png", 0, 130 * k, 1.12, 1.0, c.cream),
    SetCommand = function(self, params)
        self:visible(params.song ~= nil)
    end,
}

for i = 1, 5 do
    detail[#detail + 1] = Def.Sprite {
        Name = "Star" .. i,
        Texture = O2.gfx("star"),
        InitCommand = function(self) self:halign(0):valign(0):xy((i - 1) * 42 * k, 196 * k):zoom(0.85) end,
    }
end

for i = 1, maxChips do
    local y = 252 * k + (i - 1) * chipStep
    detail[#detail + 1] = Def.ActorFrame {
        Name = "Chip" .. i,
        InitCommand = function(self) self:xy(0, y):visible(false) end,
        Def.Sprite {
            Name = "Pill",
            Texture = O2.gfx("diff_chip"),
            InitCommand = function(self) self:halign(0):valign(0) end,
        },
        text("Name", O2.fonts.plain, 20 * k, 8 * k, c.ink, 0.72, 0),
        text("Meter", O2.fonts.plain, 176 * k, 8 * k, c.ink, 0.72, 1),
        SetCommand = function(self, params)
            local chart = chartList[i]
            if not chart or not params.song then
                self:visible(false)
                return
            end
            local selected = chart == params.steps
            local color = c[O2.difficultyColors[chart:GetDifficulty()] or "teal"]
            self:visible(true):stoptweening():linear(0.1)
            self:x(selected and -14 * k or 0):zoom(selected and 1.08 or 1)
            self:GetChild("Pill"):diffuse(selected and color or { color[1] * 0.55, color[2] * 0.55, color[3] * 0.55, 0.9 })
            self:GetChild("Name"):settext(ToEnumShortString(chart:GetDifficulty()))
            self:GetChild("Meter"):settext(string.format("%.1f", chart:GetMSD(1, 1)))
        end,
    }
end

-- stars follow the level of the chosen chart
detail.SetCommand = function(self, params)
    self:visible(params.song ~= nil)
    local level = params.steps and params.steps:GetMSD(1, 1) or 0
    local lit = clamp(math.floor(level + 0.5), 1, 5)
    for i = 1, 5 do
        local star = self:GetChild("Star" .. i)
        if i <= lit then
            star:diffuse(c.mustard)
        else
            star:diffuse({ 0.25, 0.2, 0.28, 0.9 })
        end
    end
    local facts = self:GetChild("Facts")
    if params.song then
        local bpm = params.song:GetDisplayBpms()[2] or 0
        local lines = {
            string.format("%d bpm", math.floor(bpm + 0.5)),
            clock(params.song:MusicLengthSeconds()),
        }
        if params.steps then
            lines[#lines + 1] = string.format("%d notes", params.steps:GetRadarValues(PLAYER_1):GetValue("RadarCategory_Notes"))
        end
        facts:settext(table.concat(lines, "\n"))
    end
end
detail[#detail + 1] = text("Facts", O2.fonts.plain, 220 * k, 262 * k, c.mustard, 0.9, 0, function(self)
    self:skewx(-0.15):vertspacing(10)
end)
t[#t + 1] = detail

-- a pack is hovered instead of a record
t[#t + 1] = Def.ActorFrame {
    Name = "PackInfo",
    InitCommand = function(self) self:xy(column, 150 * k):visible(false) end,
    SetCommand = function(self, params)
        local pack = type(params.hovered) == "string" and params.hovered or ""
        self:visible(params.song == nil and pack ~= "")
        self:GetChild("Pack"):settext(pack)
        local count = pack ~= "" and WHEELDATA:GetFolderCount(pack) or 0
        self:GetChild("Count"):settext(string.format("%d songs", count))
    end,
    text("Pack", O2.fonts.bold, 0, 0, c.cream, 0.8, 0, function(self) self:maxwidth(340 * k / 0.8) end),
    text("Count", O2.fonts.plain, 0, 64 * k, c.mint, 1, 0),
    text("Open", O2.fonts.plain, 0, 110 * k, c.mustard, 0.9, 0, function(self)
        self:settext("press enter to open"):skewx(-0.15)
    end),
}

-- key hints along the bottom, each in a little round badge
local hints = {
    { "< >", "Browse", 40 },
    { "^ v", "Difficulty", 250 },
    { "Ent", "Play", 500 },
    { "Esc", "Back", 690 },
}
for _, hint in ipairs(hints) do
    local x = hint[3] * k
    t[#t + 1] = Def.Sprite {
        Texture = O2.gfx("dot"),
        InitCommand = function(self) self:halign(0):valign(0):xy(x - 4 * k, 658 * k):zoomto(48 * k, 48 * k):diffuse(c.lav) end,
    }
    t[#t + 1] = text(hint[2] .. "Key", O2.fonts.plain, x + 20 * k, 672 * k, c.ink, 0.62, 0.5, function(self)
        self:settext(hint[1])
    end)
    t[#t + 1] = text(hint[2], O2.fonts.plain, x + 52 * k, 668 * k, c.cream, 0.85, 0, function(self)
        self:settext(hint[2])
    end)
end

return t
