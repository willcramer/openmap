-- Explicitly await the real cooperative planner in older behavior fixtures.
-- Raw GPSStart/GPSPlay tests exercise accepted/pending lifecycle separately.
local gps = ...
function DrainGPS()
	for _ = 1, 20000 do
		if not gps.GPSPlanningStats().active then
			return not gps.GPSStatus().planningError, gps.GPSStatus().planningError
		end
		gps.GPSRunPlanning(1)
	end
	error("GPS planning did not finish within the fixture frame limit")
end
function PlanGPS(...)
	local ok, err = gps.GPSStart(...)
	if not ok then return ok, err end
	return DrainGPS()
end
function PlayGPS(...)
	local ok, err = gps.GPSPlay(...)
	if not ok then return ok, err end
	return DrainGPS()
end
function RoutingGPS(...)
	local ok = gps.GPSSetRoutingOption(...)
	DrainGPS()
	return ok
end
function CommandGPS(...)
	SlashCmdList.OPENMAP(...)
	return DrainGPS()
end
