# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

"""Anonymize a DICOM dataset and associate non-DICOM files by source path.

The original dataset is never modified. Mapping CSVs contain potentially
identifying information and must be stored securely outside the anonymized data.

Note: this script preserves the original anonymization scope (PatientName,
PatientID and PatientAddress). It is not, by itself, a complete DICOM
confidentiality-profile implementation; other identifying tags and burned-in
pixel annotations may remain.
"""

from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import re
import shutil

from pydicom import dcmread
from pydicom.dataset import Dataset


# Known DICOM extensions. The signature check is used for files with other
# extensions, unless their extension is in the non-DICOM skip list below.
DICOM_EXTENSIONS = {
    ".dcm",
    ".ima",
    ".dic",
    ".dicom",
    ".dc3",
}

# Common non-DICOM extensions. For these, don't open each file just to check
# whether byte 128 contains the DICOM preamble marker. Keep this list
# conservative: unknown extensions still get the signature check.
NON_DICOM_EXTENSIONS = {
    # Documents and text
    ".pdf", ".txt", ".text", ".rtf", ".doc", ".docx", ".odt",
    ".xls", ".xlsx", ".ods", ".csv", ".tsv", ".ppt", ".pptx", ".odp",
    ".md", ".rst", ".xml", ".json", ".yaml", ".yml", ".html", ".htm",
    ".log", ".ini", ".cfg", ".conf", ".toml",
    # Images and media commonly found alongside medical data
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".svg", ".mp4", ".mov", ".avi", ".mp3", ".wav", ".flac",
    # Archives and compressed files
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    # Other common data / system files
    ".npy", ".npz", ".nii", ".gz", ".jsonl", ".db", ".sqlite", ".bak",
    ".tmp", ".lock", ".py", ".sh", ".bat", ".exe", ".dll", ".so",
}

# Metadata used in the first pass to identify patients, studies, and dates.
# pydicom also retains required character-set information when needed.
DICOM_METADATA_TAGS = [
    "PatientID",
    "PatientName",
    "StudyInstanceUID",
    "StudyDate",
    "AcquisitionDate",
    "StudyTime",
    "AcquisitionTime",
    "StudyID",
    "StudyDescription",
    "AccessionNumber",
]


@dataclass
class DatasetAnonymizationResult:
    output_dataset: Path
    patient_mapping_file: Path
    session_mapping_file: Path
    path_mapping_file: Path
    anonymized_files: int
    failed_files: list[Path]


class PatientMapper:
    """Maintain a stable mapping from patient information to anonymous IDs."""

    def __init__(self, mapping_file: str | Path):
        self.mapping_file = Path(mapping_file)
        self._mapping: dict[str, str] = {}
        self._next_subject_number = 1
        if self.mapping_file.exists():
            self._load_mapping()

    def _load_mapping(self) -> None:
        with self.mapping_file.open("r", newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                patient_key = row["patient_key"]
                anonymous_id = row["anonymous_id"]
                self._mapping[patient_key] = anonymous_id
                match = re.fullmatch(r"sub-(\d+)", anonymous_id)
                if match:
                    self._next_subject_number = max(
                        self._next_subject_number, int(match.group(1)) + 1
                    )

    def get_subject_id(self, patient_key: str) -> str:
        if patient_key in self._mapping:
            return self._mapping[patient_key]
        anonymous_id = f"sub-{self._next_subject_number:03d}"
        self._mapping[patient_key] = anonymous_id
        self._next_subject_number += 1
        return anonymous_id

    def save(self) -> None:
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with self.mapping_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["patient_key", "anonymous_id"])
            writer.writeheader()
            for patient_key, anonymous_id in sorted(self._mapping.items()):
                writer.writerow({"patient_key": patient_key, "anonymous_id": anonymous_id})


