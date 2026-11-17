# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

from nicegui import ui, run
from names_curation import build_mapping_duplicates_control, build_all_filenames, build_filename
from project_settings_config import SettingsConfig
from classification_config import ClassificationConfig
from classification_rules_editor import (
    open_classification_rules_editor
)
import pandas as pd
import json
import os
from pathlib import Path
# =========================================================
# CONFIG
# =========================================================

FIELD_ORDER = [
    "Sub", "Ses", "EchoTime", "RepetitionTime", "FlipAngle",
    "InversionTime", "ScanningSequence", "MRAcquisitionType",
    "PrincipalPlane", "MagneticFieldStrength", "ScannerModel", 
    "AcquisitionTime", "Gad_keywords", "Repeat", "Original Filepath",
    "Original Path", "path_nii"
]



def show_rule_editor(config):
    """
    Show a dialog to edit classification rules.
    This is a placeholder - you can extend this to edit individual rules.
    """
    with ui.dialog() as dialog:
        with ui.card().classes('w-full max-w-2xl'):
            ui.label('Classification Rules Editor').classes('text-lg font-bold')
            
            # Display all rule names
            rule_names = config.get_all_rule_names()
            ui.label(f'Available rules: {", ".join(rule_names)}').classes('text-sm text-gray-600')
            
            ui.label('Note: To modify rules, edit the classification_config.json file or use programmatic API').classes('text-sm')
            
            with ui.row():
                ui.button('Close', on_click=dialog.close)
    
    dialog.open()


def launch_gui(all_scans,container, project_folder):
    """Launch the main GUI.
    
    Args:
        all_scans: List of scan dictionaries
        container: NiceGUI container element
        project_folder: Path to the project folder
    """
    
    print("Launching main GUI")
    with container:
        prepare_scans(all_scans)

        table = create_table(all_scans, project_folder)
        print(f"Loaded {len(all_scans)} scans")
        export_csv(all_scans, project_folder)
        register_row_click(table, all_scans, project_folder)

        create_bottom_controls(all_scans, table, project_folder)

        ui.label('Click a row to edit the Proposed Filename.')


# =========================================================
# 1. DATA PREPARATION
# =========================================================

def prepare_scans(all_scans):
    for i, scan in enumerate(all_scans):
        scan['_idx'] = i
        scan.setdefault('gad_manual', 'To Do')
        scan.setdefault('manual_inspection', 'To Do')
        scan.setdefault('notes', '')
        scan.setdefault('_original_state', {
            'Orientation': scan.get('Orientation'),
            'scan_seq': scan.get('scan_seq'),
            'Contrast': scan.get('Contrast'),
            'Modality': scan.get('Modality'),
            'run': scan.get('run'),
            'Proposed Filename': scan.get('Proposed Filename'),
        })


# =========================================================
# 2. TABLE
# =========================================================

def build_table_rows(all_scans, datatype_options=None):
    datatype_options = datatype_options or []

    return [
        {
            'Parent Folder': s['Parent Folder'],
            'Datatype': s['Datatype'],
            'Original Filename': s['Original Filename'],
            'Proposed Filename': s['Proposed Filename'],
            '_idx': s['_idx'],
            '_datatype_options': datatype_options,
            'gad_manual': s['gad_manual'],
            'manual_inspection': s['manual_inspection'],
            'notes': s['notes'],
        }
        for s in all_scans
    ]

def load_classification_config(project_folder):
    settings_path = os.path.join(
        project_folder, 'project_settings.json'
    )

    settings = SettingsConfig()
    settings.load_from_file(settings_path)
    classification_config_filename = settings.classification_config
    base_dir = Path(__file__).resolve().parent
    class_config_path = base_dir / "classification_configs" / classification_config_filename
    config = ClassificationConfig()
    config.load_from_file(class_config_path)
    
    return config, class_config_path, settings, settings_path



EMPTY_DATATYPE = "__EMPTY_DATATYPE__"


def is_empty_datatype(value):
    return value is None or str(value).strip() == ""


