# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

import os
import glob
import json
import numpy as np
import pandas as pd
import csv
import nibabel as nib
from datetime import datetime
from pathlib import Path
from classification_config import ClassificationConfig
from classification_rules import (
    classify_modality,
    get_sequence_from_flags,
    get_orientation_code,
    apply_sequence_fallbacks,
    check_filename_keywords,
    classify_datatype
)
from project_settings_config import SettingsConfig


def compare_nifti(file1, file2):
    # Load images and compare them safely
    try:
        img1 = nib.load(file1)
        img2 = nib.load(file2)

        # Compare headers first
        if not np.array_equal(img1.affine, img2.affine):
            return False, "Affine matrices differ"

        if img1.shape != img2.shape:
            return False, "Shapes differ"

        # Compare image data
        try:
            data1 = img1.get_fdata()
            data2 = img2.get_fdata()

            if np.array_equal(data1, data2):
                return True, "Images are exactly the same"

            return False, "Image data differs"

        except Exception as e:
            message = (
                f"Image data comparison failed: "
                f"{type(e).__name__}: {e}"
            )
            print(f"\nWARNING: {message}")
            print(f"  File 1: {file1}")
            print(f"  File 2: {file2}")
            return False, message

    except Exception as e:
        message = (
            f"NIfTI loading/comparison failed: "
            f"{type(e).__name__}: {e}"
        )
        print(f"\nWARNING: {message}")
        print(f"  File 1: {file1}")
        print(f"  File 2: {file2}")
        return False, message

def get_2d_plane_from_iop(iop):
    # Missing or invalid orientation metadata
    if not isinstance(iop, (list, tuple, np.ndarray)) or len(iop) != 6:
        return "unknown"

    
    try:
        row = np.array(iop[:3], dtype=float)
        col = np.array(iop[3:], dtype=float)

        # Reject non-numeric or non-finite values
        if not np.all(np.isfinite(row)) or not np.all(np.isfinite(col)):
            return "unknown"

        normal = np.cross(row, col)
        norm = np.linalg.norm(normal)

        # Avoid division by zero
        if norm == 0:
            return "unknown"

        normal = normal / norm
        axis = np.argmax(np.abs(normal))

        axis_map = {
            0: "sagittal",
            1: "coronal",
            2: "axial"
        }

        return axis_map[axis]

    except (TypeError, ValueError, IndexError):
        return "unknown"



def get_2d_plane_from_iop(iop):
    row = np.array(iop[:3])
    col = np.array(iop[3:])
    
    normal = np.cross(row, col)
    normal = normal / np.linalg.norm(normal)
    
    axis = np.argmax(np.abs(normal))
    
    # axis meaning of slice direction
    axis_map = {
        0: "sagittal",  # slices stacked left-right
        1: "coronal",   # slices stacked anterior-posterior
        2: "axial"      # slices stacked inferior-superior
    }
    
    return axis_map[axis]

def get_json_files(dataFolder):
    Patient_IDs = sorted([d.name for d in os.scandir(dataFolder) if ('sub-' in d.name)])
    files=[]
    for patient in range(0,len(Patient_IDs)): #1):#
        patientFolder = os.path.join(dataFolder,Patient_IDs[patient])
        timepoints = sorted([d.name for d in os.scandir(os.path.join(dataFolder,Patient_IDs[patient])) if ('ses-' in d.name)])
        # separate the timepoints within each patient
        for t in timepoints:
            timepointFolder = os.path.join(patientFolder,t)
            files += sorted(
                glob.glob(os.path.join(timepointFolder, "**", "*.json"), recursive=True),
                reverse=True
            )
            # if os.path.exists(os.path.join(timepointFolder,"anat")):
            #     files+=sorted(glob.glob(os.path.join(timepointFolder,"anat","*.json")), reverse=True)
    return files

