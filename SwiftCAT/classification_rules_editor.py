# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

from nicegui import ui
from pathlib import Path
from classification_config import ClassificationConfig
from project_settings_config import SettingsConfig
import os
import copy
import json

SEQUENCE_FIELDS = [
    {
        "key": "description",
        "label": "Description",
        "field_type": "text",
        "default":"",
    },
    {
        "key": "requires_inversion",
        "label": "Requires inversion",
        "field_type": "bool",
        "default":False,
    },
    {
        "key": "flags",
        "label": "ScanningSequence Flags",
        "field_type": "list",
        "default":[],
    },
    {
        "key": "sequence_keywords",
        "label": "Fallback Keywords",
        "field_type": "list",
        "default":[],
    },
]


ORIENTATION_FIELDS = [
    {
        "key": "plane",
        "label": "Plane",
        "field_type": "text",
        "default":"",
    },
    {
        "key": "mr_acquisition_type",
        "label": "MR Acquisition Type",
        "field_type": "list",
        "default":[],
    },
    {
        "key": "code",
        "label": "Code",
        "field_type": "text",
        "default":"",
    },
]

CONTRAST_FIELDS = [
    {
        "key": "include",
        "label": "Include",
        "field_type": "list",
        "default":[],
    },
    {
        "key": "exclude",
        "label": "Exclude",
        "field_type": "list",
        "default":[],
    },
]

FALLBACK_FIELDS = [
    {
        "key": "scan_seq",
        "label": "Input Sequence",
        "field_type": "text",
        "default": "",
    },
    {
        "key": "modality",
        "label": "Modality",
        "field_type": "text",
        "default": "",
    },
    {
        "key": "result",
        "label": "Output Sequence",
        "field_type": "text",
        "default": "",
    },
]

def open_classification_rules_editor(project_folder):

    settings_path = os.path.join(project_folder, 'project_settings.json')

    settings_config = SettingsConfig()
    settings_config.load_from_file(settings_path)

    classification_config_filename = settings_config.classification_config
    base_dir = Path(__file__).resolve().parent
    class_config_path = base_dir / "classification_configs" / classification_config_filename
    default_class_config_path = base_dir / "classification_configs" / "class_config_default.json" 
    config = ClassificationConfig()
    config.load_from_file(class_config_path)
    default_config = ClassificationConfig()
    default_config.load_from_file(default_class_config_path)

    with ui.dialog() as dialog:

        with ui.card().classes(
            'w-[90vw] max-w-[1400px] h-[90vh]'
        ):
            
            

            ui.label(
                'Classification Rules'
            ).classes('text-xl font-bold')

            with ui.tabs().classes('w-full') as tabs:
                tab_sequence = ui.tab('Sequence')
                tab_orientation = ui.tab('Orientation')
                tab_contrast = ui.tab('Contrast')
                tab_modality = ui.tab('Modality')
                tab_fallback = ui.tab('Fallback')

            with ui.tab_panels(
                tabs,
                value=tab_sequence
            ).classes('w-full flex-grow'):

                with ui.tab_panel(tab_sequence):
                    sequence_table = build_editor(
                        config.get("sequence_rules", {}), 
                        default_config.get("sequence_rules", {}),
                        SEQUENCE_FIELDS, 
                        "Sequence")

                with ui.tab_panel(tab_orientation):
                    orientation_table = build_editor(
                        config.get("orientation_rules", {}),
                        default_config.get("orientation_rules", {}),
                        ORIENTATION_FIELDS,
                        "Orientation")

                with ui.tab_panel(tab_contrast):
                    contrast_table = build_editor(
                        config.get("contrast_keywords", {}),
                        default_config.get("contrast_keywords", {}),
                        CONTRAST_FIELDS,
                        "Contrast")

                with ui.tab_panel(tab_modality):
                    modality_rules = config.get("modality_rules", [])
                    modality_table = build_modality_editor(modality_rules)
                
                with ui.tab_panel(tab_fallback):
                    fallback_table = build_editor(
                        config.get("fallback_rules", {}),
                        default_config.get("fallback_rules", {}),
                        FALLBACK_FIELDS,
                        "Fallback")

            new_config_file=ui.input(label='New Classification Config File Name', value="New_config_filename.json").classes('w-full text-sm')

            def save():
                class_config_path = base_dir / "classification_configs" / new_config_file.value
                config.save_to_file(class_config_path)

                settings_config.classification_config = new_config_file.value
                settings_config.save_to_file(settings_path)

                ui.notify(
                    'Classification rules saved',
                    color='positive'
                )

                dialog.close()

            def reset_all_rules():
                config.reset_to_defaults()

                sequence_table.rows = build_rows(config.get("sequence_rules", {}), SEQUENCE_FIELDS)
                sequence_table.update()

                orientation_table.rows = build_rows(config.get("orientation_rules", {}), ORIENTATION_FIELDS)
                orientation_table.update()

                contrast_table.rows = build_rows(config.get("contrast_keywords", {}), CONTRAST_FIELDS)
                contrast_table.update()

                modality_table.rows = build_modality_rows(modality_rules)
                modality_table.update()

                fallback_table.rows = build_rows(config.get("fallback_rules", {}), FALLBACK_FIELDS)
                fallback_table.update()

                settings_config.classification_config_reset_default()
                settings_config.save_to_file(settings_path)


            with ui.row().classes('justify-end w-full'):
                ui.button(
                    'Cancel & Close',
                    on_click=dialog.close
                )


                ui.button(
                    'Save Config File',
                    on_click=save
                )

                ui.button(
                    'Reset to Default Rules',
                    on_click=lambda: reset_all_rules(),
                    color='red'
                )

    dialog.open()

