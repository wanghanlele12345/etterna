-- The record crate seen from the front: the current sleeve stands at the front of a stack, the
-- records already flipped past recede behind it as slivers up and to the right, and the next one
-- is pulled up from the tray. Reuses Rebirth's MusicWheel (input, groups, sorting, selection);
-- only how the items look and where they stand is ours.
--
-- Frames are drawn in wheel order, so negative offsets (earlier records) are drawn first, which
-- is exactly the back of the stack; positive offsets (the next record) come up in front.
local k = O2.k
local c = O2.colors

local numWheelItems = 22
local ART = 240 -- the art window of a sleeve, in sleeve pixels
local SLEEVE_W, SLEEVE_H = 288, 300
local front = { x = 250 * k, y = 355 * k, zoom = 1.15 }
local stack = { dx = 13 * k, dy = -8.5 * k, shrink = 0.012, maxDepth = 9, dim = 0.08 }
local rise = 300 * k -- how far below the front the next record waits

local wheelIndex = nil -- index of the current record in the wheel's list, once known

-- where a sleeve stands for a given distance from the front (fractional while scrolling)
local function transformFrame(frame, offset)
    local count = #WHEELDATA:GetWheelItems()
    local depth = math.floor(-offset + 0.5)
    local shown
    if offset > 0 then
        shown = offset < 1 and count > 1
    else
        local behind = wheelIndex and (wheelIndex - 1) or (count - 1)
        shown = depth <= math.min(behind, stack.maxDepth)
    end
    frame:visible(shown)
    if not shown then return end

    if offset > 0 then
        local t = math.min(offset, 1)
        frame:xy(front.x - t * 30 * k, front.y + t * rise):zoom(front.zoom):rotationz(-8 * t)
        frame:diffuse({ 1, 1, 1, (1 - t) ^ 1.3 })
    else
        local d = -offset
        frame:xy(front.x + d * stack.dx, front.y + d * stack.dy)
        frame:zoom(front.zoom - d * stack.shrink):rotationz(0)
        local shade = math.max(0.45, 1 - stack.dim * d)
        frame:diffuse({ shade, shade, shade, 1 })
    end
end

-- a cover-cropped picture inside the sleeve's art window
local function setArt(art, path)
    if art.path == path then return end
    art.path = path
    local extension = (path and path:match("%.(%w+)$") or ""):lower()
    local isVideo = extension == "mp4" or extension == "avi" or extension == "mov" or extension == "mkv"
        or extension == "webm" or extension == "mpg" or extension == "mpeg"
    if path and path ~= "" and not isVideo and FILEMAN:DoesFileExist(path) then
        art:cropleft(0):cropright(0):croptop(0):cropbottom(0)
        art:Load(path)
        local w, h = art:GetWidth(), art:GetHeight()
        local zoom = math.max(ART / w, ART / h)
        art:zoom(zoom)
        local sx, sy = ART / (w * zoom), ART / (h * zoom)
        art:cropleft((1 - sx) / 2):cropright((1 - sx) / 2):croptop((1 - sy) / 2):cropbottom((1 - sy) / 2)
        art:visible(true)
    else
        art:visible(false)
    end
end

local function songArtPath(song)
    local path = song:GetJacketPath()
    if not path or path == "" then path = song:GetBannerPath() end
    if not path or path == "" then path = song:GetBackgroundPath() end
    return path
end

local function sleeveBack(tint)
    return Def.Sprite {
        Name = "Back",
        Texture = O2.gfx("sleeve_back"),
        InitCommand = function(self)
            self:zoomto(SLEEVE_W, SLEEVE_H)
            if tint then self:diffuse(tint) end
        end,
    }
end

local function sleeveWindow(fill)
    return Def.Quad {
        Name = "Window",
        InitCommand = function(self) self:xy(0, -6):zoomto(ART, ART):diffuse(fill) end,
    }
end

local function sleeveFrame()
    return Def.Sprite {
        Name = "Frame",
        Texture = O2.gfx("sleeve_frame"),
        InitCommand = function(self) self:zoomto(SLEEVE_W, SLEEVE_H) end,
    }
end

local function songActorBuilder()
    return Def.ActorFrame {
        Name = "Song",
        sleeveBack(),
        sleeveWindow(c.bg2),
        Def.Sprite {
            Name = "Art",
            InitCommand = function(self) self:xy(0, -6) end,
        },
        sleeveFrame(),
        -- the level of the chart that will be played, on a little tag at the corner of the art
        Def.ActorFrame {
            Name = "Level",
            InitCommand = function(self) self:xy(82, -108) end,
            Def.Sprite { Texture = O2.gfx("pill") },
            LoadFont(O2.fonts.plain) .. {
                Name = "Number",
                InitCommand = function(self) self:y(-1):zoom(0.75):diffuse(c.ink) end,
            },
        },
    }
