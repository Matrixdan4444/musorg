# dmgbuild settings for the Musorg installer image.
#
# Produces a drag-to-install window with two large icons side by side —
# Musorg.app on the left, an Applications symlink on the right. dmgbuild writes
# the .DS_Store layout directly (no Finder scripting), so it works headless.
#
# Driven by packaging/make_dmg.sh, which passes the app path and volume name
# via the defines below. Run through: dmgbuild -s packaging/dmg_settings.py ...

import os

app_path = os.environ["MUSORG_APP"]
app_name = os.path.basename(app_path)

# Contents of the image: the app, plus a symlink to /Applications.
files = [app_path]
symlinks = {"Applications": "/Applications"}

# Icon view layout: large icons, app on the left, Applications on the right.
icon_size = 160
default_view = "icon-view"
show_icon_preview = False
include_icon_view_settings = True
include_list_view_settings = False
arrange_by = None
text_size = 13

# Window geometry: {x, y, width, height} of the content area.
window_rect = ((420, 160), (640, 360))

icon_locations = {
    app_name: (170, 175),
    "Applications": (470, 175),
}

# No custom background image: keep the default so we ship nothing binary.
background = None