def apply_table_filters(table, all_scans, datatype_options):
    """Apply active column filters without modifying all_scans."""

    rows = build_table_rows(all_scans, datatype_options)
    filters = table._curation_filters

    def matches_condition(text, condition):
        operator = condition.get("operator", "contains")
        value = str(condition.get("value", "")).casefold()
        text = str(text or "").casefold()

        if not value:
            return True

        if operator == "contains":
            return value in text
        if operator == "does not contain":
            return value not in text
        if operator == "starts with":
            return text.startswith(value)
        if operator == "does not start with":
            return not text.startswith(value)
        if operator == "ends with":
            return text.endswith(value)
        if operator == "does not end with":
            return not text.endswith(value)
        if operator == "equals":
            return text == value
        if operator == "does not equal":
            return text != value

        return True

    filtered_rows = []

    for row in rows:
        scan = all_scans[row["_idx"]]
        keep = True

        # Datatype: exact matching, including the special (Empty) option.
        selected_datatypes = filters["Datatype"]["values"]

        if selected_datatypes is not None:
            datatype = row.get("Datatype")

            datatype_matches = any(
                (
                    selected == EMPTY_DATATYPE
                    and is_empty_datatype(datatype)
                )
                or (
                    selected != EMPTY_DATATYPE
                    and not is_empty_datatype(datatype)
                    and datatype == selected
                )
                for selected in selected_datatypes
            )

            if not datatype_matches:
                keep = False

        # Text filters for Parent Folder and Original Filename.
        for column in ("Parent Folder", "Original Filename"):
            if not keep:
                break

            state = filters[column]
            conditions = [
                c for c in state["conditions"]
                if str(c.get("value", "")).strip()
            ]

            if conditions:
                results = [
                    matches_condition(row.get(column), condition)
                    for condition in conditions
                ]

                keep = (
                    any(results)
                    if state["join"] == "OR"
                    else all(results)
                )

        # Proposed Filename text conditions and gad status.
        if keep:
            state = filters["Proposed Filename"]
            conditions = [
                c for c in state["conditions"]
                if str(c.get("value", "")).strip()
            ]

            if conditions:
                results = [
                    matches_condition(
                        row.get("Proposed Filename"), condition
                    )
                    for condition in conditions
                ]

                keep = (
                    any(results)
                    if state["join"] == "OR"
                    else all(results)
                )

            selected_statuses = state["gad_statuses"]

            if (
                keep
                and selected_statuses is not None
                and scan.get("gad_manual", "To Do") not in selected_statuses
            ):
                keep = False

        if keep:
            filtered_rows.append(row)

    table.rows = filtered_rows
    table.update()




