"""Names shared by discovery and the command line."""

APP_NAME = "supershelf"
LOGGER_NAME = APP_NAME

ENV_CONFIG = "SUPERSHELF_CONFIG"
ENV_PROFILES = "SUPERSHELF_PROFILES"

CONFIG_SECTION = "config"
PROFILE_KEY = "profile"
DEFAULT_PROFILE = "default"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_ROOT_DIR_TEMPLATE = "{{ __profile_dir__ }}"
DEFAULT_DATABASE_FILE_TEMPLATE = (
    "{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite"
)
DEFAULT_CACHE_FILE_TEMPLATE = "{{ __root_dir__ }}/profile.{{ __profile__ }}.cache"

KEY_DEFAULT_DATE_FORMAT = "default_date_format"
KEY_ROOT_DIR = "root_dir"
KEY_DATABASE_FILE = "database_file"
KEY_CACHE_FILE = "cache_file"
KEY_INPUTS = "inputs"

VAR_PROFILE = "__profile__"
VAR_PROFILE_NAME = "__profile_name__"
VAR_PROFILE_TYPE = "__profile_type__"
VAR_PROFILE_PATH = "__profile_path__"
VAR_PROFILE_DIR = "__profile_dir__"
VAR_PROFILE_FILE = "__profile_file__"
VAR_DEFAULT_DATE_FORMAT = "__default_date_format__"
VAR_CONFIG_DATA = "__config_data__"
VAR_ROOT_DIR = "__root_dir__"
VAR_DATABASE_FILE = "__database_file__"
VAR_CACHE_FILE = "__cache_file__"

SINGLETON_STEM = APP_NAME
PROFILE_PREFIX = "profile."

FILE_TYPE_TOML = "toml"
FILE_TYPE_YAML = "yaml"

# Preference order: toml, then yaml, then yml. yml is stored as yaml.
CONFIG_SUFFIXES = (".toml", ".yaml", ".yml")
SUFFIX_TYPES = {
    ".toml": FILE_TYPE_TOML,
    ".yaml": FILE_TYPE_YAML,
    ".yml": FILE_TYPE_YAML,
}
