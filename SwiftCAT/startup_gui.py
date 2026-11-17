# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

import os
import json
import pandas as pd
from pathlib import Path
from nicegui import run, ui
from names_curation import build_mapping_duplicates_control
import ast
from project_settings_config import SettingsConfig
from classification_config import ClassificationConfig
from preprocessing.input_detection import detect_input_type, InputType
from preprocessing.folder_anonymizer import anonymize_dataset
from preprocessing.dicom_converter import convert_dicom_to_nifti
from preprocessing.organize_folders_bids import organize_dataset
import shutil
import time
from datetime import datetime, timezone
import asyncio
import traceback

RECENT_INPUT_FOLDER_FILE = "recent_input_folders.json"
RECENT_PROJECT_FOLDER_FILE = "recent_project_folders.json"
RECENT_CSV_FILE = "recent_csvs.json"
RECENT_JSON_FILE = "recent_jsons.json"
# =========================================================
# ENTRY POINT
# =========================================================

def startup_screen(container):

    state = {
        'mode': None,
        'folder': '',
        'csv': '',
        'json': '',
        'has_contrast_data': True,
        'project_folder':'',
        'orientation_settings':'dimensionality'
    }

    with container:
        ui.label('SwiftCAT').classes('text-3xl font-bold')
        ui.label('Swift MRI Curation and Annotation Tool').classes('text-xl font-bold')

        content = ui.column().classes('w-full items-center mt-6')

        build_mode_selector(content, state, container)

# =========================================================
# 1. FOLDER MODE
# =========================================================

def build_mode_selector(content, state, container):

    with content:

        ui.label('Choose an option').classes('text-xl font-semibold')

        with ui.row().classes('gap-6 mt-4'):

            ui.button(
                'Start New Project',
                on_click=lambda: show_new_project(content, state, container)
            ).classes('w-64 h-20 text-lg')

            ui.button(
                'Continue Project',
                on_click=lambda: show_continue_session(content, state, container),
                color = 'light-green-8'
            ).classes('w-64 h-20 text-lg')




def load_recent(file):
    if not Path(file).exists():
        return []
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return []


def save_recent(file, path, max_items=5):
    if not path:
        return

    recent = load_recent(file)

    if path in recent:
        recent.remove(path)

    recent.insert(0, path)
    recent = recent[:max_items]

    with open(file, "w") as f:
        json.dump(recent, f, indent=2)

def build_recent_ui(state, input, recent_files,label_str):

    ui.label(f"Recent {label_str}").classes("text-sm text-gray-500 mt-2")

    recent = load_recent(recent_files)

    if not recent:
        ui.label(f"No recent {label_str} yet").classes("text-xs text-gray-400")
        return

    with ui.row().classes("gap-2 flex-wrap"):

        for path in recent:

            ui.button(
                path,
                on_click=lambda p=path: (
                    setattr(input, "value", p),
                    state.update({f"{label_str}": p})
                )
            ).props("outline dense")