def add_column_filter_menu(table, column, all_scans, datatype_options):
    """Add a filter menu inside its parent column-filter button."""

    import copy

    filters = table._curation_filters
    current = copy.deepcopy(filters[column])

    # Always use the latest datatype options from the table.
    datatype_options = table._curation_datatype_options

    with ui.menu().classes("w-80") as menu:
        with ui.card().classes("w-full p-3 gap-3"):
            with ui.row().classes("items-center justify-between w-full"):
                ui.label(f"Filter by {column}").classes(
                    "text-base font-bold"
                )
                ui.icon("filter_list").classes("text-grey-7")

            if column == "Datatype":
                ui.label("Show rows matching:").classes("text-sm text-grey-7")

                datatype_filter_options = [
                    *datatype_options,
                    EMPTY_DATATYPE,
                ]

                current_values = current["values"]
                datatype_checks = []

                for datatype in datatype_filter_options:
                    label = (
                        "(Empty)"
                        if datatype == EMPTY_DATATYPE
                        else datatype
                    )

                    checkbox = ui.checkbox(
                        label,
                        value=(
                            True
                            if current_values is None
                            else datatype in current_values
                        ),
                    )

                    datatype_checks.append((datatype, checkbox))

                def select_all_datatypes():
                    for _, checkbox in datatype_checks:
                        checkbox.value = True

                def select_no_datatypes():
                    for _, checkbox in datatype_checks:
                        checkbox.value = False

                with ui.row().classes("gap-1"):
                    ui.button(
                        "Select all",
                        on_click=select_all_datatypes,
                    ).props("flat dense no-caps")

                    ui.button(
                        "Clear selection",
                        on_click=select_no_datatypes,
                    ).props("flat dense no-caps")

                def save_datatype_filter():
                    selected = [
                        datatype
                        for datatype, checkbox in datatype_checks
                        if checkbox.value
                    ]

                    # None means no restriction. An empty list means
                    # that no datatype values are selected.
                    filters[column]["values"] = (
                        None
                        if len(selected) == len(datatype_filter_options)
                        else selected
                    )

                    apply_table_filters(
                        table, all_scans, datatype_options
                    )
                    menu.close()

                with ui.row().classes("justify-end w-full"):
                    ui.button(
                        "Cancel", on_click=menu.close
                    ).props("flat no-caps")

                    ui.button(
                        "Apply", on_click=save_datatype_filter
                    ).props("unelevated no-caps")

            else:
                operators = [
                    "contains",
                    "does not contain",
                    "starts with",
                    "does not start with",
                    "ends with",
                    "does not end with",
                    "equals",
                    "does not equal",
                ]

                condition_controls = []
                join_input = None

                for index in range(2):
                    saved = (
                        current["conditions"][index]
                        if index < len(current["conditions"])
                        else {"operator": "contains", "value": ""}
                    )

                    with ui.column().classes("w-full gap-1"):
                        ui.label(
                            "Condition 1" if index == 0 else "Condition 2"
                        ).classes("text-sm font-medium")

                        operator_input = ui.select(
                            operators,
                            value=saved.get("operator", "contains"),
                            label="Operator",
                        ).classes("w-full")

                        value_input = ui.input(
                            label="Text",
                            value=saved.get("value", ""),
                            placeholder="Enter text...",
                        ).props("clearable").classes("w-full")

                    condition_controls.append(
                        (operator_input, value_input)
                    )

                    if index == 0:
                        with ui.row().classes("items-center gap-2"):
                            ui.label("Match")
                            join_input = ui.radio(
                                ["AND", "OR"],
                                value=current["join"],
                            ).props("inline")

                status_checks = []

                if column == "Proposed Filename":
                    ui.separator()
                    ui.label("Gadolinium manual check").classes(
                        "text-sm font-medium"
                    )

                    available_statuses = sorted({
                        str(scan.get("gad_manual", "To Do"))
                        for scan in all_scans
                        if scan.get("gad_manual", "To Do") is not None
                    })

                    saved_statuses = current["gad_statuses"]

                    for status in available_statuses:
                        checkbox = ui.checkbox(
                            status,
                            value=(
                                True
                                if saved_statuses is None
                                else status in saved_statuses
                            ),
                        )
                        status_checks.append((status, checkbox))

                def clear_column_filter():
                    if column == "Datatype":
                        filters[column]["values"] = None
                    else:
                        filters[column]["conditions"] = []
                        filters[column]["join"] = "AND"

                        if column == "Proposed Filename":
                            filters[column]["gad_statuses"] = None

                    apply_table_filters(
                        table, all_scans, datatype_options
                    )
                    menu.close()

                def save_text_filter():
                    conditions = []

                    for operator_input, value_input in condition_controls:
                        value = (value_input.value or "").strip()

                        if value:
                            conditions.append({
                                "operator": operator_input.value,
                                "value": value,
                            })

                    filters[column]["conditions"] = conditions
                    filters[column]["join"] = join_input.value

                    if column == "Proposed Filename":
                        selected = [
                            status
                            for status, checkbox in status_checks
                            if checkbox.value
                        ]

                        filters[column]["gad_statuses"] = (
                            None
                            if len(selected) == len(status_checks)
                            else selected
                        )

                    apply_table_filters(
                        table, all_scans, datatype_options
                    )
                    menu.close()

                with ui.row().classes("justify-between w-full"):
                    ui.button(
                        "Clear filter",
                        on_click=clear_column_filter,
                    ).props("flat dense no-caps")

                    with ui.row().classes("gap-1"):
                        ui.button(
                            "Cancel", on_click=menu.close
                        ).props("flat no-caps")

                        ui.button(
                            "Apply", on_click=save_text_filter
                        ).props("unelevated no-caps")

    return menu


def rebuild_filter_buttons(filter_buttons, table, all_scans):
    """Recreate filter menus using the latest datatype configuration."""

    filter_buttons.clear()

    datatype_options = table._curation_datatype_options

    with filter_buttons:
        for column in table._curation_columns:
            with ui.button(
                column,
                icon="arrow_drop_down",
            ).props("flat dense no-caps"):
                add_column_filter_menu(
                    table,
                    column,
                    all_scans,
                    datatype_options,
                )


