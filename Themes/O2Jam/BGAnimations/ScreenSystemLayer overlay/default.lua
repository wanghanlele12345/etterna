-- The stock system layer, plus a developer driver that is only active while
-- Save/o2jam_dev.txt exists (it walks title -> select music -> gameplay by itself so the
-- gameplay screen can be screenshotted without anyone at the keyboard).
local t = Def.ActorFrame {}
t[#t + 1] = LoadActor("/Themes/_fallback/BGAnimations/ScreenSystemLayer overlay/default.lua")
t[#t + 1] = LoadActor("dev.lua")
return t
