-- o2jam key colors: [white][blue][white][yellow][white][blue][white]
local keyColors = {
	Key1 = "white",
	Key2 = "blue",
	Key3 = "white",
	Key4 = "yellow",
	Key5 = "white",
	Key6 = "blue",
	Key7 = "white"
}
local keyColor = keyColors[Var "Button"] or "white"

local t =
	Def.ActorFrame {
	-- normal
	Def.Sprite {
		Texture = NOTESKIN:GetPath("_bar", "receptor base " .. keyColor),
		Frame0000 = 0,
		Delay0000 = 1,
		InitCommand = NOTESKIN:GetMetricA("ReceptorArrow", "InitCommand"),
		NoneCommand = NOTESKIN:GetMetricA("ReceptorArrow", "NoneCommand"),
		PressCommand = NOTESKIN:GetMetricA("ReceptorArrow", "PressCommand")
	},
	-- flashpert
	Def.Sprite {
		Texture = "_bar receptor tap",
		Frame0000 = 0,
		Delay0000 = 1,
		InitCommand = NOTESKIN:GetMetricA("ReceptorOverlay", "InitCommand"),
		PressCommand = NOTESKIN:GetMetricA("ReceptorOverlay", "PressCommand"),
		LiftCommand = NOTESKIN:GetMetricA("ReceptorOverlay", "LiftCommand"),
		NoneCommand = NOTESKIN:GetMetricA("ReceptorArrow", "NoneCommand")
	}
}

return t
