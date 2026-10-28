-- O2Jam gameplay overlay: layout controller + HUD.
-- Practice, replay and gameplay-customization modes need Rebirth's own element machinery,
-- so they get Rebirth's overlay untouched (the player still sits in the O2Jam position).
local practiceEnabled = GAMESTATE:IsPracticeMode()
local replayEnabled = GAMESTATE:GetGameplayMode() == "GameplayMode_Replay"
local customizationEnabled = playerConfig:get_data().CustomizeGameplay == true

if practiceEnabled or replayEnabled or customizationEnabled then
    return LoadActor("/Themes/Rebirth/BGAnimations/ScreenGameplay overlay/default.lua")
end

Arch.setCursorVisible(false)
TOOLTIP:HidePointer()

-- Rebirth's notefield cover reads MovableValues while it loads, so fill them in as Rebirth does.
setMovableKeymode(getCurrentKeyMode())

local t = Def.ActorFrame {
    Name = "O2JamOverlay",
    BeginCommand = function(self)
        if updateNowPlaying then
            updateNowPlaying()
        end
        local screen = SCREENMAN:GetTopScreen()
        if not screen then
            return
        end
        -- the stock life bar is replaced by the vertical gauge
        local lifebar = screen:GetLifeMeter(PLAYER_1)
        if lifebar then
            lifebar:visible(false)
        end
        -- fit the whole song background into the video region beside the lanes
        local background = screen:GetChild("SongBackground")
        if background then
            local zoom, x, y = O2.videoTransform()
            background:zoom(zoom)
            background:xy(x, y)
        end
    end,
}

t[#t + 1] = LoadActor("hud")

-- re entering gameplay should empty the mouse overlay stuff
local screenName = Var("LoadingScreen") or ...
BUTTON:ResetButtonTable(screenName)

return t
