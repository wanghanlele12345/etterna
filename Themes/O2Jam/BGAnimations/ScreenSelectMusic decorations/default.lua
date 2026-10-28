-- Select music: a crate of records. The wheel (wheel.lua) is the stack of sleeves, crate.lua
-- draws the tray in front of it, info.lua the text beside it.
local t = Def.ActorFrame {}

t[#t + 1] = LoadActor("wheel")
t[#t + 1] = LoadActor("crate")
t[#t + 1] = LoadActor("info")

return t
