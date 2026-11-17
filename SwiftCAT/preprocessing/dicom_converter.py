# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
from collections.abc import Callable


@dataclass
class Dcm2NiixResult:
    output_directory: Path
    nifti_files: list[Path]
    json_files: list[Path]
    bval_files: list[Path]
    bvec_files: list[Path]


class Dcm2NiixError(RuntimeError):
    """Raised when dcm2niix conversion fails."""


# Extensions that clearly identify non-DICOM files.
# These files can be classified without opening them.
NON_DICOM_EXTENSIONS = {
    ".txt", ".csv", ".tsv", ".json", ".xml", ".html", ".htm",
    ".pdf", ".md", ".log", ".rtf",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff",
    ".svg", ".webp",
    ".nii", ".gz", ".zip", ".tar", ".7z", ".rar",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".py", ".sh", ".bat", ".exe", ".r"
}

# Common DICOM extensions.
DICOM_EXTENSIONS = {
    ".dcm",
    ".ima",
    ".dic",
    ".dc3",
    ".dicom",
}


def find_dcm2niix(
    executable: str | Path = "dcm2niix",
) -> Path:
    """Find the dcm2niix executable."""

    executable = str(executable)

    if Path(executable).is_file():
        return Path(executable)

    found = shutil.which(executable)

    if found is None:
        raise FileNotFoundError(
            "Could not find dcm2niix. "
            "Make sure dcm2niix is installed and available "
            "on the system PATH."
        )

    return Path(found)


def _is_dicom_file(file_path: Path) -> bool:
    """
    Classify a file as DICOM or non-DICOM.

    Detection order:
    1. Known non-DICOM extensions: no file read.
    2. Known DICOM extensions: accept as DICOM candidates.
    3. Check the standard DICM marker at byte 128.
    4. For ambiguous files, use pydicom as a fallback.

    This avoids opening clearly non-DICOM files unnecessarily.
    """

    name = file_path.name.lower()
    suffix = file_path.suffix.lower()

    # Handle compound extensions first.
    if name.endswith(".nii.gz"):
        return False

    # Reject clearly non-DICOM files without opening them.
    if suffix in NON_DICOM_EXTENSIONS:
        return False

    # Common DICOM extensions.
    if suffix in DICOM_EXTENSIONS:
        return True

    # Quick content check for extensionless files or unknown
    # extensions. A standard DICOM preamble is 128 bytes,
    # followed by the four-byte marker "DICM".
    try:
        with file_path.open("rb") as file:
            file.seek(128)
            if file.read(4) == b"DICM":
                return True
    except OSError:
        return False

    # Some valid DICOM files do not have the standard preamble.
    # Use pydicom only for files that remain ambiguous.
    try:
        import pydicom
    except ImportError:
        # Without pydicom, ambiguous files without the marker
        # cannot be identified reliably.
        return False

    try:
        pydicom.dcmread(
            str(file_path),
            stop_before_pixels=True,
            force=False,
        )
        return True
    except Exception:
        return False


def _get_series_description(directory: Path) -> str:
    """
    Get the SeriesDescription from the first readable DICOM file.
    Called only when conversion fails.

    Reads DICOM headers without loading pixel data.
    """

    try:
        import pydicom
    except ImportError:
        return "Unknown (pydicom not installed)"

    for file_path in directory.iterdir():
        if not file_path.is_file() or file_path.is_symlink():
            continue

        # Skip files already known to be non-DICOM.
        name = file_path.name.lower()
        suffix = file_path.suffix.lower()

        if name.endswith(".nii.gz") or suffix in NON_DICOM_EXTENSIONS:
            continue

        try:
            dataset = pydicom.dcmread(
                str(file_path),
                stop_before_pixels=True,
                force=False,
                specific_tags=["SeriesDescription"],
            )

            description = getattr(
                dataset, "SeriesDescription", None
            )

            if description:
                return str(description).strip()

        except Exception:
            continue

    return "Unknown"


