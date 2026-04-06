import os
import yaml
from pathlib import Path
from dotenv import load_dotenv, set_key

load_dotenv(Path(__file__).parent.resolve() / ".env")

PROJECT_ROOT = Path(__file__).parent.resolve()

CONFIG_PATH = PROJECT_ROOT / "config.yaml"
ENV_PATH = PROJECT_ROOT / ".env"


# Custom YAML representer: use block scalar (|) for multiline strings
def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_yaml_dumper = yaml.SafeDumper
_yaml_dumper.add_representer(str, _str_representer)


def load_config(path=CONFIG_PATH):
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}

def save_config(config, path=CONFIG_PATH):
    try:
        with open(path, "w") as f:
            yaml.dump(config, f, Dumper=_yaml_dumper, default_flow_style=False, sort_keys=False)
    except Exception as e:
        print(f"Error saving config: {e}")

def get_env_value(key, default=None):
    return os.getenv(key, default)

def get_account_password(account_id):
    if not account_id:
        return None
    # account_id should be a string ID (e.g. "GMX")
    env_key = f"PASSWORD_{account_id.upper()}"
    return os.getenv(env_key)

def set_account_password(account_id, password):
    if not account_id:
        return
    env_key = f"PASSWORD_{account_id.upper()}"
    os.environ[env_key] = password
    
    # Ensure .env exists
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, "w") as f:
            f.write("")
            
    try:
        set_key(ENV_PATH, env_key, password)
    except Exception as e:
        print(f"Error writing to .env: {e}")

def set_env_variable(key, value):
    if not key or not value:
        return
    
    os.environ[key] = value
    
    # Ensure .env exists
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, "w") as f:
            f.write("")
            
    try:
        set_key(ENV_PATH, key, value)
    except Exception as e:
        print(f"Error writing to .env: {e}")