def create_table(all_scans, project_folder):
    settings_path = os.path.join(
        project_folder, "project_settings.json"
    )

    settings = SettingsConfig()
    settings.load_from_file(settings_path)

    config, config_path, settings, settings_path = load_classification_config(project_folder)

    has_contrast_data = settings.get("has_contrast_data", False)

    # Use the actual datatype names from the selected project config.
    datatype_options = list(
        config.get("datatype_rules", {}).keys()
    )

    columns = [
        "Parent Folder",
        "Datatype",
        "Original Filename",
        "Proposed Filename",
    ]

    # Store persistent filter state on the table.
    filters = {
        "Parent Folder": {
            "conditions": [],
            "join": "AND",
        },
        "Datatype": {
            "values": None,
        },
        "Original Filename": {
            "conditions": [],
            "join": "AND",
        },
        "Proposed Filename": {
            "conditions": [],
            "join": "AND",
            "gad_statuses": None,
        },
    }

    with ui.row().classes("w-full items-center gap-2 mb-2"):
        ui.label("Filters").classes("font-bold text-gray-600")
        filter_buttons = ui.row().classes("items-center gap-2")


    table = ui.table(
        rows=build_table_rows(all_scans, datatype_options),
        columns=[
            {
                "name": column,
                "label": column,
                "field": column,
                "align": "left",
                "sortable": True,
            }
            for column in columns
        ],
        pagination={
            "rowsPerPage": 10,
            "sortBy": "Original Filename",
            "page": 1,
        },
    ).classes("w-full").props("virtual-scroll")

    table._curation_filters = filters
    table._curation_columns = columns
    table._curation_datatype_options = datatype_options


    table._curation_filter_buttons = filter_buttons

    rebuild_filter_buttons(
        filter_buttons,
        table,
        all_scans,
    )

    # Keep the existing editable Datatype dropdown.
    table.add_slot(
        "body-cell-Datatype",
        r"""
        <q-td :props="props" @click.stop>
            <q-select
                v-model="props.row.Datatype"
                :options="props.row._datatype_options"
                dense
                outlined
                options-dense
                emit-value
                map-options
                @click.stop
                @mousedown.stop
                @update:model-value="
                    $parent.$emit('datatype-change', {
                        idx: props.row._idx,
                        datatype: $event
                    })
                "
            />
        </q-td>
        """,
    )

    def handle_datatype_change(e):
        idx = e.args["idx"]
        datatype = e.args["datatype"]

        all_scans[idx]["Datatype"] = datatype

        refresh_table(table, all_scans, datatype_options)
        export_csv(all_scans, project_folder)

    table.on("datatype-change", handle_datatype_change)

    install_css()

    if has_contrast_data:
        add_table_cell_template_contrast(table)
    else:
        add_table_cell_template_no_contrast(table)

    ui.button(
        "Add datatype",
        icon="add",
        on_click=lambda: add_datatype_dialog(
            project_folder,
            datatype_options,
            table,
            all_scans,
        ),
    )

    return table


def add_datatype_dialog(project_folder, datatype_options, table, all_scans):
    classification_config, config_path, settings_config, settings_path = load_classification_config(
        project_folder
    )

    rules = classification_config.get('datatype_rules', {})

    available_modalities = sorted({
        modality
        for rule in rules.values()
        for modality in rule.get('modality', [])
    })

    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('Add a new datatype').classes(
            'text-lg font-bold'
        )

        name_input = ui.input(
            label='Datatype name',
            placeholder='e.g. dwi'
        ).classes('w-full')

        description_input = ui.input(
            label='Description',
            placeholder='e.g. Diffusion weighted imaging'
        ).classes('w-full')

        modality_input = ui.select(
            options=available_modalities,
            label='Modalities',
            multiple=True,
            new_value_mode='add'
        ).props('use-input use-chips').classes('w-full')

        config_path_input = ui.input(
            label='New Classification Config File Name', 
            placeholder = 'new_class_config.json',
        )

        def save_datatype():
            name = (name_input.value or '').strip()
            description = (
                description_input.value or ''
            ).strip()

            modalities = modality_input.value or []
            modalities = list(dict.fromkeys(
                str(m).strip()
                for m in modalities
                if str(m).strip()
            ))

            if not name:
                ui.notify(
                    'Enter a datatype name',
                    type='warning'
                )
                return

            if name in rules:
                ui.notify(
                    'This datatype already exists',
                    type='warning'
                )
                return

            # Update the config through the config object
            rules[name] = {
                'description': description,
                'modality': modalities
            }
            classification_config.set('datatype_rules', rules)

            saving_config_name = config_path_input.value if config_path_input.value else config_path
            saving_config_path = Path(__file__).resolve().parent / "classification_configs" / saving_config_name

            try:
                classification_config.save_to_file(saving_config_path)
                settings_config.classification_config = str(saving_config_name)
                settings_config.save_to_file(settings_path)
            except (OSError, ValueError) as exc:
                del rules[name]
                ui.notify(
                    f'Could not save classification config: {exc}',
                    type='negative'
                )
                return

            # Refresh the datatype options stored on the table.
            
            # Reload the saved classification configuration.
            config, _, _, _ = load_classification_config(project_folder)

            datatype_options = list(config.get("datatype_rules", {}).keys())

            # Update the options used by the table and future filter menus.
            table._curation_datatype_options = datatype_options

            # Refresh row dropdowns and apply the existing filters.
            refresh_table(table, all_scans, datatype_options)

            # Rebuild the filter menus so the new datatype appears.
            rebuild_filter_buttons(
                table._curation_filter_buttons,
                table,
                all_scans,
            )

            ui.notify(f'Datatype "{name}" added')
            dialog.close()


        with ui.row().classes('justify-end w-full'):
            ui.button('Cancel', on_click=dialog.close)
            ui.button('Save', on_click=save_datatype)

    dialog.open()