def _get_acquisition_datetime(dicom: Dataset) -> str:
    """Return a sortable YYYYMMDDHHMMSS string, or empty if no date exists."""
    date_value = str(getattr(dicom, "StudyDate", "")).strip()
    if not date_value:
        date_value = str(getattr(dicom, "AcquisitionDate", "")).strip()
    if not date_value:
        return ""

    time_value = str(getattr(dicom, "StudyTime", "")).strip()
    if not time_value:
        time_value = str(getattr(dicom, "AcquisitionTime", "")).strip()
    time_value = time_value.split(".", 1)[0]
    time_value = time_value.ljust(6, "0")
    return f"{date_value}{time_value[:6]}"


class SessionMapper:
    """Assign session IDs chronologically within each subject."""

    def __init__(self):
        self._studies: dict[str, dict[str, tuple[str, str]]] = {}
        self._session_ids: dict[tuple[str, str], str] = {}

    def register_study(
        self, subject_id: str, study_key: str, acquisition_datetime: str
    ) -> None:
        studies = self._studies.setdefault(subject_id, {})
        if study_key not in studies:
            studies[study_key] = (acquisition_datetime, study_key)
        else:
            existing_datetime, _ = studies[study_key]
            if acquisition_datetime and (
                not existing_datetime or acquisition_datetime < existing_datetime
            ):
                studies[study_key] = (acquisition_datetime, study_key)

    def assign_sessions(self) -> None:
        for subject_id, studies in self._studies.items():
            sorted_studies = sorted(
                studies.values(),
                key=lambda item: (
                    item[0] if item[0] else "99999999999999", item[1]
                ),
            )
            for session_number, (_, study_key) in enumerate(sorted_studies, start=1):
                self._session_ids[(subject_id, study_key)] = f"ses-{session_number:02d}"

    def get_session_id(self, subject_id: str, study_key: str) -> str:
        try:
            return self._session_ids[(subject_id, study_key)]
        except KeyError as error:
            raise KeyError(
                f"No session assigned for {subject_id}, study {study_key}"
            ) from error

    def save(self, mapping_file: str | Path) -> None:
        mapping_file = Path(mapping_file)
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for subject_id, studies in self._studies.items():
            for study_key, (acquisition_datetime, _) in studies.items():
                rows.append({
                    "subject_id": subject_id,
                    "study_key": study_key,
                    "session_id": self.get_session_id(subject_id, study_key),
                    "acquisition_datetime": acquisition_datetime,
                })
        rows.sort(key=lambda row: (row["subject_id"], row["session_id"]))
        with mapping_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "subject_id", "study_key", "session_id", "acquisition_datetime"
                ],
            )
            writer.writeheader()
            writer.writerows(rows)


class PathMapper:
    """Map original ancestor directories to subjects and sessions."""

    def __init__(self, input_dataset: str | Path):
        self.input_dataset = Path(input_dataset).resolve()
        self._session_paths: dict[Path, set[tuple[str, str]]] = {}
        self._subject_paths: dict[Path, set[str]] = {}

    def _ancestor_paths(self, path: Path) -> list[Path]:
        try:
            relative_parent = path.parent.relative_to(self.input_dataset)
        except ValueError:
            return []
        ancestors = []
        current = self.input_dataset
        for part in relative_parent.parts:
            current = current / part
            ancestors.append(current)
        return ancestors

    def register_file(
        self, file_path: str | Path, subject_id: str, session_id: str
    ) -> None:
        file_path = Path(file_path).resolve()
        for ancestor in self._ancestor_paths(file_path):
            self._session_paths.setdefault(ancestor, set()).add((subject_id, session_id))
            self._subject_paths.setdefault(ancestor, set()).add(subject_id)

    def _find_best_matching_path(self, file_path: Path, mapping: dict):
        current = file_path.parent
        while True:
            if current in mapping:
                return current
            if current == self.input_dataset or self.input_dataset not in current.parents:
                return None
            current = current.parent

    def find_destination(self, file_path: str | Path):
        file_path = Path(file_path).resolve()
        session_path = self._find_best_matching_path(file_path, self._session_paths)
        if session_path is not None:
            matches = self._session_paths[session_path]
            if len(matches) == 1:
                subject_id, session_id = next(iter(matches))
                return "session", subject_id, session_id
            return None

        subject_path = self._find_best_matching_path(file_path, self._subject_paths)
        if subject_path is not None:
            matches = self._subject_paths[subject_path]
            if len(matches) == 1:
                return "subject", next(iter(matches)), None
            return None
        return None

    def save(self, mapping_file: str | Path) -> None:
        mapping_file = Path(mapping_file)
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for original_path, matches in self._session_paths.items():
            for subject_id, session_id in sorted(matches):
                rows.append({
                    "original_path": str(original_path),
                    "mapping_type": "session",
                    "subject_id": subject_id,
                    "session_id": session_id,
                })
        for original_path, subjects in self._subject_paths.items():
            for subject_id in sorted(subjects):
                rows.append({
                    "original_path": str(original_path),
                    "mapping_type": "subject",
                    "subject_id": subject_id,
                    "session_id": "",
                })
        rows.sort(key=lambda row: (
            row["original_path"], row["mapping_type"],
            row["subject_id"], row["session_id"]
        ))
        with mapping_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["original_path", "mapping_type", "subject_id", "session_id"],
            )
            writer.writeheader()
            writer.writerows(rows)


