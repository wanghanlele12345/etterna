-- Paper grain and darkened corners over the select screen, plus the mouse cursor layer.
local W, H = SCREEN_WIDTH, SCREEN_HEIGHT
local k = O2.k

local t = Def.ActorFrame {
    OnCommand = function(self)
        if MPinput then
            SCREENMAN:GetTopScreen():AddInputCallback(MPinput)
        end
    end,
}

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

t[#t + 1] = LoadActor("/Themes/Rebirth/BGAnimations/_mouse.lua")

return t
