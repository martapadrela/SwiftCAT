# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

import json
import re
import shutil
from pathlib import Path

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

# Datatype folders already recognized in the input
DATATYPES = {
    "anat", "dwi", "func", "fmap", "perf", "pet", "eeg",
    "meg", "ieeg", "micr", "beh", "nirs", "motion", 
    "extras", "extras_manual", "reports", "angio", 
    "mrs", "swi", "surveys", "screen_shots", "results_reading"
}

# JSON fields used when sub/ses folders are absent.
# Adapt these to the metadata in your datasets.
SUBJECT_KEYS = ["PatientName","PatientID", "SubjectName", "SubjectID", "subject_id"]
SESSION_KEYS = ["StudyDate", "SessionDate", "session_id", "AcquisitionDateTime", "StudyID"]


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def nifti_stem(path):
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem



def clean_label(value):
    """Normalize a subject/session label without duplicating prefixes."""
    value = str(value).strip()

    # Remove an existing BIDS-style prefix, if present.
    value = re.sub(r"^(sub|ses)-", "", value, flags=re.IGNORECASE)

    # Keep only alphanumeric characters.
    value = re.sub(r"[^a-zA-Z0-9]+", "", value)

    return value or None



def read_json(path):
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: Cannot read {path}: {exc}")
        return {}


def get_metadata_value(metadata, keys):
    for key in keys:
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def metadata_sidecar(nifti):
    return nifti.with_name(nifti_stem(nifti) + ".json")


def find_existing_identifier(path, datafolder, prefix):
    for parent in path.parents:
        if parent == datafolder.parent:
            break
        if parent.name.startswith(prefix):
            return parent.name
        if parent == datafolder:
            break
    return None


def find_datatype(path, datafolder):
    for parent in path.parents:
        if parent == datafolder.parent:
            break
        if parent.name.lower() in DATATYPES:
            return parent.name.lower()
        if parent == datafolder:
            break
    return None


def get_unique_pair_destination(
    destination_dir,
    nifti,
    target_stem,
    reserved_destinations,
    paired_extensions,
):
    """
    Choose a unique basename for a NIfTI and its associated files.
    All paired files receive the same _dupN suffix if necessary.
    """
    extension = ".nii.gz" if nifti.name.endswith(".nii.gz") else ".nii"

    counter = 0

    while True:
        if counter == 0:
            new_stem = target_stem
        else:
            new_stem = f"{target_stem}_dup{counter}"

        candidates = [
            destination_dir / f"{new_stem}{ext}"
            for ext in paired_extensions
        ]
        candidates.append(destination_dir / f"{new_stem}{extension}")

        conflict = any(
            path.exists() or str(path.resolve()) in reserved_destinations
            for path in candidates
        )

        if not conflict:
            reserved_destinations.update(
                str(path.resolve()) for path in candidates
            )
            return new_stem

        counter += 1


# --------------------------------------------------
# ORGANIZATION
# --------------------------------------------------

