# Platform Adapters

## Windows — prioridade

- filesystem;
- processos;
- apps;
- janelas;
- clipboard;
- notificações;
- áudio;
- rede;
- energia;
- UI Automation;
- PowerShell;
- APIs Windows;
- diagnóstico.

## macOS

- Accessibility API;
- AppleScript;
- Shortcuts;
- filesystem;
- processos;
- notificações.

## Linux

- DBus;
- AT-SPI;
- shell;
- filesystem;
- processos;
- desktop APIs.

## iOS

Usar apenas capacidades permitidas:
- App Intents;
- Shortcuts;
- Share Extensions;
- APIs oficiais.

Não prometer controle irrestrito.

## Contrato comum

```text
PlatformAdapter
├── files
├── apps
├── windows
├── system
├── clipboard
├── notifications
├── audio
├── network
└── capabilities
```