def show_new_project(content, state, container):
    content.clear()

    state["input_type"] = "nifti"
    state["folder"] = ""
    state["project_folder"] = ""
    state["datafolder"] = ""

    with content:
        ui.label("Start New Project").classes(
            "text-xl font-semibold"
        )

        # --------------------------------------------------
        # STEP 1: Choose the input type
        # --------------------------------------------------
        ui.label("What type of input data do you have?").classes(
            "text-sm text-gray-600"
        )

        input_type = ui.radio(
            {
                "dicom": "DICOM",
                "nifti": "NIfTI",
            },
            value="nifti",
        ).props("inline")

        # --------------------------------------------------
        # STEP 2: Select input and output folders
        # --------------------------------------------------
        folder_input = ui.input(
            label="Input Data Folder Path",
            placeholder="/path/to/input/data",
        ).classes("w-[500px]")

        build_recent_ui(
            state,
            folder_input,
            RECENT_INPUT_FOLDER_FILE,
            "Folders",
        )

        folder_output = ui.input(
            label="Output Project Folder Path",
            placeholder="/path/to/output/project",
        ).classes("w-[500px]")

        # The following elements are shown only after
        # checking the selected input.
        workflow = ui.column().classes("w-full items-center")

        async def check_input():
            input_path = Path(folder_input.value or "").expanduser()

            if not input_path.is_dir():
                ui.notify("Invalid input folder path", type="negative")
                return

            if not folder_output.value:
                ui.notify(
                    "Please specify an output project folder",
                    type="warning",
                )
                return

            state["input_type"] = input_type.value
            state["folder"] = str(input_path)
            state["project_folder"] = str(
                Path(folder_output.value).expanduser()
            )

            save_recent(
                RECENT_INPUT_FOLDER_FILE,
                str(input_path),
            )

            # ----------------------------------------------
            # STEP 3: Detect and compare input type
            # ----------------------------------------------
            try:
                detected_type = detect_input_type(input_path)
            except Exception as e:
                ui.notify(
                    f"Could not detect input type: {e}",
                    type="negative",
                )
                return

            selected_enum = (
                InputType.DICOM
                if input_type.value == "dicom"
                else InputType.NIFTI
            )

            if detected_type != selected_enum:
                ui.notify(
                    "Warning: the detected input type is "
                    f"{detected_type}, but you selected "
                    f"{selected_enum}. Continuing with your "
                    "selected input type.",
                    type="warning",
                    timeout=8000,
                )

            workflow.clear()

            # ----------------------------------------------
            # STEP 4: Ask about anonymization for DICOM
            # ----------------------------------------------
            if input_type.value == "dicom":
                with workflow:
                    ui.label(
                        "Would you like to anonymize the DICOM data?"
                    ).classes("text-sm text-gray-600")

                    anonymize_choice = ui.radio(
                        {
                            True: "Yes, anonymize",
                            False: "No, skip anonymization",
                        },
                        value=True,
                    ).props("inline")

                    async def start_dicom_processing():
                        await process_dataset(
                            input_path=input_path,
                            project_path=Path(state["project_folder"]),
                            selected_type="dicom",
                            anonymize=anonymize_choice.value,
                            content=content,
                            workflow=workflow,
                            state=state,
                            container=container,
                        )

                    ui.button(
                        "Process DICOM Data",
                        on_click=start_dicom_processing,
                    ).classes("mt-3")

            else:
                # NIfTI: no anonymization or conversion.
                await process_dataset(
                    input_path=input_path,
                    project_path=Path(state["project_folder"]),
                    selected_type="nifti",
                    anonymize=False,
                    content=content,
                    workflow=workflow,
                    state=state,
                    container=container,
                )

        with ui.row().classes("mt-4 gap-4"):
            ui.button(
                "Back",
                on_click=lambda: reset_startup(
                    content, state, container
                ),
                color="grey-6",
            )

            ui.button(
                "Check Input and Continue",
                on_click=check_input,
            )

        # The workflow column must exist before check_input
        # is called so it can be populated dynamically.


