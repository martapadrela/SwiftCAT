# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

from nicegui import ui
from startup_gui import startup_screen

app_container = ui.column().classes('w-full')

startup_screen(app_container)

ui.run(host="0.0.0.0", port=8080, reload=False, title = "SwiftCAT")