def organize_dataset(datafolder, dry_run=False):
    datafolder = datafolder.resolve()

    if not datafolder.is_dir():
        raise NotADirectoryError(
            f"Input directory does not exist: {datafolder}"
        )

    nifti_files = sorted(
        p for p in datafolder.rglob("*")
        if p.is_file()
        and (p.name.endswith(".nii") or p.name.endswith(".nii.gz"))
    )

    moved = 0
    unresolved = []
    errors = []
    reserved_destinations = set()

    print(f"Found {len(nifti_files)} NIfTI files.")

    for nifti in nifti_files:
        try:
            sidecar = metadata_sidecar(nifti)
            has_sidecar = sidecar.is_file()
            metadata = read_json(sidecar)

            # Prefer existing folder identifiers.
            subject = find_existing_identifier(nifti, datafolder, "sub-")
            session = find_existing_identifier(nifti, datafolder, "ses-")

            # Fall back to JSON metadata.
            if subject is None:
                patient_id = get_metadata_value(
                    metadata, SUBJECT_KEYS
                )
                if patient_id:
                    subject = "sub-" + clean_label(patient_id)

            # print('session', session)

            if session is None:
                study_date = get_metadata_value(
                    metadata, SESSION_KEYS
                )
                # print('study_data', study_date)
                if study_date:
                    digits = re.sub(r"\D", "", study_date)
                    if len(digits) >= 8:
                        digits = digits[:8]

                    session_label = clean_label(digits)
                    if session_label:
                        session = "ses-" + session_label
            # print('session', session)


            if not subject:
                unresolved.append(str(nifti))
                print(f"SKIP (no subject ID): {nifti}")
                continue

            # Build the destination directory.
            destination_dir = datafolder / subject

            if session:
                destination_dir /= session

            datatype = find_datatype(nifti, datafolder)
            if datatype:
                destination_dir /= datatype

            # If the NIfTI is already in its correct location,
            # do not rename it unnecessarily.
            # --------------------------------------------------
            # BUILD THE REQUIRED FILENAME PREFIX
            # --------------------------------------------------

            # Remove an existing subject/session prefix from the
            # filename to avoid duplicating it.
            original_stem = nifti_stem(nifti)

            original_stem = re.sub(
                r"^sub-[^_]+_ses-[^_]+_",
                "",
                original_stem,
                flags=re.IGNORECASE,
            )

            # Also remove a subject-only prefix if one exists.
            original_stem = re.sub(
                r"^sub-[^_]+_",
                "",
                original_stem,
                flags=re.IGNORECASE,
            )

            if session:
                required_prefix = f"{subject}_{session}_"
            else:
                # A session label cannot be added if none was identified.
                required_prefix = f"{subject}_"

            target_stem = required_prefix + original_stem

            # Find all matching files sharing the NIfTI basename.
            source_stem = nifti_stem(nifti)

            paired_extensions = [".json", ".bvec", ".bval"]

            paired_files = {
                ext: nifti.with_name(source_stem + ext)
                for ext in paired_extensions
            }

            existing_pairs = {
                ext: path
                for ext, path in paired_files.items()
                if path.is_file()
            }

            # Build the destination directory.
            # The NIfTI and all its paired files go together.
            destination_dir = datafolder / subject

            if session:
                destination_dir /= session

            datatype = find_datatype(nifti, datafolder)

            if datatype:
                destination_dir /= datatype

            # Check whether the file needs either renaming or moving.
            correct_name = nifti.with_name(
                target_stem
                + (".nii.gz" if nifti.name.endswith(".nii.gz") else ".nii")
            )

            already_correct = (
                destination_dir.resolve() == nifti.parent.resolve()
                and nifti.name == correct_name.name
                and all(
                    path.name == target_stem + ext
                    for ext, path in existing_pairs.items()
                )
            )

            if already_correct:
                continue

            # Choose a unique destination basename for the entire group.
            new_stem = get_unique_pair_destination(
                destination_dir=destination_dir,
                nifti=nifti,
                target_stem=target_stem,
                reserved_destinations=reserved_destinations,
                paired_extensions=[
                    ext for ext in paired_extensions
                    if ext in existing_pairs
                ],
            )

            nifti_extension = (
                ".nii.gz" if nifti.name.endswith(".nii.gz") else ".nii"
            )

            destination = destination_dir / (new_stem + nifti_extension)

            # print(f"\nNIfTI: {nifti}")
            # print(f"    -> {destination}")

            for ext, source_file in existing_pairs.items():
                target_file = destination_dir / (new_stem + ext)
                # print(f"{ext}: {source_file}")
                # print(f"    -> {target_file}")

            if dry_run:
                moved += 1
                continue

            destination_dir.mkdir(parents=True, exist_ok=True)

            # Move the NIfTI.
            shutil.move(str(nifti), str(destination))

            # Move all matching sidecars using the same basename.
            for ext, source_file in existing_pairs.items():
                target_file = destination_dir / (new_stem + ext)
                shutil.move(str(source_file), str(target_file))

            moved += 1

        except Exception as exc:
            errors.append((str(nifti), str(exc)))
            print(f"ERROR processing {nifti}: {exc}")

    # Remove empty series folders and other empty directories.
    # The dataset datafolder is never removed.
    if not dry_run:
        directories = sorted(
            (p for p in datafolder.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True
        )

        for directory in directories:
            try:
                if directory != datafolder and not any(directory.iterdir()):
                    directory.rmdir()
            except OSError:
                pass

    print("\n---------- SUMMARY ----------")
    print(f"NIfTI files found: {len(nifti_files)}")
    print(f"Files planned/moved: {moved}")
    print(f"Unresolved subjects: {len(unresolved)}")
    print(f"Errors: {len(errors)}")
    print(f"Dry run: {dry_run}")

    if unresolved:
        print("\nFiles requiring manual review:")
        for path in unresolved:
            print(f"  {path}")

    if errors:
        print("\nFiles with errors:")
        for path, error in errors:
            print(f"  {path}: {error}")

#%%
# --------------------------------------------------
# RUN
# --------------------------------------------------
# datafolder = Path("/generalData/glioma/SwiftCAT Tests/conversion_anonymized_test_14-10_run-1_copy/")
# organize_dataset(datafolder, dry_run=True)


