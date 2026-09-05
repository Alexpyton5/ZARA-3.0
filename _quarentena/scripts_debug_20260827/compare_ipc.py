frontend = set([
    'engine-change', 'engine-list', 'supercerebro-toggle', 'supercerebro-status',
    'send-message', 'interrupt', 'conversation-history-list', 'conversation-history-clear',
    'memory-galaxy-list', 'action-execute', 'action-list', 'system-metrics', 'system-info',
    'voice-start', 'voice-stop', 'voice-status', 'voice-mic-chunk', 'voice-mute',
    'config-get', 'config-set', 'lab-state', 'lab-send', 'lab-proposal-create',
    'lab-proposal-decide', 'reminder-create', 'reminder-list', 'reminder-cancel',
    'window-minimize', 'window-maximize', 'window-close'
])
backend_handler_map = set([
    'engine-change', 'engine-list', 'supercerebro-toggle', 'supercerebro-status',
    'send-message', 'interrupt', 'voice-mute', 'voice-mic-chunk', 'action-execute',
    'action-confirm', 'action-confirm-cancel', 'action-list', 'soul-get', 'self-status',
    'system-metrics', 'system-info', 'voice-start', 'voice-stop', 'voice-status',
    'config-get', 'config-set', 'lab-state', 'lab-send', 'lab-proposal-create',
    'lab-proposal-decide', 'reminder-create', 'reminder-list', 'reminder-cancel',
    'memory-user-add', 'memory-user-search', 'memory-user-list', 'memory-user-forget',
    'project-memory-get', 'project-memory-list', 'memory-galaxy-list',
    'conversation-history-list', 'conversation-history-clear'
])
print('Frontend methods not in backend handler map:', sorted(frontend - backend_handler_map))
print('Backend handler map keys not in frontend:', sorted(backend_handler_map - frontend))