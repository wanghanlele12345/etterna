-- The record shop: a brick wall and a floor. The crate (decorations) stands on it, the grain and
-- vignette (overlay) go over everything.
local W, H = SCREEN_WIDTH, SCREEN_HEIGHT
local k = O2.k

-- reset the context manager as early as possible in the select music init (Rebirth does the same)
CONTEXTMAN:Reset()

local t = Def.ActorFrame { Name = "UnderlayFile" }

-- brick wall over a purple floor
t[#t + 1] = Def.Sprite {
    Texture = O2.gfx("wall"),
    InitCommand = function(self)
        self:halign(0):valign(0):xy(0, 0):zoomto(W, H)
    end,
}

return t
