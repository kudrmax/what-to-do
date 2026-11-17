# The disk image window for dmgbuild (https://dmgbuild.readthedocs.io): the app on the left, Applications on
# the right, and the background's arrow between them. build-dmg.sh passes app, background and icon.
import os.path

app = defines["app"]  # noqa: F821 — dmgbuild provides `defines`
app_name = os.path.basename(app)

format = "ULFO"
filesystem = "APFS"
files = [app]
symlinks = {"Applications": "/Applications"}
icon = defines["icon"]  # noqa: F821
background = defines["background"]  # noqa: F821

window_rect = ((200, 160), (640, 400))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
icon_size = 112
text_size = 13
icon_locations = {app_name: (170, 180), "Applications": (470, 180)}