def _has_dicom_signature(path: Path) -> bool:
    """Check for the standard DICOM 'DICM' marker at byte 128."""
    try:
        with path.open("rb") as file:
            header = file.read(132)
        return len(header) >= 132 and header[128:132] == b"DICM"
    except OSError:
        return False


def is_dicom_file(path: str | Path) -> bool:
    """Quick file classification using known extensions before signature I/O."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in DICOM_EXTENSIONS:
        return True
    if suffix in NON_DICOM_EXTENSIONS:
        return False
    return _has_dicom_signature(path)


def _get_patient_key(dicom: Dataset) -> str:
    patient_id = str(getattr(dicom, "PatientID", "")).strip()
    patient_name = str(getattr(dicom, "PatientName", "")).strip()
    if patient_id and patient_name:
        return f"{patient_id}|{patient_name}"
    if patient_id:
        return patient_id
    if patient_name:
        return patient_name
    raise ValueError("DICOM contains neither PatientID nor PatientName.")


def _get_study_key(dicom: Dataset) -> str:
    study_uid = str(getattr(dicom, "StudyInstanceUID", "")).strip()
    if study_uid:
        return study_uid
    study_date = str(getattr(dicom, "StudyDate", "")).strip()
    study_time = str(getattr(dicom, "StudyTime", "")).strip()
    study_id = str(getattr(dicom, "StudyID", "")).strip()
    study_description = str(getattr(dicom, "StudyDescription", "")).strip()
    accession_number = str(getattr(dicom, "AccessionNumber", "")).strip()
    fallback = "|".join([
        study_date, study_time, study_id, study_description, accession_number
    ])
    if fallback.strip("|"):
        return f"fallback-study-{fallback}"
    return "unknown-study"


def _get_series_key(dicom: Dataset) -> str:
    series_uid = str(getattr(dicom, "SeriesInstanceUID", "")).strip()
    if series_uid:
        return series_uid
    series_number = str(getattr(dicom, "SeriesNumber", "")).strip()
    if series_number:
        return f"series-{series_number}"
    return "unknown-series"


def _series_hash(dicom: Dataset) -> str:
    return hashlib.sha256(_get_series_key(dicom).encode("utf-8")).hexdigest()[:8]


def _anonymize_dataset(dicom: Dataset, subject_id: str) -> Dataset:
    """Replace the same core patient identifiers as the original script."""
    if "PatientName" in dicom:
        dicom.PatientName = subject_id
    if "PatientID" in dicom:
        dicom.PatientID = subject_id
    if "PatientAddress" in dicom:
        dicom.PatientAddress = ""
    return dicom


def _make_anonymous_filename(dicom: Dataset, file_number: int) -> str:
    return f"image-{_series_hash(dicom)}-{file_number:06d}.dcm"


def _make_anonymous_non_dicom_filename(
    input_path: Path, input_dataset: Path
) -> str:
    """Make a stable filename from the relative path, not the original name."""
    try:
        relative_path = input_path.resolve().relative_to(input_dataset.resolve())
        path_key = relative_path.as_posix()
    except ValueError:
        path_key = input_path.name
    path_hash = hashlib.sha256(path_key.encode("utf-8")).hexdigest()[:16]
    suffix = input_path.suffix.lower()
    # Retain ordinary short extensions for usability; discard unusual suffixes
    # that might themselves contain identifying text.
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".bin"
    return f"file-{path_hash}{suffix}"


def copy_non_dicom_file(
    input_path: str | Path,
    output_dataset: str | Path,
    input_dataset: str | Path,
    path_mapper: PathMapper,
) -> Path:
    input_path = Path(input_path)
    output_dataset = Path(output_dataset)
    input_dataset = Path(input_dataset)
    mapping = path_mapper.find_destination(input_path)

    if mapping is None:
        output_directory = output_dataset / "non-dicom-unknown"
    else:
        mapping_type, subject_id, session_id = mapping
        if mapping_type == "session":
            output_directory = output_dataset / subject_id / session_id
        elif mapping_type == "subject":
            output_directory = output_dataset / subject_id
        else:
            raise ValueError(f"Unknown mapping type: {mapping_type}")

    output_directory.mkdir(parents=True, exist_ok=True)
    output_filename = _make_anonymous_non_dicom_filename(input_path, input_dataset)
    output_path = output_directory / output_filename
    counter = 1
    while output_path.exists():
        output_path = output_directory / f"{Path(output_filename).stem}-{counter}{Path(output_filename).suffix}"
        counter += 1
    shutil.copy2(input_path, output_path)
    return output_path


def anonymize_dicom_file(
    input_path: str | Path,
    output_dataset: str | Path,
    subject_id: str,
    session_id: str,
    file_number: int,
) -> Path:
    input_path = Path(input_path)
    output_dataset = Path(output_dataset)
    if not input_path.is_file():
        raise FileNotFoundError(f"DICOM file does not exist: {input_path}")

    # Read the full dataset here because it must be written out again.
    dicom = dcmread(input_path, force=False)
    series_hash = _series_hash(dicom)
    output_directory = output_dataset / subject_id / session_id / f"series-{series_hash}"
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / _make_anonymous_filename(dicom, file_number)
    dicom = _anonymize_dataset(dicom, subject_id)
    dicom.save_as(output_path)
    return output_path


def anonymize_dataset(
    input_dataset: str | Path,
    output_dataset: str | Path,
    mapping_directory: str | Path,
) -> DatasetAnonymizationResult:
    """Create an anonymized copy, keeping the input dataset unchanged."""
    input_dataset = Path(input_dataset)
    output_dataset = Path(output_dataset)
    mapping_directory = Path(mapping_directory)

    if not input_dataset.is_dir():
        raise NotADirectoryError(f"Input dataset does not exist: {input_dataset}")

    input_resolved = input_dataset.resolve()
    output_resolved = output_dataset.resolve()
    if (
        output_resolved == input_resolved
        or input_resolved in output_resolved.parents
    ):
        raise ValueError(
            "The output directory cannot be inside the input dataset. "
            "SwiftCAT never modifies the original dataset."
        )
    if output_dataset.exists() and any(output_dataset.iterdir()):
        raise FileExistsError(
            f"Output dataset already exists and is not empty: {output_dataset}"
        )
    output_dataset.mkdir(parents=True, exist_ok=True)

    mapping_directory = mapping_directory / "mapping"
    mapping_directory.mkdir(parents=True, exist_ok=True)
    patient_mapping_file = mapping_directory / "patient_mapping.csv"
    session_mapping_file = mapping_directory / "session_mapping.csv"
    path_mapping_file = mapping_directory / "path_mapping.csv"

    patient_mapper = PatientMapper(patient_mapping_file)
    session_mapper = SessionMapper()
    path_mapper = PathMapper(input_dataset)

    anonymized_files = 0
    failed_files: list[Path] = []
    dicom_records: list[tuple[Path, str, str]] = []
    non_dicom_files: list[Path] = []

    # PASS 1: traverse the tree once and classify each file only once.
    # The metadata-only read registers patient/study relationships.
    for input_file in input_dataset.rglob("*"):
        if not input_file.is_file():
            continue
        if not is_dicom_file(input_file):
            non_dicom_files.append(input_file)
            continue
        try:
            dicom = dcmread(
                input_file,
                force=False,
                stop_before_pixels=True,
                specific_tags=DICOM_METADATA_TAGS,
            )
            patient_key = _get_patient_key(dicom)
            subject_id = patient_mapper.get_subject_id(patient_key)
            study_key = _get_study_key(dicom)
            acquisition_datetime = _get_acquisition_datetime(dicom)
            session_mapper.register_study(subject_id, study_key, acquisition_datetime)
            dicom_records.append((input_file, subject_id, study_key))
        except Exception as error:
            print(f"Could not read DICOM: {input_file}\n  {error}")
            failed_files.append(input_file)

    # Session numbering depends on all studies having been discovered.
    session_mapper.assign_sessions()

    # Register paths after session IDs are known.
    for input_file, subject_id, study_key in dicom_records:
        session_id = session_mapper.get_session_id(subject_id, study_key)
        path_mapper.register_file(input_file, subject_id, session_id)

    # PASS 2A: anonymize and write each DICOM.
    for input_file, subject_id, study_key in dicom_records:
        try:
            session_id = session_mapper.get_session_id(subject_id, study_key)
            anonymize_dicom_file(
                input_path=input_file,
                output_dataset=output_dataset,
                subject_id=subject_id,
                session_id=session_id,
                file_number=anonymized_files + 1,
            )
            anonymized_files += 1
        except Exception as error:
            print(f"Could not anonymize DICOM: {input_file}\n  {error}")
            failed_files.append(input_file)

    # PASS 2B: reuse the non-DICOM paths discovered in Pass 1.
    for input_file in non_dicom_files:
        try:
            copy_non_dicom_file(
                input_path=input_file,
                output_dataset=output_dataset,
                input_dataset=input_dataset,
                path_mapper=path_mapper,
            )
        except Exception as error:
            print(f"Could not copy non-DICOM file: {input_file}\n  {error}")
            failed_files.append(input_file)

    patient_mapper.save()
    session_mapper.save(session_mapping_file)
    path_mapper.save(path_mapping_file)

    return DatasetAnonymizationResult(
        output_dataset=output_dataset,
        patient_mapping_file=patient_mapping_file,
        session_mapping_file=session_mapping_file,
        path_mapping_file=path_mapping_file,
        anonymized_files=anonymized_files,
        failed_files=failed_files,
    )

#%%

# if __name__ == "__main__":
#     # Edit these three paths before running.
#     result = anonymize_dataset(
#         input_dataset=(
#             "/generalData/glioma/SwiftCAT Tests/"
#             "glioma_original_dicoms_test_set/"
#         ),
#         output_dataset=(
#             "/generalData/glioma/SwiftCAT Tests/"
#             "anonymization_test_13-10_run-2"
#         ),
#         mapping_directory=(
#             "/generalData/glioma/SwiftCAT Tests/"
#             "anonymization_test_13-10_run-2/"
#         ),
#     )
#     print(f"DICOM files anonymized: {result.anonymized_files}")
#     print(f"Failed files: {len(result.failed_files)}")
#     if result.failed_files:
#         print("\nFailed files:")
#         for path in result.failed_files:
#             print(f"  {path}")

