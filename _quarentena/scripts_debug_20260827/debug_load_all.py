import core.actions
from core.capability_registry import load_capability, get_loaded_actions, get_fundamental_actions

# Load all fundamentals first
print("Fundamentals:", get_fundamental_actions())
print()

# Now load additional capabilities needed for testing
test_actions = [
    "os_brightness_absolute", "os_night_light_on", "os_night_light_off",
    "os_open", "window_focus_named", "window_switch_next",
    "youtube_pause", "youtube_resume", "youtube_next", "youtube_skip_ad",
    "youtube_open", "youtube_search", "youtube_play_by_name", "spotify_search",
    "browser_new_tab", "browser_back", "browser_forward", "browser_close_tab",
    "browser_scroll", "browser_read_page", "browser_search", "browser_open_url",
    "os_clipboard_read", "audio_status", "audio_mute", "audio_unmute",
    "vision_screenshot", "os_notify", "os_close_safe_app",
    "input_type_text", "input_hotkey", "web_search", "web_fetch",
    "files_list", "files_read", "files_search",
    "claude_ler", "claude_enviar", "codex_ler", "codex_enviar", "ponte_repassar",
    "aprendizado_resumo",
    "files_delete", "os_power", "system_kill", "terminal", "terminal_bg", "browser_eval",
]

for action in test_actions:
    load_capability(action)

print("Loaded actions:", sorted(get_loaded_actions()))
print("Total:", len(get_loaded_actions()))