def install_css():
    ui.add_head_html("""
        <style>
        .q-field__label {
            font-size: 20px;
        }
        </style>
        """)


def add_table_cell_template_contrast(table):
    with table.add_slot('body-cell-Proposed Filename', r'''
        <q-td :props="props">
            <div class="row items-center no-wrap gap-2">

                <span
                    :style="props.row.manual_inspection === 'Done'
                        ? 'color: #9333ea !important;'
                        : ''"
                    :class="props.row.manual_inspection !== 'Done'
                        ? (
                            props.value &&
                            props.value.toLowerCase().includes('t1w') &&
                            props.row.gad_manual === 'To Do'
                                ? 'bg-amber-5 text-black q-pa-xs'
                                : props.row.gad_manual === 'Gad'
                                    ? 'text-green-8 q-pa-xs'
                                    : props.row.gad_manual === 'Not GAD'
                                        ? 'text-blue-7 q-pa-xs'
                                        : ''
                        )
                        : 'q-pa-xs'"
                >
                    {{ props.value }}
                </span>

                <q-icon
                    v-if="props.row.notes && props.row.notes.length > 0"
                    name="note"
                    color="blue-4"
                    size="16px"
                >
                    <q-tooltip>Has notes</q-tooltip>
                </q-icon>

            </div>
        </q-td>
    '''):
        pass



def add_table_cell_template_no_contrast(table):
    with table.add_slot('body-cell-Proposed Filename', r'''
        <q-td :props="props">
            <div class="row items-center no-wrap gap-2">

                <span
                    :style="props.row.manual_inspection === 'Done'
                        ? 'color: #9333ea !important;'
                        : ''"
                >
                    {{ props.value }}
                </span>

                <q-icon
                    v-if="props.row.notes && props.row.notes.length > 0"
                    name="note"
                    color="blue-4"
                    size="16px"
                >
                    <q-tooltip>Has notes</q-tooltip>
                </q-icon>

            </div>
        </q-td>
    '''):
        pass


# =========================================================
# 3. ROW CLICK HANDLER
# =========================================================

def register_row_click(table, all_scans, project_folder):
    table.on('row-click', lambda e: open_editor(e, all_scans, table, project_folder))


# =========================================================
# 4. EDITOR ENTRY POINT
# =========================================================

def open_editor(e, all_scans, table, project_folder):
    
    row = e.args[1]
    idx = row['_idx']
    scan = all_scans[idx]

    original_state = scan['_original_state']

    dialog = ui.dialog()

    with dialog, ui.card().classes('w-[80vm] max-w-full'):
        build_editor(scan, all_scans, table, dialog, original_state, project_folder)

    dialog.open()


def apply_scan_changes(scan, orientation, scan_seq, contrast, modality, run, gad, manual_inspection, notes, filename):
    scan['Orientation'] = orientation
    scan['scan_seq'] = scan_seq
    scan['Contrast'] = contrast
    scan['Modality'] = modality
    scan['run'] = run
    scan['gad_manual'] = gad
    scan['manual_inspection'] = manual_inspection
    scan['notes'] = notes
    scan['Proposed Filename'] = filename




