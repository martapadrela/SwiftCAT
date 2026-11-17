# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

"""
Helper functions for image classification using the configuration rules.
These functions evaluate the classification rules to determine modality, sequence, etc.
"""

from classification_config import (
    ClassificationConfig,
    create_new_classification_config,
    load_classification_config,
)

from project_settings_config import (
    SettingsConfig,
    create_new_settings,
    load_project_settings,
)

def has_valid_value(value, config):

    missing_value = config.get(
        "constants", {}
    ).get(
        "missing_numeric_value",
        100000
    )

    return value is not None and value != missing_value

def check_condition(value, condition_range, config):
    """
    Check if a value falls within a condition range.
    
    Args:
        value: The value to check
        condition_range: Dict with "min" and/or "max" keys, or None for no limit
    
    Returns:
        bool: True if value satisfies the condition
    """
    if not has_valid_value(value, config):
        return False
    
    if condition_range is None:
        return True
    
    min_val = condition_range.get("min")
    max_val = condition_range.get("max")
    
    if min_val is not None and value < min_val:
        return False
    if max_val is not None and value > max_val:
        return False
    
    return True


def check_sequence_rule(scan_seq, sequence_condition):
    """Check if scan sequence matches a condition."""
    if "sequence" not in sequence_condition:
        return True
    return scan_seq == sequence_condition["sequence"]


def check_all_conditions(properties, rule, config):
    """
    Check if all conditions in a rule are satisfied.
    
    Args:
        properties: Dict with EchoTime, RepetitionTime, FlipAngle, etc.
        rule: Classification rule dict
    
    Returns:
        bool: True if all conditions are met
    """
    # Check basic conditions
    conditions = rule.get("conditions", {})
    for param_name, condition_range in conditions.items():
        if param_name in properties:
            if not check_condition(properties[param_name], condition_range, config):
                return False
        else:
            return False
    
    # Check sequence-specific conditions
    sequence_conditions = rule.get("sequence_conditions")
    if sequence_conditions:
        found_match = False
        for seq_cond in sequence_conditions:
            seq_match = check_sequence_rule(
                properties.get("scan_seq"), seq_cond
            )
            if seq_match:
                # Check all conditions within this sequence
                seq_cond_copy = seq_cond.copy()
                seq_cond_copy.pop("sequence", None)
                all_match = True
                for param_name, condition_range in seq_cond_copy.items():
                    if param_name in properties:
                        if not check_condition(properties[param_name], condition_range, config):
                            all_match = False
                            break
                if all_match:
                    found_match = True
                    break
        if not found_match:
            return False
    
    return True


def check_required_inversion(properties, rule, config):
    """Check if inversion time requirement is satisfied."""
    requires_inversion = rule.get("requires_inversion", False)
    forbid_inversion = rule.get("forbid_inversion", False)
    inversion_time = properties.get("InversionTime")
    has_inversion = has_valid_value(inversion_time, config)
    
    if requires_inversion and not has_inversion:
        return False
    
    if forbid_inversion and has_inversion:
        return False
    
    return True


def check_sequence_match(scan_seq, rule):
    """Check if scan sequence matches rule requirement."""
    required_seq = rule.get("sequence")
    if required_seq is None:
        return True
    return scan_seq == required_seq


def check_filename_keywords(filename, keywords_list, exclude_keywords=None):
    """
    Check if filename contains any of the keywords.
    
    Args:
        filename: The filename to check
        keywords_list: List of keywords to look for
        exclude_keywords: List of keywords that must NOT be present
    
    Returns:
        bool: True if conditions are met
    """
    if keywords_list is None:
        return False
    
    f = filename.lower()
    
    # Check exclude keywords first
    if exclude_keywords:
        for kw in exclude_keywords:
            if kw.lower() in f:
                return False
    
    # Check for any include keyword
    for kw in keywords_list:
        if kw.lower() in f:
            return True
    return False