def save_preprocessing_timings(
    project_path,
    selected_type,
    anonymize,
    timings,
    total_seconds,
    status,
    error=None,
):
    """Save preprocessing durations and status to JSON."""

    project_path = Path(project_path)
    timing_file = project_path / "preprocessing_timings.json"

    report = {
        "input_type": selected_type,
        "anonymization_requested": (
            anonymize if selected_type == "dicom" else False
        ),
        "status": status,
        "started_at": timings["started_at"],
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "total_seconds": round(total_seconds, 3),
        "stages": timings["stages"],
    }

    if error:
        report["error"] = str(error)

    with open(timing_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return timing_file


def preprocess_dataset_worker(
    input_path,
    project_path,
    selected_type,
    anonymize,
):
    """Run preprocessing without accessing NiceGUI elements."""

    input_path = Path(input_path).expanduser().resolve()
    project_path = Path(project_path).expanduser().resolve()

    if not input_path.is_dir():
        raise ValueError(f"Input folder does not exist: {input_path}")

    if (
        input_path == project_path
        or project_path in input_path.parents
    ):
        raise ValueError(
            "The project folder cannot be the input folder "
            "or a folder inside the input folder."
        )

    project_path.mkdir(parents=True, exist_ok=True)

    if selected_type == "dicom":

        if anonymize:
            anonymized_dir = project_path / "anonymized_dicoms"
            mappings_dir = project_path / "anonymization_mappings"

            if anonymized_dir.exists() or mappings_dir.exists():
                raise FileExistsError(
                    "Anonymization output already exists. "
                    "Choose a new project folder."
                )

            anonymized_dir.mkdir()
            mappings_dir.mkdir()

            result = anonymize_dataset(
                input_dataset=str(input_path),
                output_dataset=str(anonymized_dir),
                mapping_directory=str(mappings_dir),
            )

            if result.failed_files:
                raise RuntimeError(
                    f"{len(result.failed_files)} files failed "
                    "anonymization. Check the anonymization results."
                )

            dicom_input = Path(result.output_dataset)
        else:
            dicom_input = input_path

        nifti_dir = project_path / "nifti_converted"

        if nifti_dir.exists():
            raise FileExistsError(
                f"Conversion directory already exists: {nifti_dir}"
            )

        nifti_dir.mkdir()

        result = convert_dicom_to_nifti(
            input_directory=dicom_input,
            output_directory=nifti_dir,
        )

        if not result.nifti_files:
            raise RuntimeError(
                "DICOM conversion did not produce any NIfTI files."
            )

        datafolder = Path(result.output_directory)

    elif selected_type == "nifti":

        datafolder = project_path / "nifti_dataset"

        if datafolder.exists():
            raise FileExistsError(
                f"Working copy already exists: {datafolder}"
            )

        shutil.copytree(input_path, datafolder)

    else:
        raise ValueError(f"Unsupported input type: {selected_type}")

    organize_dataset(datafolder)

    return str(datafolder)



async def process_dataset(
    input_path,
    project_path,
    selected_type,
    anonymize,
    content,
    workflow,
    state,
    container,
):
    """Preprocess data with live progress and per-stage timings."""

    input_path = Path(input_path).expanduser().resolve()
    project_path = Path(project_path).expanduser().resolve()

    if not input_path.is_dir():
        ui.notify("Input folder does not exist", type="negative")
        return

    if (
        input_path == project_path
        or project_path in input_path.parents
    ):
        ui.notify(
            "The project folder cannot be the input folder "
            "or a folder inside the input folder.",
            type="negative",
        )
        return

    # Number of stages depends on the selected workflow.
    if selected_type == "dicom":
        stage_total = 3 if anonymize else 2
    elif selected_type == "nifti":
        stage_total = 2
    else:
        ui.notify(
            f"Unsupported input type: {selected_type}",
            type="negative",
        )
        return

    def format_time(seconds):
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    project_path.mkdir(parents=True, exist_ok=True)


    total_start = time.monotonic()
    clock_state = {
        "stage": "Preparing dataset",
        "stage_start": total_start,
    }
    timings = []
    timing_report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stages": [],
    }

    progress_state = {
        "fraction": 0.0,
        "detail": "",
    }
    completed_stages = 0

    # --------------------------------------------------
    # PROGRESS UI
    # --------------------------------------------------
    with content:
        progress_panel = ui.card().classes("w-full max-w-2xl mt-4")
        with progress_panel:
            ui.label("Dataset preprocessing").classes(
                "text-lg font-semibold"
            )

            stage_label = ui.label("Preparing dataset...")
            progress = ui.linear_progress(
                value=0,
                show_value=False,
            ).classes("w-full")

            progress_detail_label = ui.label(
                ""
            ).classes("text-sm text-gray-500")

            progress_text = ui.label(
                f"0 of {stage_total} stages completed"
            ).classes("text-sm text-gray-500")

            total_time_label = ui.label(
                "Total elapsed: 00:00"
            ).classes("text-sm")

            stage_time_label = ui.label(
                "Current stage elapsed: 00:00"
            ).classes("text-sm")

            timing_summary = ui.column().classes("w-full gap-1")

    def update_clock():
        now = time.monotonic()

        total_time_label.set_text(
            f"Total elapsed: {format_time(now - total_start)}"
        )

        stage_time_label.set_text(
            f"Current stage elapsed: "
            f"{format_time(now - clock_state['stage_start'])}"
        )

        # Progress within the current stage, when available.
        overall_progress = (
            completed_stages + progress_state["fraction"]
        ) / stage_total

        progress.set_value(min(overall_progress, 1.0))

        if progress_state["detail"]:
            progress_detail_label.set_text(
                progress_state["detail"]
            )

    clock = ui.timer(1.0, update_clock)

    async def run_stage(label, func, *args, **kwargs):
        nonlocal completed_stages

        clock_state["stage"] = label
        clock_state["stage_start"] = time.monotonic()

        progress_state["fraction"] = 0.0
        progress_state["detail"] = ""

        stage_label.set_text(f"{label}...")
        update_clock()

        started = time.monotonic()
        success = False

        try:
            result = await run.io_bound(
                func, *args, **kwargs
            )
            success = True
            return result

        finally:
            elapsed = time.monotonic() - started

            timings.append((label, elapsed))
            timing_report["stages"].append({
                "name": label,
                "seconds": round(elapsed, 3),
                "status": "completed" if success else "failed",
            })

            if success:
                completed_stages += 1

            progress_state["fraction"] = 0.0
            progress_state["detail"] = ""
            update_clock()

    try:
        # --------------------------------------------------
        # DICOM WORKFLOW
        # --------------------------------------------------
        if selected_type == "dicom":

            if anonymize:
                anonymized_dir = (
                    project_path / "anonymized_dicoms"
                )
                mappings_dir = (
                    project_path / "anonymization_mappings"
                )

                if (
                    anonymized_dir.exists()
                    or mappings_dir.exists()
                ):
                    raise FileExistsError(
                        "Anonymization output already exists. "
                        "Choose a new project folder."
                    )

                anonymized_dir.mkdir()
                mappings_dir.mkdir()

                result = await run_stage(
                    "Anonymization",
                    anonymize_dataset,
                    input_dataset=str(input_path),
                    output_dataset=str(anonymized_dir),
                    mapping_directory=str(mappings_dir),
                )

                if result.failed_files:
                    raise RuntimeError(
                        f"{len(result.failed_files)} files failed "
                        "anonymization. Review the results before "
                        "continuing."
                    )

                dicom_input = Path(result.output_dataset)
            else:
                dicom_input = input_path

            # Convert DICOM to NIfTI.
            def conversion_progress(index, total, directory):
                progress_state["fraction"] = (
                    index / total if total else 0.0
                )

                progress_state["detail"] = (
                    f"Converting directory {index}/{total}: {directory}"
                )
            nifti_dir = project_path / "nifti_converted"

            if nifti_dir.exists():
                raise FileExistsError(
                    f"Conversion directory already exists: {nifti_dir}"
                )

            nifti_dir.mkdir()

            conversion_result = await run_stage(
                "DICOM to NIfTI conversion",
                convert_dicom_to_nifti,
                input_directory=dicom_input,
                output_directory=nifti_dir,
                progress_callback=conversion_progress,
            )

            if not conversion_result.nifti_files:
                raise RuntimeError(
                    "Conversion did not produce any NIfTI files."
                )

            datafolder = Path(
                conversion_result.output_directory
            )

        # --------------------------------------------------
        # NIFTI WORKFLOW
        # --------------------------------------------------
        else:
            datafolder = project_path / "nifti_dataset"

            if datafolder.exists():
                raise FileExistsError(
                    f"Working copy already exists: {datafolder}"
                )

            await run_stage(
                "Copying NIfTI dataset",
                shutil.copytree,
                input_path,
                datafolder,
            )

        # --------------------------------------------------
        # ORGANIZE DATASET
        # --------------------------------------------------
        await run_stage(
            "Dataset organization",
            organize_dataset,
            datafolder,
        )

        state["datafolder"] = str(datafolder)

        total_elapsed = time.monotonic() - total_start
        clock_state["stage"] = "Completed"
        clock_state["stage_start"] = time.monotonic()

        stage_label.set_text("Preprocessing completed!")
        update_clock()

        # Show the final timing summary.
        with timing_summary:
            ui.separator()
            ui.label("Processing time summary").classes(
                "font-semibold"
            )

            for name, elapsed in timings:
                ui.label(
                    f"{name}: {format_time(elapsed)}"
                )

            ui.separator()
            ui.label(
                f"Total preprocessing time: "
                f"{format_time(total_elapsed)}"
            ).classes("font-semibold")

            ui.label(
                f"Working dataset: {datafolder}"
            ).classes("text-sm text-gray-500")

        ui.notify(
            "Preprocessing completed successfully",
            type="positive",
        )

        timing_file = save_preprocessing_timings(
            project_path=project_path,
            selected_type=selected_type,
            anonymize=anonymize,
            timings=timing_report,
            total_seconds=time.monotonic() - total_start,
            status="completed",
        )

        print(f"Preprocessing timings saved to: {timing_file}")

        # Keep the progress summary visible while displaying
        # the existing project settings screen.
        show_project_settings(
            content=content,
            state=state,
            container=container,
            datafolder=datafolder,
            project_path=project_path,
        )

    except Exception as e:
        print(f"Dataset preprocessing failed: {e}")

        stage_label.set_text(
            f"Preprocessing failed: {e}"
        )

        with timing_summary:
            ui.separator()
            ui.label("Time spent before failure").classes(
                "font-semibold"
            )

            for name, elapsed in timings:
                ui.label(
                    f"{name}: {format_time(elapsed)}"
                )

            ui.label(
                f"Total elapsed: "
                f"{format_time(time.monotonic() - total_start)}"
            )

        try:
            timing_file = save_preprocessing_timings(
                project_path=project_path,
                selected_type=selected_type,
                anonymize=anonymize,
                timings=timing_report,
                total_seconds=time.monotonic() - total_start,
                status="failed",
                error=str(e),
            )
            print(f"Partial timing report saved to: {timing_file}")
        except Exception as save_error:
            print(f"Could not save timing report: {save_error}")

        ui.notify(
            f"Preprocessing failed: {e}",
            type="negative",
            timeout=10000,
        )

    finally:
        clock.cancel()