def refresh_table(table, all_scans, datatype_options=None):
    if datatype_options is None:
        datatype_options = getattr(
            table,
            "_curation_datatype_options",
            None,
        )

    if datatype_options is None:
        current_rows = table.rows or []
        datatype_options = (
            current_rows[0].get("_datatype_options", [])
            if current_rows
            else []
        )

    # Preserve the datatype options for future refreshes.
    table._curation_datatype_options = datatype_options

    apply_table_filters(
        table,
        all_scans,
        datatype_options,
    )


# =========================================================
# 5. EDITOR UI
# =========================================================

def build_editor(scan, all_scans, table, dialog, original_state, project_folder):

    state = {
        "is_resetting": False
    }

    with ui.row().classes('w-full no-wrap'):
        build_metadata_panel(scan)

        with ui.column().classes('w-1/2 gap-3'):
            build_filename_panel(scan, original_state)
            controls = build_controls_panel(scan, project_folder)

            bind_control_logic(controls, scan, original_state, state, table, all_scans, dialog, project_folder)

def build_metadata_panel(scan):
    with ui.column().classes('w-1/2 max-h-[500px] overflow-y-auto'):
        ui.label('Metadata').classes('text-md font-semibold')

        for key in FIELD_ORDER:
            if key in scan:
                with ui.row().classes('justify-between w-full text-sm'):
                    ui.label(str(key)).classes('text-gray-600')
                    ui.label(str(scan[key])).classes('text-right')

def build_filename_panel(scan, original_state):
    ui.label('Filenames').classes('text-md font-semibold')

    ui.label('Original Filename').classes('text-gray-600')
    ui.label(scan['Original Filename'])
    with ui.row().classes('justify-end'):
        ui.label('1st Version Proposed Filename').classes('text-gray-600')
        ui.label(f"Rule Trace: {scan['rule_trace']}").classes('text-xs text-gray-400')
    ui.label(original_state['Proposed Filename']).classes('text-sm break-all')



def build_controls_panel(scan, project_folder):

    settings_path = os.path.join(project_folder, 'project_settings.json')

    settings = SettingsConfig()
    settings.load_from_file(settings_path)

    has_contrast_data = settings.get("has_contrast_data", False)

    
    with ui.row().classes('w-full gap-2'):
        orientation = ui.input(
            label='Orientation',
            value=scan.get('Orientation') or ''
        ).classes('flex-1')

        scan_seq = ui.input(
            label='Scanning Sequence',
            value=scan.get('scan_seq') or ''
        ).classes('flex-1')

    with ui.row().classes('w-full gap-2 no-wrap'):
        contrast_val = (scan.get('Contrast') or '').rstrip('_')
        run_val = (scan.get('run') or '').rstrip('_')

        contrast = ui.input(
            label='Contrast',
            value=contrast_val
        ).classes('flex-1 min-w-0')

        modality = ui.input(
            label='Modality',
            value=scan.get('Modality') or ''
        ).classes('flex-1 min-w-0')

        run = ui.input(
            label='Run',
            value=run_val
        ).classes('flex-1 min-w-0')


    if has_contrast_data:
        with ui.row().classes('items-center gap-4'):
            ui.label('Gadolinium Manual Check').classes('text-sm text-gray-600')

            gad_toggle = ui.toggle(
                ['To Do', 'Gad', 'Not GAD'],
                value='To Do'
            )    
            gad_toggle.value = (
                scan.get('gad_manual')
            )
    else:
        # ensure gad_toggle always exists; use a simple dummy object with a .value
        gad_toggle = type('DummyToggle', (), {'value': ''})()

    with ui.row().classes('items-center gap-4'):
        ui.label('Image Name Check').classes(
            'text-sm text-gray-600'
        )

        manual_inspection = ui.toggle(
            ['To Do', 'Done'],
            value=scan.get('manual_inspection', 'To Do')
        )

    filename_input = ui.input(
        label='Proposed Filename - You can EDIT',
        value=scan['Proposed Filename']
    ).classes('w-full text-sm')

    ui.label('Notes').classes('text-sm text-gray-600')
    notes_input = ui.textarea(
        value=scan.get('notes', ''),
        placeholder='Write notes about this scan...'
    ).props('autogrow dense outlined').classes('w-full')

    

    return {
        "orientation": orientation,
        "scan_seq": scan_seq,
        "contrast": contrast,
        "modality": modality,
        "run": run,
        "gad_toggle": gad_toggle,
        "manual_inspection": manual_inspection,
        "filename_input": filename_input,
        "notes_input": notes_input
    }

 # when saving, store the internal values expected by filename builder (with underscores)
