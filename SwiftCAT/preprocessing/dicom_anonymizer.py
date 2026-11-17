# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

from pathlib import Path
from typing import Iterable

from pydicom import dcmread
from pydicom.dataset import Dataset



# DICOM tags containing direct patient-identifying information.
# These are the tags we currently remove from the DICOM metadata.
DEFAULT_ANONYMIZE_TAGS = (
    (0x0010, 0x0010),  # PatientName
    (0x0010, 0x0020),  # PatientID
    (0x0010, 0x1040),  # PatientAddress
)


DICOM_EXTENSIONS = {
    ".dcm",
    ".ima",
    ".dic",
    ".dc3",
    ".dicom",
}


def find_dicom_files(input_path: str | Path) -> list[Path]:
    """
    Find DICOM files recursively inside a file or directory.

    Parameters
    ----------
    input_path:
        Path to a DICOM file or directory containing DICOM files.

    Returns
    -------
    list[Path]
        Paths to files that appear to be DICOM files based on their
        extension.

    Notes
    -----
    This is only an initial file discovery mechanism. Later we can make
    the input detection more robust by checking the DICOM file signature
    (DICM) and attempting to read the file with pydicom.
    """
    input_path = Path(input_path)

    if input_path.is_file():
        if input_path.suffix.lower() in DICOM_EXTENSIONS:
            return [input_path]
        return []

    if not input_path.is_dir():
        raise FileNotFoundError(
            f"Input path does not exist: {input_path}"
        )

    return sorted(
        path
        for path in input_path.rglob("*")
        if path.is_file()
        and path.suffix.lower() in DICOM_EXTENSIONS
    )


def check_dicom_anonymization(
    dicom: Dataset,
    tags: Iterable[tuple[int, int]] = DEFAULT_ANONYMIZE_TAGS,
) -> dict[tuple[int, int], object]:
    """
    Check whether selected DICOM tags still contain values.

    Parameters
    ----------
    dicom:
        A pydicom Dataset.

    tags:
        DICOM tags to inspect.

    Returns
    -------
    dict
        Dictionary containing the tags that still have non-empty values.
    """
    remaining_identifiers = {}

    for tag in tags:
        if tag in dicom:
            value = dicom[tag].value

            if value not in ("", None):
                remaining_identifiers[tag] = value

    return remaining_identifiers


def anonymize_dicom_dataset(
    dicom: Dataset,
    tags: Iterable[tuple[int, int]] = DEFAULT_ANONYMIZE_TAGS,
) -> tuple[Dataset, list[tuple[int, int]]]:
    """
    Anonymize a DICOM Dataset in memory.

    Parameters
    ----------
    dicom:
        A pydicom Dataset.

    tags:
        DICOM tags to anonymize.

    Returns
    -------
    tuple
        The modified Dataset and a list of tags that were changed.

    Notes
    -----
    This function only modifies the Dataset held in memory.
    It does not write to disk.
    """

    modified_tags = []

    for tag in tags:
        if tag in dicom:
            value = dicom[tag].value

            if value not in ("", None):
                dicom[tag].value = ""
                modified_tags.append(tag)

    return dicom, modified_tags


def anonymize_dicom_file(
    input_path: str | Path,
    output_path: str | Path,
    tags: Iterable[tuple[int, int]] = DEFAULT_ANONYMIZE_TAGS,
) -> list[tuple[int, int]]:
    """
    Anonymize a DICOM file without modifying the original file.

    Parameters
    ----------
    input_path:
        Path to the original DICOM file.

    output_path:
        Path where the anonymized DICOM should be written.

    tags:
        DICOM tags to anonymize.

    Returns
    -------
    list[tuple[int, int]]
        DICOM tags that were modified.

    Raises
    ------
    FileNotFoundError
        If the input file does not exist.

    ValueError
        If input and output paths are the same.

    Notes
    -----
    The original DICOM file is NEVER modified or deleted.
    """

    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(
            f"DICOM file does not exist: {input_path}"
        )

    if input_path.resolve() == output_path.resolve():
        raise ValueError(
            "Input and output paths must be different. "
            "SwiftCAT never anonymizes DICOM files in place."
        )

    # Read the original DICOM.
    dicom = dcmread(input_path)

    # Modify only the in-memory copy.
    dicom, modified_tags = anonymize_dicom_dataset(
        dicom,
        tags=tags,
    )

    # Create the destination directory if necessary.
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Save the anonymized copy.
    dicom.save_as(output_path)

    return modified_tags