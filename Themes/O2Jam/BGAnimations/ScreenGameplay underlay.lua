-- Static backdrop of the gameplay screen: wallpaper, inked panels, lanes.
-- The engine draws the song background (the video) first and this underlay above it, so the
-- backdrop is painted in pieces around the video window instead of over it.

local W, H = SCREEN_WIDTH, SCREEN_HEIGHT
local k = O2.k
local colors = O2.colors
local style = GAMESTATE:GetCurrentStyle()
local columns = style and style:ColumnsPerPlayer() or 7
local laneW = O2.laneWidth
local fieldLeft = O2.fieldLeft
local fieldRight = fieldLeft + columns * laneW
local video = O2.video

local t = Def.ActorFrame { Name = "O2Underlay" }

-- the stock Rebirth underlay resets the context manager and applies mods; keep it
t[#t + 1] = LoadActor("/Themes/Rebirth/BGAnimations/ScreenGameplay underlay.lua")

local function sprite(name, x, y, w, h)
    return Def.Sprite {
        Texture = O2.gfx(name),
        InitCommand = function(self)
            self:halign(0):valign(0):xy(x, y)
            if w then
                self:zoomto(w, h)
            end
        end,
    }
end

local function quad(x, y, w, h, color, alpha)
    return Def.Quad {
        InitCommand = function(self)
            self:halign(0):valign(0):xy(x, y):zoomto(w, h):diffuse(color)
            if alpha then
                self:diffusealpha(alpha)
            end
        end,
    }
end

-- one piece of the wallpaper, cropped to the screen rectangle it covers (cropping, not
-- customtexturerect: the engine pads non power of two textures and rect fractions would show the padding)
local function backdropPiece(x0, y0, x1, y1)
    return Def.Sprite {
        Texture = O2.gfx("backdrop"),
        InitCommand = function(self)
            self:halign(0):valign(0):xy(0, 0):zoomto(W, H)
            self:cropleft(x0 / W):cropright(1 - x1 / W):croptop(y0 / H):cropbottom(1 - y1 / H)
        end,
    }
end
t[#t + 1] = backdropPiece(0, 0, W, video.y)
t[#t + 1] = backdropPiece(0, video.y + video.h, W, H)
t[#t + 1] = backdropPiece(0, video.y, video.x, video.y + video.h)
t[#t + 1] = backdropPiece(video.x + video.w, video.y, W, video.y + video.h)

-- left margin rail, an ink line with a cream edge
t[#t + 1] = quad(fieldLeft - 9 * k, 0, 3 * k, O2.regionBottom, colors.cream, 0.5)
t[#t + 1] = quad(fieldLeft - 6 * k, 0, 6 * k, O2.regionBottom, colors.ink)

-- lanes, each tinted like the keys under it
for lane = 1, columns do
    t[#t + 1] = sprite("lane_" .. O2.laneColorName(lane), fieldLeft + (lane - 1) * laneW, 0, laneW, O2.regionBottom)
end
for i = 0, columns do
    local edge = i == 0 or i == columns
    t[#t + 1] = quad(fieldLeft + i * laneW - (edge and 3 or 1.5) * k, 0, (edge and 6 or 3) * k, O2.regionBottom,
        colors.ink, edge and 1 or 0.7)
end

-- record cells + energy column
t[#t + 1] = quad(fieldRight + 3 * k, 0, O2.stripX - fieldRight - 3 * k, O2.regionBottom, colors.bg0, 0.55)
t[#t + 1] = sprite("strip", O2.stripX, 0, 24 * k, H)

-- right column cards
t[#t + 1] = sprite("panel_info", O2.info.x, O2.info.y, O2.info.w, O2.info.h)
t[#t + 1] = sprite("video_frame", video.x - 6 * k, video.y - 6 * k, 504 * k, 294 * k)
t[#t + 1] = sprite("panel_stats", O2.stats.x, O2.stats.y, O2.stats.w, O2.stats.h)

-- bottom bar and the wells in it
t[#t + 1] = sprite("panel_bottom", 0, O2.regionBottom, W, O2.barHeight)
t[#t + 1] = sprite("panel_score", 18 * k, 651 * k, 276 * k, 60 * k)
t[#t + 1] = sprite("panel_wide", 306 * k, 651 * k, 342 * k, 60 * k)
t[#t + 1] = sprite("panel_grade", 660 * k, 651 * k, 210 * k, 60 * k)

return t