def build_rows(rules, fields):

    rows = []

    for name, rule in rules.items():

        row = {"Name": name}

        for field in fields:

            value = rule.get(field["key"], field["default"])

            if field["field_type"] == "list":
                value = ",".join(value)

            row[field["label"]] = value

        rows.append(row)

    return rows


def build_modality_rows(rules):
    """Flatten modality rules into rows suitable for NiceGUI's table."""

    rows = []

    for rule in rules:
        conditions = rule.get("conditions", {})

        def limits(field):
            condition = conditions.get(field, {})
            minimum = condition.get("min")
            maximum = condition.get("max")
            return (
                "" if minimum is None else str(minimum),
                "" if maximum is None else str(maximum),
            )

        te_min, te_max = limits("EchoTime")
        tr_min, tr_max = limits("RepetitionTime")
        fa_min, fa_max = limits("FlipAngle")

        rows.append({
            "Name": rule.get("name", ""),
            "Description": rule.get("description", ""),
            "Modality": rule.get("modality", ""),
            "Sequence": rule.get("sequence", ""),
            "Inversion": rule.get("requires_inversion", False),
            "TE min": te_min,
            "TE max": te_max,
            "TR min": tr_min,
            "TR max": tr_max,
            "FA min": fa_min,
            "FA max": fa_max,
        })

    return rows