def extract_properties(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            session_parameters = json.load(f)
            filename = os.path.basename(file)
            parent_folder = os.path.basename(os.path.dirname(file))

            InversionTime = session_parameters.get("InversionTime", 100000)
            EchoTime = session_parameters.get("EchoTime", 100000)
            RepetitionTime = session_parameters.get("RepetitionTime", 100000)
            FlipAngle = session_parameters.get("FlipAngle", 100000)
            MRAcquisitionType = session_parameters.get("MRAcquisitionType", "")
            ImgOriPatient = session_parameters.get("ImageOrientationPatientDICOM")
            AcquisitionTime = session_parameters.get("AcquisitionTime", "NA")
            SeriesDescription = session_parameters.get("SeriesDescription", "NA")
            ImageType = session_parameters.get("ImageType","NA")
            RawImage = session_parameters.get("RawImage", "NA")
            PhaseEncodingDirection = session_parameters.get("PhaseEncodingDirection", "NA")
            PhaseEncodingAxis = session_parameters.get("PhaseEncodingAxis", "NA")

            plane = get_2d_plane_from_iop(ImgOriPatient)

            if plane == "unknown":
                print(f"[WARNING] Unknown orientation; keeping file: {file}")

            if "ScanningSequence" in session_parameters:
                scan_seq = session_parameters["ScanningSequence"]
            elif InversionTime != 100000:
                scan_seq = "IR"
            else:
                scan_seq = ""

            return {
                "Original Filename": filename,
                "Original Filepath": file,
                "Original Path": file.replace(filename, ""),
                "Parent Folder": parent_folder,
                "EchoTime": EchoTime,
                "RepetitionTime": RepetitionTime,
                "MagneticFieldStrength": session_parameters.get("MagneticFieldStrength", "NA"),
                "ScannerModel": session_parameters.get("ManufacturersModelName", "Unknown"),
                "ScanningSequence": scan_seq,
                "AcquisitionTime": AcquisitionTime,
                "FlipAngle": FlipAngle,
                "MRAcquisitionType": MRAcquisitionType,
                "PrincipalPlane": plane,
                "InversionTime": InversionTime,
                "SeriesDescription": SeriesDescription,
                "ImageType": ImageType,
                "RawImage": RawImage,
                "PhaseEncodingDirection": PhaseEncodingDirection,
                "PhaseEncodingAxis": PhaseEncodingAxis
            }

    except Exception as e:
        print(f"\n[ERROR] Could not process JSON file:")
        print(f"  File: {file}")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Details: {e}\n")
        return None



def derive_names(properties, config, settings_config):
    """
    Derive scan names (modality, sequence, orientation, contrast) from imaging properties.
    
    Args:
        properties: Dictionary with imaging parameters
        config: ClassificationConfig instance
    
    Returns:
        Dictionary with derived classification fields
    """
    
    
    filename = properties['Original Filename']
    EchoTime = properties['EchoTime']
    RepetitionTime = properties['RepetitionTime']
    FlipAngle = properties['FlipAngle']
    MRAcquisitionType = properties['MRAcquisitionType']
    plane = properties['PrincipalPlane']
    InversionTime = properties["InversionTime"]
    scan_seq_input = properties['ScanningSequence']
    
    has_contrast_data = settings_config.get("has_contrast_data", False)

    # Step 1: Determine scanning sequence from input
    scan_seq = get_sequence_from_flags(filename, scan_seq_input, InversionTime, config)
    
    # Step 2: Determine orientation
    orientation = get_orientation_code(plane, MRAcquisitionType, config, settings_config)
    
    # Step 3: Prepare properties for classification
    classification_props = {
        'EchoTime': EchoTime,
        'RepetitionTime': RepetitionTime,
        'FlipAngle': FlipAngle,
        'InversionTime': InversionTime
    }
    
    # Step 4: Classify modality based on rules
    modality, rule_trace, scan_seq_override, has_contrast = classify_modality(
        classification_props,
        scan_seq,
        filename,
        config
    )
    
    # Apply sequence override from modality rule if needed
    if scan_seq_override:
        scan_seq = scan_seq_override
    
    # Step 5: Apply fallback sequence rules
    scan_seq = apply_sequence_fallbacks(scan_seq, modality, config)
    
    # Step 6: Determine contrast from keywords
    contrast = ''
    if has_contrast_data:
        if has_contrast:
            contrast = 'ce-gadolinium_'

    datatype = classify_datatype(modality, config)
    
    return {
        "scan_seq": scan_seq,
        "Orientation": orientation,
        "Modality": modality,
        "Contrast": contrast,
        "Datatype": datatype,
        "rule_trace": rule_trace
    }

def parse_time(t):
    """Parse AcquisitionTime; return None if missing or invalid."""

    if t is None or str(t).strip() in ("", "NA", "None"):
        return None

    t = str(t).strip()

    for fmt in ("%H:%M:%S.%f", "%H:%M:%S"):
        try:
            return datetime.strptime(t, fmt).time()
        except ValueError:
            continue

    print(f"[WARNING] Invalid AcquisitionTime: {t!r}.")
    return None


def build_filename(sub, ses, orientation, scan_seq, contrast, run, modality, ext, repeat):
    """Construct the final BIDS filename."""
    #TODO: add flags for orientation and scan_seq
    return f"sub-{sub}_ses-{ses}_acq-{orientation}{scan_seq}_{contrast}{run}{modality}{repeat}{ext}"

def compare_scans(scan1, scan2, check_niftis=True):
    """Compare nifti images if requested."""
    if not check_niftis:
        return False
    path1 = scan1["path_nii"]
    path2 = scan2["path_nii"]
    equal, _ = compare_nifti(path1, path2)
    return equal

def has_gad(filename, config):
    """Detect if filename indicates gadolinium contrast."""
    f = filename.lower()
    contrast_config = config.get("contrast_keywords", {}).get("ce-gadolinium", {})
    include_kw = contrast_config.get("include", [])
    exclude_kw = contrast_config.get("exclude", [])
    
    #TODO: check common gad indicators
    return check_filename_keywords(f, include_kw, exclude_kw)


def prepare_scans(all_scans, config):

    for scan in all_scans:

        scan["acq_time"] = parse_time(scan["AcquisitionTime"])
        scan["Contrast"] = scan.get("Contrast", "")
        scan["Gad_keywords"] = has_gad(scan["Original Filename"], config)

        scan["run"] = ""
        scan["Proposed Filename"] = ""
        scan["Repeat"] = ""

        scan["path_nii"] = scan.get(
            "Original Filepath", ""
        ).replace(scan["ext"], ".nii.gz") if os.path.exists(scan.get("Original Filepath", "").replace(scan["ext"], ".nii.gz")) else "NO NIFTI"

    return all_scans


def resolve_duplicates(all_scans, settings_config, check_niftis):
    has_contrast_data = settings_config.get("has_contrast_data", False)
    # 2. Group scans by base identity (excluding run/contrast)
    groups = {}
    for scan in all_scans:
        key = (scan["Sub"], scan["Ses"], scan["Orientation"], scan["scan_seq"], scan["Modality"])
        groups.setdefault(key, []).append(scan)

    # 3. Process each group
    for group in groups.values():
        if len(group)>1:
            # Sort by acquisition time
            group.sort(
                key=lambda x: (
                    x["acq_time"] is None,
                    x["acq_time"] if x["acq_time"] is not None
                    else datetime.strptime("00:00:00", "%H:%M:%S").time()
                )
            )

            # Split T1w into pre/post gad
            if group[0].get("Modality", "") == "T1w":
                if has_contrast_data:
                    gad = [s for s in group if s["Gad_keywords"]]
                    # gad = [s for s in group if s.get("Contrast", "") == "ce-gadolinium_"]

                    if gad:
                        post = gad
                        pre = [s for s in group if not s["Gad_keywords"]]
                    else:
                        # fallback to heuristic classification
                        ce = [s for s in group if s.get("Contrast", "") == "ce-gadolinium_"]
                        non_ce = [s for s in group if s.get("Contrast", "") == ""]

                        if ce and non_ce:
                            pre = non_ce
                            post = ce
                        else:
                            # heuristics failed, assume last scan is contrast
                            group[-1]["Contrast"] = "ce-gadolinium_"
                            pre = group[:-1]
                            post = [group[-1]]
                        

                    subgroups = [(pre, ""), (post, "ce-gadolinium_")]
                    #TODO: add time of the dcs flag
                else:
                    subgroups = [(group, group[0].get("Contrast", ""))]
            else:
                subgroups = [(group, group[0].get("Contrast", ""))]

            # 4. Assign run numbers & detect REPEAT
            for subgroup, contrast in subgroups:
                if len(subgroup) == 0:
                    continue
                for i, scan in enumerate(subgroup):
                    scan["Contrast"] = contrast

                    if len(subgroup) > 1:
                        # Compare with all previous in subgroup
                        is_repeat = any(
                            compare_scans(prev, scan, check_niftis=check_niftis)
                            for prev in subgroup[:i]
                        )
                        if is_repeat:
                            scan["run"] = ""
                            scan["Repeat"] = "_REPEAT"
                        else:
                            scan["run"] = f"run-{i+1}_"
    return all_scans

def build_all_filenames(all_scans):
    for scan in all_scans:
        scan["Proposed Filename"] = build_filename(
            scan["Sub"],
            scan["Ses"],
            scan["Orientation"],
            scan["scan_seq"],
            scan["Contrast"],
            scan["run"],
            scan["Modality"],
            scan["ext"],
            scan["Repeat"]
        )
    return all_scans

def generate_filenames(all_scans, config, settings_config, check_niftis=True):

    all_scans=prepare_scans(all_scans, config)
    all_scans=resolve_duplicates(all_scans, settings_config, check_niftis)
    all_scans=build_all_filenames(all_scans)

    return all_scans

def build_mapping_duplicates_control(dataFolder, project_folder, check_niftis=True):
    """
    Build a mapping of all scans with duplicate control and naming.
    
    Args:
        dataFolder: Path to the data folder containing patient data
        check_niftis: Whether to compare nifti files for duplicate detection
        config: ClassificationConfig instance
    
    Returns:
        tuple: (list of scans, DataFrame of scans, config)
    """
    settings_config = SettingsConfig()
    settings_config.load_from_file(
            project_folder / "project_settings.json"
        )
    
    classification_config_filename = settings_config.classification_config
    base_dir = Path(__file__).resolve().parent
    class_config_path = base_dir / "classification_configs" / classification_config_filename
    config = ClassificationConfig()
    config.load_from_file(class_config_path)
 
    files=get_json_files(dataFolder)
    all_scans = []

    for f in files:
        scan = extract_properties(f)

        if scan is not None:
            all_scans.append(scan)

    print(f"Total JSON files found: {len(files)}")
    print(f"Successfully processed: {len(all_scans)}")
    print(f"Failed: {len(files) - len(all_scans)}")
    for scan in all_scans:
        components = derive_names(scan, config, settings_config)
        scan.update(components)
        filename = scan["Original Filename"]
        scan["Sub"] = filename.split('_')[0].split('-')[1].zfill(3)
        scan["Ses"] = filename.split('_')[1].split('-')[1].zfill(2)
        scan["ext"] = os.path.splitext(filename)[1]
    
    # Generate final filenames in batch (GUI-friendly)
    new_scans = generate_filenames(all_scans, config, settings_config, check_niftis=check_niftis)

    new_scans_df=pd.DataFrame(new_scans)

    return new_scans, new_scans_df, config

def save2file(list_names,list_paths,output='.csv'):

    fields = set()
    for d in list_paths:
        fields |= set(d.keys())
    # write the data to a CSV file:
    #PATH NAMES
    with open(f'/home/mloureiro/glioma/Dataset Curation/Final_excels/path_names{output}', 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=sorted(fields), delimiter=';')
        writer.writeheader()
        for d in list_paths:
            row = {}
            for field in fields:
                row[field] = d.get(field, '')  # use '' as default value if field is not present
            writer.writerow(row)

    fields = set()
    for d in list_names:
        fields |= set(d.keys())
    # write the data to a CSV file
    #Filenames
    with open(f'/home/mloureiro/glioma/Dataset Curation/Artigo_Data_Curation/Excels_anat_names/new_names{output}', 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=sorted(fields), delimiter=';')
        writer.writeheader()
        for d in list_names:
            row = {}
            for field in fields:
                row[field] = d.get(field, '')  # use '' as default value if field is not present
            writer.writerow(row)

def save2file_justnames(list_names,output='.csv'):
    fields = set()
    for d in list_names:
        fields |= set(d.keys())
    # write the data to a CSV file
    #Filenames
    with open(f'/home/mloureiro/glioma/Dataset Curation/Artigo_Data_Curation/Excels_anat_names/new_names{output}', 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=sorted(fields), delimiter=';')
        writer.writeheader()
        for d in list_names:
            row = {}
            for field in fields:
                row[field] = d.get(field, '')  # use '' as default value if field is not present
            writer.writerow(row)
#%%
# dataFolder = "/generalData/glioma/jsons_4_article/original_jsons/"
# list_names, df_names, config=build_mapping_duplicates_control(dataFolder, check_niftis=False)
# save2file_justnames(list_names,output='gui_rules_user_12-06-2026_run1.csv')

def change_paths(list_names,change=False):
    list_paths=[]
    for d in list_names:
        old_filename_json=d['filename']
        old_filename=os.path.splitext(old_filename_json)[0]
        new_filename_json=d['final filename']
        sub_num = old_filename.split('_')[0].split('-')[1].zfill(3)
        ses_num = old_filename.split('_')[1].split('-')[1].zfill(2)
        path=f'/generalData/glioma/jsons_4_article/original_jsons/sub-{sub_num}/ses-{ses_num}/anat/'
        old_filename_nii=f'{old_filename}.nii'
        old_filename_nii_gz=f'{old_filename}.nii.gz'
        if '?' not in new_filename_json and 'MISSING' not in new_filename_json and 'sub-002_ses-08_anat_t1_se_sag_320_20180620110326_3' not in old_filename and '/home/glioma/sub-002/ses-08/anat/sub-002_ses-08_anat_t2_tse_tra_3mm_20180620110326_4' not in old_filename:# and 'sub-045_ses-04' not in old_filename and 'sub-041_ses-01' not in old_filename and 'sub-030_ses-02' not in old_filename and 'sub-030_ses-03' not in old_filename and 'sub-030_ses-04' not in old_filename and 'sub-030_ses-05' not in old_filename:
            new_filename=os.path.splitext(new_filename_json)[0]
            new_filename_nii=f'{new_filename}.nii'
            new_filename_nii_gz=f'{new_filename}.nii.gz'
            new_path=os.path.join(path,new_filename_nii)
            if os.path.exists(os.path.join(path,old_filename_json)):
                print('change name')
                print(new_filename)
                # Do NOT Change this Part!!!!!
                if change:
                    print('ERRROROROR CHANGING')
                    os.rename(os.path.join(path,old_filename_json),os.path.join(path,new_filename_json))
            else:
                print('doesnt exist', os.path.join(path,old_filename_json))
            if os.path.exists(os.path.join(path,old_filename_nii)):
                print('change name')
                if change:
                    print('ERRROROROR CHANGING')
                    os.rename(os.path.join(path,old_filename_nii),os.path.join(path,new_filename_nii))
            elif os.path.exists(os.path.join(path,old_filename_nii_gz)):
                print('change name')
                if change:
                    print('ERRROROROR CHANGING')
                    os.rename(os.path.join(path,old_filename_nii_gz),os.path.join(path,new_filename_nii_gz))
            else:
                print('doesnt exist', os.path.join(path,old_filename_nii))    
        else:
            print('NOT CHANGE ANAT')
            new_filename_nii_gz=f'{old_filename}_anat.nii.gz'
            new_filename_nii=f'{old_filename}_anat.nii'
            new_filename_json=f'{old_filename}_anat.json'
            print(new_filename_nii,new_filename_json)
            if os.path.exists(os.path.join(path,old_filename_json)):
                print('change name')
                print(new_filename)
                if change:
                    print('ERRROROROR CHANGING')
                    os.rename(os.path.join(path,old_filename_json),os.path.join(path,new_filename_json))
                print(os.path.join(path,old_filename_json),os.path.join(path,new_filename_json))
            else:
                print('doesnt exist', os.path.join(path,old_filename_json))
            if os.path.exists(os.path.join(path,old_filename_nii)):
                print('change name')
                if change:
                    print('ERRROROROR CHANGING')
                    os.rename(os.path.join(path,old_filename_nii),os.path.join(path,new_filename_nii))
                print(os.path.join(path,old_filename_nii),os.path.join(path,new_filename_nii))
            elif os.path.exists(os.path.join(path,old_filename_nii_gz)):
                print('change name')
                if change:
                    print('ERRROROROR CHANGING')
                    os.rename(os.path.join(path,old_filename_nii_gz),os.path.join(path,new_filename_nii_gz))
                print(os.path.join(path,old_filename_nii_gz),os.path.join(path,new_filename_nii_gz))
            else:
                print('doesnt exist', os.path.join(path,old_filename_nii))
        
        list_paths+=[{'path':path,'old filename':old_filename,'new filename json': new_filename_json, 'new filename nii':new_filename_nii}]
    return list_paths    
                                

#save old and new names to file
