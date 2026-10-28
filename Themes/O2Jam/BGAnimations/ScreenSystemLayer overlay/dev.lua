local FLAG = "/Save/o2jam_dev.txt"
if not FILEMAN:DoesFileExist(FLAG) then
    return Def.ActorFrame {}
end

-- flag file lines: difficulty=Easy   autoplay=1
local settings = { difficulty = "Easy", autoplay = "0", fakefx = "0", stop = "", moves = "", steps = "" }
local file = RageFileUtil.CreateRageFile()
if file:Open(FLAG, 1) then
    for key, value in tostring(file:Read()):gmatch("(%w+)=([%w,%-]+)") do
        settings[key] = value
    end
    file:Close()
end
file:destroy()

local done = {}

-- a scripted run of judgments to see every effect: 60 COOLs (milestones, FEVER), then a mix
local script = {}
for i = 1, 60 do script[#script + 1] = "TapNoteScore_W1" end
for _, kind in ipairs({ "TapNoteScore_W3", "TapNoteScore_W1", "TapNoteScore_W1", "TapNoteScore_W5",
                        "TapNoteScore_W1", "TapNoteScore_W2", "TapNoteScore_Miss", "TapNoteScore_W1",
                        "TapNoteScore_W3", "TapNoteScore_W4", "TapNoteScore_Miss" }) do
    script[#script + 1] = kind
end
for i = 1, 40 do script[#script + 1] = "TapNoteScore_W1" end
local fakeIndex = 0

local function pickSong()
    local song = SONGMAN:GetAllSongs()[1]
    if not song then
        print("O2DEV no songs")
        return
    end
    local wanted = "Difficulty_" .. settings.difficulty
    local steps
    for _, s in ipairs(song:GetAllSteps()) do
        if s:GetDifficulty() == wanted and s:GetStepsType() == "StepsType_Kb7_Single" then
            steps = s
        end
    end
    print("O2DEV picking " .. song:GetMainTitle() .. " " .. wanted .. " steps=" .. tostring(steps ~= nil))
    GAMESTATE:SetCurrentSong(song)
    if steps then
        GAMESTATE:SetCurrentSteps(PLAYER_1, steps)
    end
    if settings.autoplay == "1" then
        GAMESTATE:ApplyGameCommand("mod,playerautoplay")
    end
    local top = SCREENMAN:GetTopScreen()
    top:GetMusicWheel():SelectSong(song)
    if top.SelectUserSong ~= nil then
        top:SelectUserSong()
    else
        top:SelectCurrent()
    end
end

return Def.ActorFrame {
    ScreenChangedMessageCommand = function(self)
        local top = SCREENMAN:GetTopScreen()
        local name = top and top:GetName() or ""
        print("O2DEV screen " .. name)
        if name == settings.stop then
            return -- stay here so the screen can be captured
        end
        if name == "ScreenTitleMenu" and not done.title then
            done.title = true
            self:sleep(2):queuecommand("LeaveTitle")
        elseif name == "ScreenSelectMusic" and settings.moves ~= "" and not done.moves then
            done.moves = true
            self:sleep(3):queuecommand("RunMoves")
        elseif name == "ScreenSelectMusic" and not done.select then
            done.select = true
            self:sleep(3):queuecommand("PickSong")
        elseif name == "ScreenGameplay" and settings.fakefx == "1" and not done.fake then
            done.fake = true
            self:sleep(4):queuecommand("FakeStep")
        end
    end,
    FakeStepCommand = function(self)
        fakeIndex = fakeIndex + 1
        local tns = script[((fakeIndex - 1) % #script) + 1]
        MESSAGEMAN:Broadcast("Judgment", {
            Player = PLAYER_1, TapNoteScore = tns, Judgment = tns, FirstTrack = (fakeIndex * 3) % 7,
            Type = "Tap", Early = false,
        })
        self:sleep(0.12):queuecommand("FakeStep")
    end,
    RunMovesCommand = function(self)
        -- moves=1,1,-1  walks the wheel; each entry is a distance, one per second
        done.moveIndex = (done.moveIndex or 0) + 1
        local list = {}
        for token in settings.moves:gmatch("[^,]+") do list[#list + 1] = tonumber(token) or token end
        local step = list[done.moveIndex]
        if not step then return end
        local container = SCREENMAN:GetTopScreen():GetChild("WheelContainer")
        local wheel = container and container:GetChild("Wheel")
        print("O2DEV move " .. step .. " wheel=" .. tostring(wheel ~= nil))
        if wheel and step == "s" then
            wheel:playcommand("SelectCurrent")
        elseif wheel and step == "d" then
            local song = GAMESTATE:GetCurrentSong()
            local charts = song and WHEELDATA:GetChartsMatchingFilter(song) or {}
            local current = GAMESTATE:GetCurrentSteps()
            for i, chart in ipairs(charts) do
                if chart == current and charts[i + 1] then
                    GAMESTATE:SetCurrentSteps(PLAYER_1, charts[i + 1])
                    MESSAGEMAN:Broadcast("ChangedSteps", { steps = charts[i + 1] })
                    break
                end
            end
        elseif wheel then
            wheel:playcommand("Move", { direction = step })
        end
        self:sleep(1.2):queuecommand("RunMoves")
    end,
    LeaveTitleCommand = function(self)
        TITLE:HandleFinalGameStart()
    end,
    PickSongCommand = function(self)
        local ok, err = pcall(pickSong)
        if not ok then
            print("O2DEV error " .. tostring(err))
        end
    end,
}
