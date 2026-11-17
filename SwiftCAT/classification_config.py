# SwiftCAT - Swift MRI Curation and Anotation Tool
# Copyright (C) 2026 Marta P. Loureiro

import copy
import json
from pathlib import Path

# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

CONFIG_DIR = BASE_DIR / "classification_configs"
CONFIG_DIR.mkdir(exist_ok=True)

DEFAULT_CONFIG_FILE = CONFIG_DIR / "class_config_default.json"


# =========================================================
# HELPERS
# =========================================================

def load_default_config():
    """
    Load the immutable default configuration.
    """
    if not DEFAULT_CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Default configuration not found:\n{DEFAULT_CONFIG_FILE}"
        )

    with open(DEFAULT_CONFIG_FILE, "r") as f:
        return json.load(f)


# =========================================================
# CLASS
# =========================================================

class ClassificationConfig:
    """
    Configuration manager for classification rules.

    This is a pure config object (no global state).
    """

    def __init__(self, config_dict=None):
        self.config = (
            copy.deepcopy(config_dict)
            if config_dict is not None
            else copy.deepcopy(load_default_config())
        )

    # -----------------------------------------------------
    # File I/O
    # -----------------------------------------------------

    def save_to_file(self, filepath):
        """Save configuration to JSON file."""

        filepath = Path(filepath)

        # Prevent overwriting shipped default
        if filepath.resolve() == DEFAULT_CONFIG_FILE.resolve():
            raise ValueError(
                "The default configuration cannot be overwritten."
            )

        with open(filepath, "w") as f:
            json.dump(self.config, f, indent=2)

        print(f"Classification config saved to {filepath}")

    def load_from_file(self, filepath):
        """Load configuration from JSON file."""

        filepath = Path(filepath)

        with open(filepath, "r") as f:
            self.config = json.load(f)

        print(f"Classification config loaded from {filepath}")

    def reset_to_defaults(self):
        """Restore configuration from default template."""
        default = load_default_config()

        self.config.clear()
        self.config.update(copy.deepcopy(default))

    # -----------------------------------------------------
    # Generic access
    # -----------------------------------------------------

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    # -----------------------------------------------------
    # Rule helpers
    # -----------------------------------------------------

    def get_rule_names(self):
        return [
            r.get("name")
            for r in self.config.get("modality_rules", [])
        ]

    def get_rule(self, rule_name):
        for rule in self.config.get("modality_rules", []):
            if rule.get("name") == rule_name:
                return rule
        return None

    def update_rule(self, rule_name, updates):
        """
        Update an entire modality rule by name.
        """
        for rule in self.config.get("modality_rules", []):
            if rule.get("name") == rule_name:
                rule.update(updates)
                return True
        return False

    def update_threshold(self, rule_name, param_name, min_val=None, max_val=None):
        """
        Update threshold values inside a rule.
        """

        for rule in self.config.get("modality_rules", []):
            if rule.get("name") == rule_name:

                if "conditions" not in rule:
                    rule["conditions"] = {}

                if param_name not in rule["conditions"]:
                    rule["conditions"][param_name] = {}

                if min_val is not None:
                    rule["conditions"][param_name]["min"] = min_val

                if max_val is not None:
                    rule["conditions"][param_name]["max"] = max_val

                return True

        return False


# =========================================================
# FACTORY FUNCTIONS (no globals)
# =========================================================

def create_new_classification_config():
    """
    Create a fresh editable config from defaults.
    """
    return ClassificationConfig()


def load_classification_config(filepath):
    """
    Load classification config from file.
    """
    config = ClassificationConfig()
    config.load_from_file(filepath)
    return config