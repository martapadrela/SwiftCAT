# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro


import os
from enum import Enum
from pathlib import Path


class InputType(Enum):
    DICOM = "dicom"
    NIFTI = "nifti"
    UNKNOWN = "unknown"


# Common DICOM extensions.
# DICOM files don't necessarily have an extension, which is why
# we also check the DICM signature below.
DICOM_EXTENSIONS = {
    ".dcm",
    ".ima",
    ".dic",
    ".dc3",
    ".dicom",
}

# NIfTI extensions.
NIFTI_SUFFIXES = (
    ".nii",
    ".nii.gz",
)


def _is_nifti_file(filename: str) -> bool:
    """Return True if the filename has a NIfTI extension."""
    filename = filename.lower()
    return filename.endswith(NIFTI_SUFFIXES)


def _has_dicom_extension(filename: str) -> bool:
    """Return True if the filename has a common DICOM extension."""
    return Path(filename).suffix.lower() in DICOM_EXTENSIONS


def _has_dicom_signature(filepath: str) -> bool:
    """
    Check for the DICOM Part 10 'DICM' signature.

    Only 132 bytes are read, so this is very cheap.
    """
    try:
        with open(filepath, "rb") as f:
            header = f.read(132)

        return (
            len(header) >= 132
            and header[128:132] == b"DICM"
        )

    except (OSError, PermissionError):
        return False


def _is_dicom_file(filepath: str, filename: str) -> bool:
    """
    Determine whether a file is likely to be DICOM.

    First checks the extension because that is essentially free.
    If there is no recognizable extension, checks the DICOM signature.
    """
    if _has_dicom_extension(filename):
        return True

    return _has_dicom_signature(filepath)


def _detect_file_type(filepath: str, filename: str) -> InputType:
    """Determine the type of a single file."""

    # NIfTI detection is based on filename.
    if _is_nifti_file(filename):
        return InputType.NIFTI

    # DICOM detection uses extension and then the file signature.
    if _is_dicom_file(filepath, filename):
        return InputType.DICOM

    return InputType.UNKNOWN


def _find_first_recognizable_file(directory: str) -> InputType:
    """
    Recursively search a directory until the first recognizable
    DICOM or NIfTI file is found.

    The search stops immediately once a type is identified.
    """

    # Stack of directories still to visit.
    directories = [directory]

    while directories:
        current_directory = directories.pop()

        try:
            with os.scandir(current_directory) as entries:

                for entry in entries:

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            directories.append(entry.path)
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            continue

                    except OSError:
                        # File disappeared or became inaccessible.
                        continue

                    file_type = _detect_file_type(
                        entry.path,
                        entry.name,
                    )

                    if file_type != InputType.UNKNOWN:
                        return file_type

        except (OSError, PermissionError):
            # Ignore directories that cannot be accessed.
            continue

    return InputType.UNKNOWN


def detect_input_type(input_path: str | Path) -> InputType:
    """
    Quickly determine whether an input is DICOM or NIfTI.

    Important:
    - The dataset is assumed to contain only DICOM or only NIfTI.
    - Mixed DICOM/NIfTI datasets are not supported.
    - The entire dataset is NOT scanned.
    - The function stops as soon as it finds the first recognizable file.

    Returns:
        InputType.DICOM
        InputType.NIFTI
        InputType.UNKNOWN
    """

    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input path does not exist: {input_path}"
        )

    # If the user selected a file directly.
    if input_path.is_file():
        return _detect_file_type(
            str(input_path),
            input_path.name,
        )

    # Otherwise search the directory tree.
    return _find_first_recognizable_file(
        str(input_path)
    )

#%%
# ---------------------------------------------------------
# Simple test
# ---------------------------------------------------------

# if __name__ == "__main__":

#     input_path = (
#         "/generalData/glioma/SwiftCAT Tests/"
#         "glioma_original_dicoms_test_set/"
#     )

#     result = detect_input_type(input_path)

#     print(f"Input type: {result.value}")