def classify_modality(properties, scan_seq, filename, config):
    """
    Classify image modality based on rules.
    
    Args:
        properties: Dict with imaging parameters
        scan_seq: Scanning sequence (GR, SE, SEIR, etc.)
        filename: Original filename for keyword matching
        config: ClassificationConfig instance, or None to use global
    
    Returns:
        tuple: (modality, rule_trace, scan_seq_override, has_contrast)
    """
    
    modality_rules = config.get("modality_rules", [])
    rule_trace = ""
    has_contrast = False
    
    # Add scan_seq to properties for rule evaluation
    props_with_seq = properties.copy()
    props_with_seq["scan_seq"] = scan_seq
    
    for i, rule in enumerate(modality_rules):
        rule_name = rule.get("name", f"rule_{i}")
        
        # Check inversion requirement
        if not check_required_inversion(props_with_seq, rule, config):
            continue
        
        # Check sequence match
        if not check_sequence_match(scan_seq, rule):
            continue
        
        # Check all conditions
        if not check_all_conditions(props_with_seq, rule, config):
            continue
        
        # Rule matched!
        modality = rule.get("modality", "NA")
        scan_seq_override = rule.get("scan_seq_override")
        
        # Check for contrast indicator keywords (non-blocking)
        if "contrast_keywords" in rule:
            keywords = rule.get("contrast_keywords", [])
            exclude_kw = rule.get("contrast_exclude_keywords", [])
            has_contrast = check_filename_keywords(filename, keywords, exclude_kw)
        
        rule_trace += f"[{rule_name}]"
        return modality, rule_trace, scan_seq_override, has_contrast
    
    # No rule matched
    return "NA", rule_trace, None, False

def classify_datatype(modality, config):
    """
    Classify datatype based on modality using rules.

    Args:
        modality: The classified modality (e.g., "T1w", "BOLD")
        config: ClassificationConfig instance, or None to use global

    Returns:
        str: Datatype (e.g., "anat", "func", "dwi", etc.)
    """

    datatype_rules = config.get("datatype_rules", {})

    for datatype, rule in datatype_rules.items():
        if modality in rule.get("modality", []):
            return datatype

    # No rule matched
    return "NA"

def get_sequence_from_flags(filename, scan_seq, inversion_time, config):
    """
    Determine scanning sequence from flags and parameters.
    """

    seq_rules = config.get("sequence_rules", {})

    has_inversion = has_valid_value(inversion_time, config)

    # First pass: check configured flags
    for seq_name, rule in seq_rules.items():

        flags = rule.get("flags", [])

        if scan_seq not in flags:
            continue

        requires_inversion = rule.get("requires_inversion", False)

        # Match inversion requirements
        if requires_inversion and has_inversion:
            return seq_name

        if not requires_inversion and not has_inversion:
            return seq_name


    # Fallback to filename keywords
    f = filename.lower()

    for seq_name, rule in seq_rules.items():
        for kw in rule.get("sequence_keywords", []):
            if kw.lower() in f:
                return seq_name

    # Special RM handling (not represented in config)
    if scan_seq == "RM" and not has_inversion:
        return ""

    return scan_seq

def get_orientation_code(plane, mra_type, config, settings_config):
    """
    Returns orientation suffix based on project settings.

    Modes:
        - anatomical: ax / cor / sag / 3D
        - dimensionality: 2D / 3D
        - none: ""
    """

    # ----------------------------
    # Load settings
    # ----------------------------
    
    orientation_mode = settings_config.orientation_mode
    valid_modes = settings_config.get_orientation_modes()

    if orientation_mode not in valid_modes:
        raise ValueError(
            f"Invalid orientation_mode: {orientation_mode}. "
            f"Valid options: {sorted(valid_modes)}"
        )

    orientation_rules = config.get("orientation_rules", {})

    # ----------------------------
    # MODE: none
    # ----------------------------
    if orientation_mode == "none":
        return ""

    # ----------------------------
    # MODE: dimensionality
    # ----------------------------
    if orientation_mode == "dimensionality":

        if mra_type == "3D":
            return orientation_rules.get("3D", {}).get("code", "3D")

        return orientation_rules.get("2D", {}).get("code", "2D")

    # ----------------------------
    # MODE: anatomical
    # ----------------------------
    if orientation_mode == "anatomical":

        # 3D always gets 3D
        if mra_type == "3D":
            return orientation_rules.get("3D", {}).get("code", "3D")

        # match plane rules for 2D
        for rule in orientation_rules.values():

            if "plane" not in rule:
                continue

            if rule["plane"] != plane:
                continue

            # Unknown plane: do not guess an anatomical orientation
            if plane == "unknown":
                return "NA"

            allowed = rule.get("mr_acquisition_type", [])

            if not isinstance(allowed, list):
                allowed = [allowed]

            if mra_type in allowed:
                return rule.get("code", "")

    return ""


def apply_sequence_fallbacks(scan_seq, modality, config):

    rules = config.get("fallback_rules", {})

    for rule in rules.values():

        if (scan_seq == rule.get("scan_seq")
            and modality == rule.get("modality")):
            return rule.get("result", scan_seq)

    return scan_seq