def show_project_settings(
    content,
    state,
    container,
    datafolder,
    project_path,
):
    """Show existing settings after preprocessing."""

    content.clear()

    with content:
        ui.label("Project Settings").classes(
            "text-xl font-semibold"
        )

        settings = SettingsConfig()

        # Keep the existing contrast question.
        ui.label(
            "Acquisitions done with contrast injection?"
        ).classes("text-sm text-gray-600")

        contrast_toggle = ui.radio(
            {
                True: "Yes or unknown",
                False: "No",
            },
            value=True,
        ).props("inline")

        contrast_toggle.bind_value(state, "has_contrast_data")

        # Keep the existing orientation question.
        ui.label("Orientation Naming Settings").classes(
            "text-sm text-gray-600"
        )

        orientation_toggle = ui.radio(
            {
                "anatomical": "Anatomical",
                "dimensionality": "Dimensionality",
                "none": "None",
            },
            value="anatomical",
        ).props("inline")

        orientation_toggle.bind_value(
            state, "orientation_settings"
        )

        description = ui.label(
            "Description: "
            + settings.get_orientation_mode_description(
                state["orientation_settings"]
            )
        )

        orientation_toggle.on_value_change(
            lambda e: description.set_text(
                "Description: "
                + settings.get_orientation_mode_description(e.value)
            )
        )

        def load_project():
            mapping_start = time.monotonic()
            mapping_status = "failed"

            try:
                settings.set(
                    "has_contrast_data",
                    state["has_contrast_data"],
                )
                settings.orientation_mode = state["orientation_settings"]

                settings.save_to_file(
                    project_path / "project_settings.json"
                )

                # Time the complete renaming-map creation process.
                mapping_start = time.monotonic()

                all_scans, _, _ = build_mapping_duplicates_control(
                    str(datafolder),
                    project_path,
                    check_niftis=False#True,
                )

                mapping_seconds = time.monotonic() - mapping_start
                mapping_status = "completed"

                # Add the timing to the existing preprocessing report.
                timing_file = project_path / "preprocessing_timings.json"

                if timing_file.exists():
                    with open(timing_file, "r", encoding="utf-8") as f:
                        report = json.load(f)
                else:
                    # Allows timing project loading even for older projects
                    # that do not yet have a preprocessing report.
                    report = {
                        "stages": [],
                        "status": "completed",
                    }

                stages = report.setdefault("stages", [])

                # Replace a previous measurement instead of adding duplicates
                # when the project is loaded more than once.
                stages[:] = [
                    stage for stage in stages
                    if stage.get("name") != "Create renaming map"
                ]

                stages.append({
                    "name": "Create renaming map",
                    "seconds": round(mapping_seconds, 3),
                    "status": mapping_status,
                })

                report["project_load_timing_updated_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )

                with open(timing_file, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)

                print(
                    f"Create renaming map: {mapping_seconds:.3f} seconds"
                )

                launch_project(
                    all_scans,
                    container,
                    project_path,
                )

            except Exception as e:
                # Record a failed mapping attempt too, if the mapping itself
                # was the operation that failed.
                if mapping_status == "failed":
                    mapping_seconds = time.monotonic() - mapping_start

                    try:
                        timing_file = project_path / "preprocessing_timings.json"

                        if timing_file.exists():
                            with open(timing_file, "r", encoding="utf-8") as f:
                                report = json.load(f)
                        else:
                            report = {"stages": []}

                        stages = report.setdefault("stages", [])
                        stages[:] = [
                            stage for stage in stages
                            if stage.get("name") != "Create renaming map"
                        ]
                        stages.append({
                            "name": "Create renaming map",
                            "seconds": round(mapping_seconds, 3),
                            "status": "failed",
                        })

                        with open(timing_file, "w", encoding="utf-8") as f:
                            json.dump(report, f, indent=2, ensure_ascii=False)

                    except Exception as timing_error:
                        print(
                            f"Could not save mapping timing: {timing_error}"
                        )

                traceback.print_exc()
                ui.notify(
                    f"Could not load project: {e}",
                    type="negative",
                    timeout=10000,
                )
                print(f"Could not load project: {e}")


        with ui.row().classes("mt-4 gap-4"):
            ui.button(
                "Back",
                on_click=lambda: show_new_project(
                    content, state, container
                ),
                color="grey-6",
            )

            ui.button(
                "Load Project",
                on_click=load_project,
            )


# =========================================================
# 2. SESSION MODE
# =========================================================

def show_continue_session(content, state, container):

    content.clear()

    with content:

        ui.label('Continue Session').classes('text-xl font-semibold')

        project_folder = ui.input(
            label='Session Output Folder Path',
            placeholder='Path/to/session/output'
        ).classes('w-[500px]')
        build_recent_ui(state, project_folder, RECENT_PROJECT_FOLDER_FILE, "Output Folder")


        def load_session():

            project_folder_path = project_folder.value

            save_recent(RECENT_PROJECT_FOLDER_FILE, project_folder_path)

            csv_path = os.path.join(project_folder_path, "session_data.csv")
            json_path = os.path.join(project_folder_path, "project_settings.json")

            if not csv_path or not os.path.exists(csv_path):
                ui.notify(f'CSV file not found: {csv_path}')
                return

            df = pd.read_csv(csv_path, dtype=str).fillna('')
            all_scans = df.to_dict(orient='records')

            for scan in all_scans:
                value = scan.get('_original_state', '')

                if isinstance(value, str) and value.strip():
                    try:
                        scan['_original_state'] = ast.literal_eval(value)
                    except Exception as e:
                        print(
                            f"Could not parse _original_state for "
                            f"{scan.get('Original Filename', 'unknown')}: {e}"
                        )
            
            if not json_path or not os.path.exists(json_path):
                ui.notify('Project Settings JSON file not found')
                return

            launch_project(all_scans, container, project_folder_path)

        with ui.row().classes('mt-4 gap-4'):
            ui.button('Back', on_click=lambda: reset_startup(content, state, container), color='grey-6')
            ui.button('Resume Session', on_click=load_session)



def reset_startup(content, state, container):

    content.clear()
    build_mode_selector(content, state, container)

# =========================================================
# 4. TRANSITION INTO MAIN APP
# =========================================================

def launch_project(all_scans,container, project_folder):
    container.clear()
    from gui_table import launch_gui  # avoid circular import if needed
    launch_gui(all_scans,container, project_folder)