def convert_dicom_to_nifti(
    input_directory: str | Path | list[str | Path] | tuple[str | Path, ...],
    output_directory: str | Path,
    dcm2niix_executable: str | Path = "dcm2niix",
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Dcm2NiixResult:
    """
    Convert DICOM data to compressed NIfTI while preserving
    the original directory hierarchy.

    input_directory can be:
    - A single dataset directory (str or Path).
    - A list/tuple of selected subject or other directories.

    For multiple input directories, each directory must belong
    to the same dataset root. The dataset root is inferred from
    the common parent of the selected directories.

    - DICOM files are converted from the input directories.
    - DICOM files are not copied to the output.
    - Non-DICOM files are copied to matching output locations.
    - Empty directories are preserved.
    - Each directory containing DICOM files is converted separately.
    - The original dataset is never modified.
    """

    output_directory = Path(output_directory)

    # ---------------------------------------------------------
    # STEP 0: Normalize the selected input directories.
    # ---------------------------------------------------------

    if isinstance(input_directory, (str, Path)):
        input_directories = [Path(input_directory)]
        dataset_root = Path(input_directory).resolve()
    else:
        input_directories = [Path(p) for p in input_directory]

        if not input_directories:
            raise ValueError("At least one input directory must be selected.")

        input_directories = [p.resolve() for p in input_directories]

        # Use the common parent to preserve the dataset hierarchy.
        dataset_root = Path(
            os.path.commonpath([str(p) for p in input_directories])
        )

        # If the selected paths have a common path that is itself
        # one of the selected directories, use its parent instead.
        if dataset_root in input_directories:
            dataset_root = dataset_root.parent

    # Resolve all paths and validate the selected directories.
    input_directories = list(dict.fromkeys(
        p.resolve() for p in input_directories
    ))

    for input_dir in input_directories:
        if not input_dir.is_dir():
            raise NotADirectoryError(
                f"Input directory does not exist: {input_dir}"
            )

    dataset_root = dataset_root.resolve()
    output_resolved = output_directory.resolve()

    # Ensure every selected directory is inside the dataset root.
    for input_dir in input_directories:
        if input_dir != dataset_root and dataset_root not in input_dir.parents:
            raise ValueError(
                f"Input directory is outside the dataset root: {input_dir}"
            )

    # Never allow the output to overlap with the dataset root.
    if (
        output_resolved == dataset_root
        or dataset_root in output_resolved.parents
        or output_resolved in dataset_root.parents
    ):
        raise ValueError(
            "The output directory must be separate from the input "
            "dataset. SwiftCAT never modifies the original dataset."
        )

    # Also guard against output overlapping a selected input directory.
    for input_dir in input_directories:
        if (
            output_resolved == input_dir
            or input_dir in output_resolved.parents
            or output_resolved in input_dir.parents
        ):
            raise ValueError(
                f"Output directory overlaps with input directory: {input_dir}"
            )

    if output_directory.exists() and any(output_directory.iterdir()):
        raise FileExistsError(
            "Output directory already exists and is not empty: "
            f"{output_directory}"
        )

    executable = find_dcm2niix(dcm2niix_executable)

    output_directory.mkdir(parents=True, exist_ok=True)

    # Each entry contains a source directory and its DICOM files.
    dicom_directories: dict[Path, list[Path]] = {}

    # Track directories to preserve, including empty directories.
    directories_to_preserve = set()

    print("Scanning input and copying non-DICOM files...")

    # ---------------------------------------------------------
    # STEP 1: Traverse only the selected directories.
    # ---------------------------------------------------------

    for input_dir in input_directories:
        for current_directory, dirnames, filenames in os.walk(input_dir):
            current_directory = Path(current_directory)

            # Do not follow symbolic links to directories.
            dirnames[:] = [
                name for name in dirnames
                if not (current_directory / name).is_symlink()
            ]

            relative_directory = current_directory.relative_to(dataset_root)
            destination_directory = output_directory / relative_directory

            directories_to_preserve.add(relative_directory)

            for filename in filenames:
                source_file = current_directory / filename

                if source_file.is_symlink() or not source_file.is_file():
                    continue

                if _is_dicom_file(source_file):
                    dicom_directories.setdefault(
                        current_directory, []
                    ).append(source_file)
                else:
                    destination_directory.mkdir(
                        parents=True, exist_ok=True
                    )
                    shutil.copy2(
                        source_file,
                        destination_directory / filename,
                    )

    # Create all selected directories, including empty ones.
    for relative_directory in directories_to_preserve:
        (output_directory / relative_directory).mkdir(
            parents=True, exist_ok=True
        )

    print(
        f"Found {len(dicom_directories)} directories "
        "containing DICOM candidates."
    )

    # ---------------------------------------------------------
    # STEP 2: Convert each DICOM-containing directory.
    # ---------------------------------------------------------

    conversion_errors = []
    total_directories = len(dicom_directories)

    for index, (dicom_directory, _) in enumerate(
        sorted(dicom_directories.items()),
        start=1,
    ):
        relative_directory = dicom_directory.relative_to(dataset_root)
        destination_directory = output_directory / relative_directory

        print(
            f"[{index}/{total_directories}] "
            f"Converting: {relative_directory}"
        )
        if progress_callback is not None:
            progress_callback(
                index,
                total_directories,
                str(relative_directory),
            )

        parts = relative_directory.parts

        subject = next(
            (part for part in parts if part.startswith("sub-")),
            None,
        )
        session = next(
            (part for part in parts if part.startswith("ses-")),
            None,
        )

        prefix = "_".join(
            part for part in (subject, session) if part
        )
        filename_format = f"{prefix}_%f_%p_%d_%t_%s"

        command = [
            str(executable),
            "-b", "y",
            "-ba", "n",
            "-d", "0",
            "-z", "y",
            "-f", filename_format,
            "-o", str(destination_directory),
            str(dicom_directory),
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )

        if completed.returncode != 0:
            series_description = _get_series_description(
                dicom_directory
            )

            error_details = (
                f"Directory: {dicom_directory}\n"
                f"Series description: {series_description}\n"
                f"Exit code: {completed.returncode}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

            conversion_errors.append(error_details)

            print(
                f"WARNING: Conversion failed for {dicom_directory}\n"
                f"         Series description: {series_description}"
            )

    # ---------------------------------------------------------
    # STEP 3: Collect all generated outputs recursively.
    # ---------------------------------------------------------

    nifti_files = sorted(output_directory.rglob("*.nii.gz"))
    json_files = sorted(output_directory.rglob("*.json"))
    bval_files = sorted(output_directory.rglob("*.bval"))
    bvec_files = sorted(output_directory.rglob("*.bvec"))

    print("\nConversion summary:")
    print(f"Input directories selected: {len(input_directories)}")
    print(f"Directories processed: {total_directories}")
    print(f"NIfTI files: {len(nifti_files)}")
    print(f"JSON files:  {len(json_files)}")
    print(f"BVAL files:  {len(bval_files)}")
    print(f"BVEC files:  {len(bvec_files)}")

    if conversion_errors:
        print(
            f"\nWARNING: {len(conversion_errors)} "
            "directory conversion(s) failed."
        )
        print("Successful outputs have been retained.")
        print("Failed directories:\n")

        for error in conversion_errors:
            print(error)
            print("-" * 80)

    return Dcm2NiixResult(
        output_directory=output_directory,
        nifti_files=nifti_files,
        json_files=json_files,
        bval_files=bval_files,
        bvec_files=bvec_files,
    )





# %%
# Example usage

# if __name__ == "__main__":

#     input_directory = "/generalData/glioma/SwiftCAT Tests/anonymization_test_13-10_run-2/"


#     output_directory = "/generalData/glioma/SwiftCAT Tests/conversion_anonymized_test_14-10_run-1"


#     result = convert_dicom_to_nifti(
#         input_directory=input_directory,
#         output_directory=output_directory,
#     )

#     print("\nConversion finished!")
#     print(f"Output directory: {result.output_directory}")

# %%
