import sys
sys.path.insert(0, '.')
from config.config_manager import get_skill_enabled, set_skill_enabled
print('hello_skill enabled:', get_skill_enabled('hello_skill'))
set_skill_enabled('hello_skill', False)
print('After disable:', get_skill_enabled('hello_skill'))