def open_modality_rule_editor(rule, rules, table):
    """Open an editor for a single modality rule."""

    with ui.dialog() as dlg:
        with ui.card().classes(
            "w-[900px] max-w-[95vw] max-h-[90vh]"
        ):
            with ui.column().classes("w-full overflow-auto"):

                ui.label("Edit Modality Rule").classes(
                    "text-lg font-bold"
                )

                name_input = ui.input(
                    "Name",
                    value=rule.get("name", ""),
                ).classes("w-full")

                description_input = ui.input(
                    "Description",
                    value=rule.get("description", ""),
                ).classes("w-full")

                modality_input = ui.input(
                    "Output Modality",
                    value=rule.get("modality", ""),
                ).classes("w-full")

                sequence_input = ui.input(
                    "Sequence (optional)",
                    value=rule.get("sequence", ""),
                ).classes("w-full")

                inversion_checkbox = ui.checkbox(
                    "Requires inversion",
                    value=rule.get("requires_inversion", False),
                )

                forbid_inversion_checkbox = ui.checkbox(
                    "Forbid inversion",
                    value=rule.get("forbid_inversion", False),
                )

                ui.label("Numeric Conditions").classes(
                    "text-md font-bold mt-2"
                )

                conditions = rule.get("conditions", {})

                numeric_inputs = {}

                with ui.grid(columns=3).classes("w-full"):
                    for field_name in (
                        "EchoTime (seconds)",
                        "RepetitionTime (seconds)",
                        "FlipAngle (degrees)",
                    ):
                        condition = conditions.get(field_name, {})

                        ui.label(field_name).classes(
                            "font-medium self-center"
                        )

                        numeric_inputs[(field_name, "min")] = ui.input(
                            "Min",
                            value=(
                                "" if condition.get("min") is None
                                else str(condition["min"])
                            ),
                        )

                        numeric_inputs[(field_name, "max")] = ui.input(
                            "Max",
                            value=(
                                "" if condition.get("max") is None
                                else str(condition["max"])
                            ),
                        )

                def keyword_input(label, key):
                    return ui.input(
                        label,
                        value=", ".join(rule.get(key, [])),
                    ).classes("w-full")

                contrast_input = keyword_input(
                    "Contrast keywords (optional, comma-separated)",
                    "contrast_keywords",
                )

                exclude_input = keyword_input(
                    "Excluded contrast keywords (optional, comma-separated)",
                    "contrast_exclude_keywords",
                )

                override_input = ui.input(
                    "Scan sequence override (optional)",
                    value=rule.get("scan_seq_override", ""),
                ).classes("w-full")

                sequence_conditions_input = ui.textarea(
                    label="Sequence conditions (optional, JSON list)",
                    value=json.dumps(
                        rule.get("sequence_conditions", []),
                        indent=2,
                    ),
                ).classes("w-full")

                def parse_number(value, field, bound):
                    value = value.strip()

                    if not value:
                        return None

                    try:
                        return float(value)
                    except ValueError:
                        raise ValueError(
                            f"{field} {bound} must be a number or empty."
                        )

                def parse_keywords(value):
                    return [
                        item.strip()
                        for item in value.split(",")
                        if item.strip()
                    ]

                def apply():
                    new_name = name_input.value.strip()
                    old_name = rule.get("name", "")

                    if not new_name:
                        ui.notify(
                            "Name cannot be empty",
                            color="negative",
                        )
                        return

                    if any(
                        other is not rule
                        and other.get("name") == new_name
                        for other in rules
                    ):
                        ui.notify(
                            "A rule with this name already exists",
                            color="negative",
                        )
                        return

                    try:
                        new_conditions = {}

                        for field_name in (
                            "EchoTime",
                            "RepetitionTime",
                            "FlipAngle",
                        ):
                            minimum = parse_number(
                                numeric_inputs[
                                    (field_name, "min")
                                ].value,
                                field_name,
                                "minimum",
                            )
                            maximum = parse_number(
                                numeric_inputs[
                                    (field_name, "max")
                                ].value,
                                field_name,
                                "maximum",
                            )

                            if minimum is not None or maximum is not None:
                                new_conditions[field_name] = {
                                    "min": minimum,
                                    "max": maximum,
                                }

                        sequence_conditions = json.loads(
                            sequence_conditions_input.value or "[]"
                        )

                        if not isinstance(sequence_conditions, list):
                            raise ValueError(
                                "Sequence conditions must be a JSON list."
                            )

                        if not all(
                            isinstance(item, dict)
                            for item in sequence_conditions
                        ):
                            raise ValueError(
                                "Each sequence condition must be a JSON object."
                            )

                    except (ValueError, TypeError) as error:
                        ui.notify(str(error), color="negative")
                        return

                    # Update the existing dictionary in place.
                    # Unknown/custom rule fields are preserved.
                    rule["name"] = new_name
                    rule["description"] = description_input.value
                    rule["modality"] = modality_input.value.strip()
                    rule["requires_inversion"] = inversion_checkbox.value

                    rule["conditions"] = new_conditions

                    # Remove optional fields when left empty.
                    optional_text_fields = {
                        "sequence": sequence_input.value.strip(),
                        "scan_seq_override": override_input.value.strip(),
                    }

                    for key, value in optional_text_fields.items():
                        if value:
                            rule[key] = value
                        else:
                            rule.pop(key, None)

                    if forbid_inversion_checkbox.value:
                        rule["forbid_inversion"] = True
                    else:
                        rule.pop("forbid_inversion", None)

                    for key, value in (
                        ("contrast_keywords", contrast_input.value),
                        (
                            "contrast_exclude_keywords",
                            exclude_input.value,
                        ),
                    ):
                        keywords = parse_keywords(value)
                        if keywords:
                            rule[key] = keywords
                        else:
                            rule.pop(key, None)

                    if sequence_conditions:
                        rule["sequence_conditions"] = sequence_conditions
                    else:
                        rule.pop("sequence_conditions", None)

                    table.rows = build_modality_rows(rules)
                    table.update()
                    dlg.close()

                with ui.row().classes("justify-end w-full"):
                    ui.button("Cancel", on_click=dlg.close)

                    ui.button(
                        "Save Changes",
                        on_click=apply,
                    )

                    ui.button(
                        "Delete Rule",
                        color="negative",
                        on_click=lambda: delete_modality_rule(
                            rule, rules, table, dlg
                        ),
                    )

    dlg.open()


def delete_modality_rule(rule, rules, table, dlg):
    rules.remove(rule)
    table.rows = build_modality_rows(rules)
    table.update()
    dlg.close()


def add_modality_rule(rules, table):
    base_name = "NEW_MODALITY_RULE"
    name = base_name
    counter = 1

    existing_names = {
        rule.get("name") for rule in rules
    }

    while name in existing_names:
        name = f"{base_name}_{counter}"
        counter += 1

    new_rule = {
        "name": name,
        "description": "",
        "requires_inversion": False,
        "conditions": {},
        "modality": "",
    }

    rules.append(new_rule)

    table.rows = build_modality_rows(rules)
    table.update()

    open_modality_rule_editor(new_rule, rules, table)


