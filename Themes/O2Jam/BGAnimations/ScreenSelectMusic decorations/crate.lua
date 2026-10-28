-- The front of the crate, drawn over the wheel's sleeves, plus
-- the tab that sticks up from the back of the stack with the name of the pack.
local k = O2.k
local c = O2.colors

local stackTop = { x = 250 * k, y = 355 * k } -- where the front sleeve stands; the tab follows the stack

local t = Def.ActorFrame { Name = "Crate" }

local depthShown = 0

local function placeTab(self)
    -- the deepest visible record sits up and to the right of the front one
    local d = depthShown
    local x = stackTop.x + d * 13 * k - 70 * k
    local y = stackTop.y - d * 8.5 * k - 150 * (1.15 - d * 0.012) * k - 26 * k
    self:xy(x, y)
end

t[#t + 1] = Def.ActorFrame {
    Name = "Tab",
    InitCommand = function(self) placeTab(self) end,
    WheelIndexChangedMessageCommand = function(self, params)
        depthShown = math.min((params.index or 1) - 1, 9)
        placeTab(self)
    end,
    WheelSettledMessageCommand = function(self, params)
        depthShown = math.min((params.index or 1) - 1, 9)
        placeTab(self)
        local pack = params.song and params.song:GetGroupName() or (type(params.hovered) == "string" and params.hovered or "")
        self:GetChild("Name"):settext(pack)
    end,
    Def.Sprite {
        Texture = O2.gfx("tag"),
        InitCommand = function(self) self:halign(0):valign(0) end,
    },
    LoadFont(O2.fonts.plain) .. {
        Name = "Name",
        InitCommand = function(self)
            self:xy(85 * k, 10 * k):valign(0):zoom(0.8):maxwidth(150 * k / 0.8):diffuse(c.ink)
        end,
    },
}

t[#t + 1] = Def.Sprite {
    Name = "Tray",
    Texture = O2.gfx("tray"),
    InitCommand = function(self) self:halign(0):valign(0):xy(-10 * k, 440 * k) end,
}

return t