def add_trailing_underscore(v):
    v = str(v or '')
    return f"{v}_" if v and not v.endswith('_') else v

def bind_control_logic(controls, scan, original_state, state, table, all_scans, dialog, project_folder):

    
    def clean_value(value):
        """Remove accidental whitespace around an input value."""
        return str(value or '').strip()

    def update_filename(changed_key=None, changed_value=None):
        if state["is_resetting"]:
            return

        # Read the current values from every control.
        values = {
            key: clean_value(controls[key].value)
            for key in ["orientation", "scan_seq", "contrast", "modality", "run"]
        }

        # Use the newest value from the event itself.
        # This avoids rebuilding the filename with stale input.
        if changed_key is not None:
            values[changed_key] = clean_value(changed_value)

        controls["filename_input"].value = build_filename(
            sub=scan.get('Sub', ''),
            ses=scan.get('Ses', ''),
            orientation=values["orientation"],
            scan_seq=values["scan_seq"],
            contrast=add_trailing_underscore(values["contrast"]),
            run=add_trailing_underscore(values["run"]),
            modality=values["modality"],
            ext='.json',
            repeat=scan.get('Repeat', '')
        )

    # --- Input bindings ---
    for key in ["orientation", "scan_seq", "contrast", "modality", "run"]:
        controls[key].on(
            'update:model-value',
            lambda e, k=key: update_filename(k, e.args)
        )


    # --- reset ---
    def reset():
        state["is_resetting"] = True

        for key in ["Orientation", "scan_seq", "Contrast", "Modality", "run"]:
            # controls should show values without trailing underscores
            ctl_key = key.lower()
            if key in ("Contrast", "run"):
                controls[ctl_key].value = (original_state[key] or '').rstrip('_')
            else:
                controls[ctl_key].value = original_state[key]
            # keep scan internal state as the original (may include underscores)
            scan[key] = original_state[key]

        controls["filename_input"].value = build_filename(
            sub = scan.get('Sub', ''),
            ses = scan.get('Ses', ''), 
            orientation = original_state["Orientation"], 
            scan_seq = original_state["scan_seq"], 
            contrast = original_state["Contrast"], 
            run = original_state['run'], 
            modality = original_state["Modality"],
            ext='.json', 
            repeat = scan.get('Repeat', '')
        )

        
        state["is_resetting"] = False

    # --- save ---
    def save():

        apply_scan_changes(
            scan,
            clean_value(controls["orientation"].value),
            clean_value(controls["scan_seq"].value),
            add_trailing_underscore(clean_value(controls["contrast"].value)),
            clean_value(controls["modality"].value),
            add_trailing_underscore(clean_value(controls["run"].value)),
            controls["gad_toggle"].value,
            controls["manual_inspection"].value,
            controls["notes_input"].value,
            controls["filename_input"].value
        )

        refresh_table(table, all_scans)
        print("Manual inspection status:", scan.get("manual_inspection"))
        dialog.close()

    with ui.row().classes('justify-end'):
        ui.button('Cancel', on_click=dialog.close)
        ui.button('Save', on_click=save)
        ui.button('Reset', on_click=reset, color='red')
        ui.button(
            'Classification Rules',
            on_click=lambda:
                open_classification_rules_editor(
                    project_folder
                ), color='light-green-8'
        )

def export_csv(all_scans,project_folder):
    import pandas as pd

    csv_path = os.path.join(project_folder, 'session_data.csv')


    df = pd.DataFrame(all_scans)
    df.to_csv(csv_path, index=False)

# =========================================================
# 6. BOTTOM CONTROLS
# =========================================================

def create_bottom_controls(all_scans, table, project_folder):

    settings_path = os.path.join(project_folder, 'project_settings.json')

    settings = SettingsConfig()
    settings.load_from_file(settings_path)

    def rebuild():
        build_all_filenames(all_scans)
        refresh_table(table, all_scans)




    with ui.row().classes('gap-2'):
        ui.button('Export CSV', on_click=lambda:
                        export_csv(all_scans, project_folder))
        ui.button(
            'Classification Rules',
            on_click=lambda:
                open_classification_rules_editor(
                    project_folder
                ), color = 'light-green-8'
            )