def build_modality_editor(rules):
    columns = [
        {"name": key, "label": key, "field": key}
        for key in [
            "Name",
            "Description",
            "Modality",
            "Sequence",
            "Inversion",
            "TE min",
            "TE max",
            "TR min",
            "TR max",
            "FA min",
            "FA max",
        ]
    ]

    table = ui.table(
        columns=columns,
        rows=build_modality_rows(rules),
        row_key="Name",
    ).classes("w-full")

    table.on(
        "row-click",
        lambda e: open_modality_rule_editor(
            next(
                (
                    rule for rule in rules
                    if rule.get("name") == e.args[1]["Name"]
                ),
                None,
            ),
            rules,
            table,
        ) if any(
            rule.get("name") == e.args[1]["Name"]
            for rule in rules
        ) else None,
    )

    with ui.row():
        ui.button(
            "Add Modality Rule",
            on_click=lambda: add_modality_rule(rules, table),
        )

    return table



def delete_rule(row, rules, table, dlg, fields):

    del rules[row["Name"]]

    table.rows = build_rows(rules, fields)
    table.update()

    dlg.close()

def add_rule(rules, table, fields):

    base_name = "NEW_RULE"
    name = base_name
    counter = 1

    while name in rules:
        name = f"{base_name}_{counter}"
        counter += 1

    new_rule = {}

    for field in fields:
        new_rule[field["key"]] = copy.deepcopy(field["default"])

    rules[name] = new_rule

    table.rows = build_rows(rules, fields)
    table.update()

    row = {"Name": name}

    for field in fields:

        value = new_rule[field["key"]]

        if field["field_type"] == "list":
            value = ",".join(value)

        row[field["label"]] = value

    open_rule_editor(row, table, rules, fields)


def open_rule_editor(row, table, rules, fields):

    with ui.dialog() as dlg:

        with ui.card().classes('w-[800px] max-w-[90vw] max-h-[90vh]'):#w-[700px]'):

            with ui.column().classes('w-full overflow-auto'):

                name_input = ui.input(
                                'Name',
                                value=row["Name"]
                            ).classes('w-full text-sm')

                rule = rules[row["Name"]]

                widgets = {}

                for field in fields:

                    value = rule.get(field["key"], field["default"])

                    if field["field_type"] == "bool":

                        widgets[field["key"]] = ui.checkbox(
                            field["label"],
                            value=value,
                        )

                    else:

                        if field["field_type"] == "list":
                            value = ",".join(value)

                        widgets[field["key"]] = ui.input(
                            field["label"],
                            value=value,
                        ).classes('w-full text-sm')

            def apply():

                old_name = row["Name"]
                new_name = name_input.value.strip()

                if not new_name:
                    ui.notify(
                        'Name cannot be empty',
                        color='red'
                    )
                    return

                if (
                    new_name != old_name
                    and new_name in rules
                ):
                    ui.notify(
                        'A rule with this name already exists',
                        color='negative'
                    )
                    return

                rule = rules[old_name]

                for field in fields:

                    value = widgets[field["key"]].value

                    if field["field_type"] == "list":
                        value = [
                            x.strip()
                            for x in value.split(",")
                            if x.strip()
                        ]

                    rule[field["key"]] = value

                if new_name != old_name:
                    rules[new_name] = rule
                    del rules[old_name]

                table.rows = build_rows(rules, fields)

                table.update()

                dlg.close()

            with ui.row():

                ui.button(
                    'Back',
                    on_click=dlg.close,
                    color = 'grey-6'
                )

                ui.button(
                    'Save Changes',
                    on_click=apply
                )

                ui.button(
                    'Delete Rule',
                    color='negative',
                    on_click=lambda: delete_rule(
                        row,
                        rules,
                        table,
                        dlg,
                        fields
                    )
                )

    dlg.open()

def build_editor(rules, default_rules, fields, rule_name):

    columns = [
        {
            "name": k,
            "label": k,
            "field": k
        }
        for k in ["Name"] + [f["label"] for f in fields]
    ]

    table = ui.table(
        columns=columns,
        rows=build_rows(rules, fields)
    ).classes('w-full h-full')


    table.on(
        'row-click',
        lambda e: open_rule_editor(e.args[1], table, rules, fields)
    )


    with ui.row():
        ui.button(
            f'Add {rule_name} Rule',
            on_click=lambda: add_rule(rules, table, fields)
        )

    return table