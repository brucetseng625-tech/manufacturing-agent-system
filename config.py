import copy
import datetime
import json
import os
import threading


def _repo_root():
    return os.path.dirname(os.path.abspath(__file__))


def resolve_repo_path(path_value):
    """Resolve a repo-relative path to an absolute path."""
    if not path_value:
        return path_value
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(_repo_root(), path_value)


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


DEFAULT_CONFIG = {
    "_description": "Default config for the Manufacturing Agent System.",
    "_source": "default",
    "server": {
        "port": 8000,
    },
    "runtime": {
        "default_data_dir": "mock_data",
        "default_data_source": "local",
        "history_last": 10,
        "metrics_window_hours": 24,
    },
    "paths": {
        "policy_config": "policies/active.json",
        "log_dir": "logs",
    },
    "security": {
        "api_token": None,
    },
    "llm": {
        "openai_api_key": None,
        "local_api_url": "http://localhost:11434/v1",
        "local_model": "qwen2.5-7b",
        "cloud_model": "gpt-4o",
        "sensitivity_keywords": ["log", "safety", "sensor", "異常", "BOM", "code", "原始碼", "感測器", "安全", "除錯", "手冊"],
    },
    "integrations": {
        "default_asana_task": None,
    },
    "rollout": {
        "local": {
            "enabled": True,
        },
        "live": {
            "enabled": True,
        },
        "auto": {
            "enabled": True,
        },
    },
}

_ORIGINAL_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG)
_local = threading.local()
_config_lock = threading.Lock()
_config_metadata = {
    "source": "default",
    "last_reload_at": None,
    "last_reload_success": True,
    "last_reload_error": None,
    "reload_count": 0,
}

_ENV_OVERRIDES = {
    "MAS_SERVER_PORT": ("server", "port", int),
    "MAS_DEFAULT_DATA_DIR": ("runtime", "default_data_dir", str),
    "MAS_DEFAULT_DATA_SOURCE": ("runtime", "default_data_source", str),
    "MAS_HISTORY_LAST": ("runtime", "history_last", int),
    "MAS_METRICS_WINDOW_HOURS": ("runtime", "metrics_window_hours", int),
    "MAS_POLICY_CONFIG_PATH": ("paths", "policy_config", str),
    "MAS_LOG_DIR": ("paths", "log_dir", str),
    "MAS_API_TOKEN": ("security", "api_token", str),
    "MAS_DEFAULT_ASANA_TASK": ("integrations", "default_asana_task", str),
    "MAS_ROLLOUT_LOCAL_ENABLED": ("rollout", "local", "enabled", bool),
    "MAS_ROLLOUT_LIVE_ENABLED": ("rollout", "live", "enabled", bool),
    "MAS_ROLLOUT_AUTO_ENABLED": ("rollout", "auto", "enabled", bool),
    "MAS_LLM_OPENAI_API_KEY": ("llm", "openai_api_key", str),
    "MAS_LLM_LOCAL_API_URL": ("llm", "local_api_url", str),
    "MAS_LLM_LOCAL_MODEL": ("llm", "local_model", str),
    "MAS_LLM_CLOUD_MODEL": ("llm", "cloud_model", str),
}


def _default_config_path():
    return os.path.join(_repo_root(), "config.json")


def _apply_env_overrides(config):
    for env_name, path_info in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw in (None, ""):
            continue
        # Handle nested paths: rollout.local.enabled vs runtime.default_data_dir
        if len(path_info) == 3:
            section, key, caster = path_info
            config.setdefault(section, {})
            config[section][key] = caster(raw)
        elif len(path_info) == 4:
            section, subsection, key, caster = path_info
            config.setdefault(section, {})
            config[section].setdefault(subsection, {})
            config[section][subsection][key] = caster(raw)
    return config


def validate_config(config):
    runtime = config.get("runtime", {})
    server = config.get("server", {})

    data_source = runtime.get("default_data_source", "local")
    if data_source not in ("local", "live", "auto"):
        raise ValueError("runtime.default_data_source must be one of: local, live, auto")

    port = server.get("port", 8000)
    if not isinstance(port, int) or port <= 0 or port > 65535:
        raise ValueError("server.port must be an integer between 1 and 65535")

    history_last = runtime.get("history_last", 10)
    if not isinstance(history_last, int) or history_last <= 0:
        raise ValueError("runtime.history_last must be a positive integer")

    metrics_window = runtime.get("metrics_window_hours", 24)
    if not isinstance(metrics_window, int) or metrics_window <= 0:
        raise ValueError("runtime.metrics_window_hours must be a positive integer")

    return True


def load_config(config_path=None):
    config = copy.deepcopy(_ORIGINAL_DEFAULTS)
    resolved_path = config_path or _default_config_path()
    source = "default"

    if os.path.isfile(resolved_path):
        with open(resolved_path, "r", encoding="utf-8") as f:
            override = json.load(f)
        config = _deep_merge(config, override)
        source = f"file:{resolved_path}"

    config = _apply_env_overrides(config)
    validate_config(config)
    config["_source"] = source
    return config


def sanitize_config(config):
    sanitized = copy.deepcopy(config)

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                lower = key.lower()
                if any(token in lower for token in ("token", "secret", "password")) and value:
                    node[key] = "***REDACTED***"
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(sanitized)
    return sanitized


def get_config(raw=False):
    config = getattr(_local, "config", DEFAULT_CONFIG)
    return copy.deepcopy(config) if raw else sanitize_config(config)


def set_config(config):
    _local.config = copy.deepcopy(config)


def get_config_value(key_path, default=None, raw=True):
    current = get_config(raw=raw)
    value = current
    for part in key_path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default
    return value


def reload_config(config_path=None):
    global DEFAULT_CONFIG  # noqa: PLW0603

    now = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    result = {
        "success": False,
        "source": None,
        "error": None,
        "reloaded_at": now,
    }

    try:
        config = load_config(config_path)
        with _config_lock:
            DEFAULT_CONFIG.clear()
            DEFAULT_CONFIG.update(copy.deepcopy(config))
            _config_metadata["source"] = config.get("_source", "default")
            _config_metadata["last_reload_at"] = now
            _config_metadata["last_reload_success"] = True
            _config_metadata["last_reload_error"] = None
            _config_metadata["reload_count"] += 1
        _local.config = copy.deepcopy(DEFAULT_CONFIG)
        result["success"] = True
        result["source"] = config.get("_source", "default")
    except Exception as e:
        with _config_lock:
            _config_metadata["last_reload_at"] = now
            _config_metadata["last_reload_success"] = False
            _config_metadata["last_reload_error"] = str(e)
            _config_metadata["reload_count"] += 1
        result["source"] = "error"
        result["error"] = str(e)
    return result


def get_config_metadata():
    with _config_lock:
        return dict(_config_metadata)