end

local function groupActorBuilder()
    return Def.ActorFrame {
        Name = "Group",
        sleeveBack(c.mustard),
        sleeveWindow(c.coral),
        LoadFont(O2.fonts.bold) .. {
            Name = "Pack",
            InitCommand = function(self)
                self:xy(0, -6):zoom(0.8):wrapwidthpixels(ART / 0.8 - 20):maxheight(ART / 0.8 - 20):diffuse(c.cream)
            end,
        },
        sleeveFrame(),
    }
end

local function songActorUpdater(songFrame, song, isCurrentItem)
    setArt(songFrame:GetChild("Art"), songArtPath(song))
    local level = songFrame:GetChild("Level")
    local steps = isCurrentItem and GAMESTATE:GetCurrentSteps() or nil
    level:visible(steps ~= nil)
    if steps then
        level:GetChild("Number"):settext(string.format("%.1f", steps:GetMSD(1, 1)))
    end
end

local function groupActorUpdater(groupFrame, packName)
    groupFrame:GetChild("Pack"):settext(packName)
end

local function frameBuilder()
    local f
    f = Def.ActorFrame {
        Name = "ItemFrame",
        InitCommand = function(self) f.actor = self end,
        songActorBuilder() .. {
            BeginCommand = function(self) f.actor.s = self end,
        },
        groupActorBuilder() .. {
            BeginCommand = function(self) f.actor.g = self end,
        },
        UIElements.QuadButton(1) .. {
            Name = "WheelItemClickBox",
            InitCommand = function(self)
                self:diffusealpha(0)
                self:zoomto(SLEEVE_W, SLEEVE_H)
            end,
            MouseDownCommand = function(self, params)
                if params.event ~= "DeviceButton_left mouse button" then return end
                local index = self:GetParent().index
                local distance = math.floor(index - numWheelItems / 2) - 1
                local wheel = self:GetParent():GetParent()
                if distance ~= 0 then
                    wheel:playcommand("Move", { direction = distance })
                    wheel:playcommand("OpenIfGroup")
                else
                    wheel:playcommand("SelectCurrent")
                end
            end,
        },
    }
    return f
end

local function frameUpdater(frame, songOrPack, offset, isCurrentItem)
    local song, group = frame.s, frame.g
    if songOrPack.GetAllSteps then
        song:visible(true)
        group:visible(false)
        songActorUpdater(song, songOrPack, isCurrentItem)
    else
        song:visible(false)
        group:visible(true)
        groupActorUpdater(group, songOrPack)
    end
end

return Def.ActorFrame {
    Name = "WheelContainer",
    InitCommand = function(self)
        SCREENMAN:set_input_redirected(PLAYER_1, true)
    end,
    BeginCommand = function(self)
        -- hide the engine's own wheel; ours is driven by the same data
        SCREENMAN:GetTopScreen():GetMusicWheel():visible(false)
    end,
    WheelIndexChangedMessageCommand = function(self, params) wheelIndex = params.index end,
    WheelSettledMessageCommand = function(self, params) wheelIndex = params.index end,
    ClosedGroupMessageCommand = function(self) wheelIndex = nil end,
    OpenedGroupMessageCommand = function(self) wheelIndex = nil end,
    -- a new difficulty changes the level tag of the record on top
    ChangedStepsMessageCommand = function(self) self:GetChild("Wheel"):playcommand("UpdateWheel") end,

    MusicWheel:new({
        count = numWheelItems,
        startOnPreferred = true,
        songActorBuilder = songActorBuilder,
        groupActorBuilder = groupActorBuilder,
        songActorUpdater = songActorUpdater,
        groupActorUpdater = groupActorUpdater,
        frameTransformer = function(frame, offsetFromCenter) transformFrame(frame, offsetFromCenter) end,
        frameBuilder = frameBuilder,
        frameUpdater = frameUpdater,
        highlightBuilder = function() return Def.ActorFrame {} end,
    }),

    Def.Quad {
        Name = "MouseWheelRegion",
        InitCommand = function(self)
            self:diffusealpha(0):halign(0):valign(0):xy(0, 0):zoomto(560 * k, SCREEN_HEIGHT)
        end,
        MouseScrollMessageCommand = function(self, params)
            if isOver(self) then
                self:GetParent():GetChild("Wheel"):playcommand("Move", { direction = params.direction == "Up" and -1 or 1 })
            end
        end,
    },
}
