# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

"""
Project settings management.

Each project/output folder contains its own
project_settings.json.

A template file is used when creating a new project.
"""

import copy
import json
from pathlib import Path


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_SETTINGS_TEMPLATE = (
    BASE_DIR / "default_project_settings.json"
)


# =========================================================
# HELPERS
# =========================================================

def load_default_config():
    """
    Load the default project settings template.
    """

    if not DEFAULT_SETTINGS_TEMPLATE.exists():
        raise FileNotFoundError(
            f"Default settings template not found:\n"
            f"{DEFAULT_SETTINGS_TEMPLATE}"
        )

    with open(DEFAULT_SETTINGS_TEMPLATE, "r") as f:
        return json.load(f)


# =========================================================
# SETTINGS CONFIG
# =========================================================

class SettingsConfig:
    """
    Configuration manager for project settings.
    """

    def __init__(self, config_dict=None):

        self.config = (
            copy.deepcopy(config_dict)
            if config_dict is not None
            else copy.deepcopy(load_default_config())
        )

    # -----------------------------------------------------
    # File operations
    # -----------------------------------------------------

    def save_to_file(self, filepath):

        filepath = Path(filepath)

        with open(filepath, "w") as f:
            json.dump(self.config, f, indent=2)

        print(f"Settings saved to {filepath}")

    def load_from_file(self, filepath):

        filepath = Path(filepath)

        with open(filepath, "r") as f:
            self.config = json.load(f)

        print(f"Settings loaded from {filepath}")

    def reset_to_defaults(self):
        """
        Restore settings from template.
        """

        self.config = copy.deepcopy(
            load_default_config()
        )

    # -----------------------------------------------------
    # Generic access
    # -----------------------------------------------------

    def get(self, key, default=None):

        return self.config.get(key, default)

    def set(self, key, value):

        self.config[key] = value

    # -----------------------------------------------------
    # Classification config
    # -----------------------------------------------------

    @property
    def classification_config(self):

        return self.get(
            "classification_config",
            "class_config_default.json"
        )

    @classification_config.setter
    def classification_config(self, config_name):

        self.set(
            "classification_config",
            config_name
        )

    def classification_config_reset_default(self):

        self.set(
            "classification_config",
            "class_config_default.json"
        )

    # -----------------------------------------------------
    # Orientation mode
    # -----------------------------------------------------

    @property
    def orientation_mode(self):

        orientation_settings = self.get(
                "orientation_settings", 
                {})

        return orientation_settings.get(
            "orientation_mode",
            "anatomical"
        )

    @orientation_mode.setter
    def orientation_mode(self, mode):

        orientation_settings = copy.deepcopy(self.get(
            "orientation_settings",
            {}
        ))

        orientation_settings["orientation_mode"] = mode

        self.set(
            "orientation_settings",
            orientation_settings
        )

    # -----------------------------------------------------
    # Orientation mode metadata
    # -----------------------------------------------------

    def get_orientation_modes(self):
        """
        Returns a list of available mode names.

        Example:
            ["anatomical", "dimensionality", "none"]
        """

        orientation_settings = self.get(
            "orientation_settings",
            {}
        )

        modes = orientation_settings.get(
            "modes",
            []
        )

        return [
            mode["name"]
            for mode in modes
        ]

    def get_orientation_mode_description(self, mode_name):
        """
        Returns the description for a mode.

        Example:
            get_orientation_mode_description("anatomical")
        """

        orientation_settings = self.get(
            "orientation_settings",
            {}
        )

        modes = orientation_settings.get(
            "modes",
            []
        )

        for mode in modes:

            if mode.get("name") == mode_name:

                return mode.get(
                    "description",
                    ""
                )

        return ""

    def get_current_orientation_description(self):
        """
        Returns the description of the
        currently selected orientation mode.
        """

        return self.get_orientation_mode_description(
            self.orientation_mode
        )

    # -----------------------------------------------------
    # Options
    # -----------------------------------------------------

    def get_option_values(self, option_name):

        options = self.get(
            "options",
            {}
        )

        return options.get(
            option_name,
            []
        )

    def set_option_values(
        self,
        option_name,
        values
    ):

        options = copy.deepcopy(self.get(
            "options",
            {}
        ))

        options[option_name] = values

        self.set(
            "options",
            options
        )

    def add_option_value(
        self,
        option_name,
        value
    ):
        """
        Add a single value to an option list.

        Returns True if a value was added,
        False otherwise.
        """

        # NiceGUI select may emit:
        # {'label': 'sag', 'value': 'sag'}
        if isinstance(value, dict):
            value = value.get("label", "")

        value = str(value).strip()

        if not value:
            return False

        options = self.get("options", {})

        values = options.get(option_name, [])

        if value in values:
            return False

        values.append(value)

        options[option_name] = values

        self.set("options", options)

        return True
    
    def remove_option_value(
        self,
        option_name,
        value
    ):
        """
        Remove a single value from an option list.

        Example:
            ["T1w", "T2w", "FLAIR"]

            remove_option_value(
                "modality",
                "FLAIR"
            )

            -> ["T1w", "T2w"]
        """

        options = self.get(
            "options",
            {}
        )

        values = options.get(
            option_name,
            []
        )

        if value in values:
            values.remove(value)

        options[option_name] = values

        self.set(
            "options",
            options
        )


# =========================================================
# FACTORY FUNCTIONS
# =========================================================

def create_new_settings():
    """
    Create settings from template.
    """

    return SettingsConfig()


def load_project_settings(filepath):
    """
    Load settings from an existing project.
    """

    settings = SettingsConfig()
    settings.load_from_file(filepath)

    return settings