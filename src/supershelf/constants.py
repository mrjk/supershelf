"""Names shared by discovery and the command line."""

APP_NAME = "supershelf"
LOGGER_NAME = APP_NAME

ENV_CONFIG = "SUPERSHELF_CONFIG"
ENV_PROFILES = "SUPERSHELF_PROFILES"
ENV_KIND_OVERRIDES_MODE = "SUPERSHELF_KIND_OVERRIDES_MODE"

CONFIG_SECTION = "config"
PROFILE_KEY = "profile"
DEFAULT_PROFILE = "default"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_ROOT_DIR_TEMPLATE = "{{ __profile_dir__ }}"
DEFAULT_DATABASE_FILE_TEMPLATE = (
    "{{ __root_dir__ }}/profile.{{ __profile__ }}.sqlite"
)
DEFAULT_CACHE_FILE_TEMPLATE = "{{ __root_dir__ }}/profile.{{ __profile__ }}.cache"
DEFAULT_KIND_OVERRIDES_TEMPLATES = (
    "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.csv",
    "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.toml",
    "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yaml",
    "{{ __root_dir__ }}/profile.{{ __profile__ }}.{{ __kind__ }}.yml",
)

KEY_DEFAULT_DATE_FORMAT = "default_date_format"
KEY_ROOT_DIR = "root_dir"
KEY_DATABASE_FILE = "database_file"
KEY_CACHE_FILE = "cache_file"
KEY_INPUTS = "inputs"
KEY_MATCH_RULES = "match_rules"
KEY_DEFAULT_VARS = "default_vars"
KEY_KIND_OVERRIDES = "kind_overrides_config"
KEY_KIND_OVERRIDES_MODE = "kind_overrides_mode"
KEY_KIND_OVERRIDES_DATE_FORMAT = "kind_overrides_date_format"
KEY_KIND_OVERRIDES_SEP = "kind_overrides_sep"
DEFAULT_KIND_OVERRIDES_SEP = ","
KIND_CSV_PATH = "PATH"
KIND_OVERRIDE_MODES = ("auto", "manual", "always", "disabled")
KIND_MODE_AUTO = "auto"
KIND_MODE_MANUAL = "manual"
KIND_MODE_ALWAYS = "always"
KIND_MODE_DISABLED = "disabled"
KEY_VAR_MODULES = "var_modules"
KEY_OVERRIDES = "overrides"
KEY_RULE_VARS = "vars"
KEY_OVERRIDE_PATH = "path"

VAR_KIND = "__kind__"
VAR_RULE_NAME = "__rule_name__"
VAR_CTIME = "__ctime__"
VAR_MTIME = "__mtime__"
VAR_FILE_HASH = "__file_hash__"
VAR_FILE_NAME = "__file_name__"
VAR_FILE_STEM = "__file_stem__"
VAR_FILE_EXT = "__file_ext__"
VAR_FILE_PATH = "__file_path__"
VAR_FILE_DIR = "__file_dir__"
VAR_FILE_CTIME = "file_ctime"
VAR_FILE_MTIME = "file_mtime"
VAR_DATE = "__date__"
VAR_INPUT = "__input__"

INTERNAL_NAMES = (
    VAR_KIND,
    VAR_RULE_NAME,
    VAR_CTIME,
    VAR_MTIME,
    VAR_FILE_HASH,
    VAR_FILE_NAME,
    VAR_FILE_STEM,
    VAR_FILE_EXT,
    VAR_FILE_PATH,
    VAR_FILE_DIR,
)
ALIAS_NAMES = (VAR_FILE_CTIME, VAR_FILE_MTIME)
DATE_TEXT = "%Y-%m-%d"

VAR_GLOBALS = "GLOBALS"
VAR_FILTERS = "FILTERS"

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
