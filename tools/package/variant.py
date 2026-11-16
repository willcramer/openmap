"""Package the GPS test build under its own addon identity.

Source and the normal release remain OpenMap. Only the GPS archive's own code and
metadata are rewritten; bundled libraries, licences, notices and art bytes stay intact.
"""
import re


BOOTSTRAP = "OpenMap/BootGPS.lua"
GUARD = "if select(2, ...).variantDormant then return end\n"


def gps_path(path):
    """Rename the addon directory and its own named assets, keeping libraries intact."""
    if path.startswith("OpenMap/Libs/"):
        return "OpenMapGPS/" + path[len("OpenMap/"):]
    return path.replace("OpenMap", "OpenMapGPS")


def gps_transform(path, data, toc):
    """Return archive path and bytes for a committed addon file."""
    target = gps_path(path)
    if path == BOOTSTRAP or path.startswith("OpenMap/Libs/"):
        return target, data
    if not path.lower().endswith((".lua", ".xml", ".toc")):
        return target, data
    text = data.decode("utf-8-sig")
    text = text.replace("https://github.com/openmap-world/openmap", "https://github.com/willcramer/openmap")
    text = text.replace("OpenMap", "OpenMapGPS").replace("OPENMAP", "OPENMAPGPS")
    text = re.sub(r"(?<![\w/:])/(openmap|omap)(?![\w-])",
                  lambda m: "/openmapgps" if m[1] == "openmap" else "/omgps", text)
    if path == toc:
        lines = []
        boot = False
        for line in text.splitlines():
            if line.startswith("## Title:"):
                lines.append("## Title: |cffe6b85cOpenMap GPS Test|r")
                # Forever's AddonList uses Group to override C++'s automatic
                # grouping of similarly named/dependent addons. It must match
                # this addon's folder name, not its displayed title.
                lines.append("## Group: OpenMapGPS")
                continue
            elif line.startswith("## Group:"):
                continue
            elif line.startswith("## X-Curse-Project-ID:"):
                continue
            elif line.startswith("## X-Website:"):
                line = "## X-Website: https://github.com/willcramer/openmap"
            elif line.startswith("## OptionalDeps:"):
                dependencies = line.partition(":")[2].strip()
                line = "## OptionalDeps: OpenMap" + (", " + dependencies if dependencies else "")
            elif line.strip() and not line.lstrip().startswith("#") and not boot:
                lines.append("BootGPS.lua")
                boot = True
            lines.append(line)
        if not boot:
            raise ValueError("the GPS toc has no files to load after its bootstrap")
        text = "\n".join(lines) + "\n"
    elif path.endswith(".lua"):
        text = GUARD + text
    elif path.endswith(".xml"):
        # Bindings.xml loads automatically even when the bootstrap keeps this copy dormant.
        text = re.sub(r"(<Binding\b[^>]*>)(.*?)(</Binding>)",
                      lambda m: m[1] + "if OpenMapGPS_Binding then " + m[2].strip() + " end" + m[3],
                      text, flags=re.S)
    return target, text.encode("utf-8")
