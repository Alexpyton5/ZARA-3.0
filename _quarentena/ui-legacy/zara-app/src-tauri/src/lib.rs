use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs,
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{ChildStdin, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{self, Sender},
        Arc, Mutex,
    },
    time::Duration,
};
use tauri::{AppHandle, Emitter, Manager, State};

/// Local bridge for the existing ZARA Python sidecar.
/// It deliberately preserves the same JSON-lines protocol used by Electron.
struct ZaraBridge {
    stdin: Mutex<Option<ChildStdin>>,
    pending: Arc<Mutex<HashMap<String, Sender<Result<Value, String>>>>>,
    started: AtomicBool,
    request_counter: AtomicU64,
}

impl Default for ZaraBridge {
    fn default() -> Self {
        Self {
            stdin: Mutex::new(None),
            pending: Arc::new(Mutex::new(HashMap::new())),
            started: AtomicBool::new(false),
            request_counter: AtomicU64::new(0),
        }
    }
}

impl ZaraBridge {
    fn workspace_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|path| path.parent())
            .expect("zara-app must be inside the ZARA workspace")
            .to_path_buf()
    }

    fn start_if_needed(&self, app: &AppHandle) -> Result<(), String> {
        if self.started.load(Ordering::SeqCst) {
            return Ok(());
        }

        let mut guard = self.stdin.lock().map_err(|_| "Ponte ZARA bloqueada".to_string())?;
        if guard.is_some() {
            return Ok(());
        }

        let workspace = Self::workspace_root();
        let python = workspace.join(".venv").join("Scripts").join("python.exe");
        let main = workspace.join("main.py");
        if !python.exists() || !main.exists() {
            return Err("O motor local da ZARA não foi encontrado neste computador.".to_string());
        }

        let mut child = Command::new(&python)
            .arg("-u")
            .arg(&main)
            .current_dir(&workspace)
            .env_remove("PYTHONPATH")
            .env("PYTHONUNBUFFERED", "1")
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("Não consegui iniciar o motor da ZARA: {error}"))?;

        let stdout = child.stdout.take().ok_or_else(|| "O motor da ZARA não disponibilizou resposta.".to_string())?;
        let stdin = child.stdin.take().ok_or_else(|| "O motor da ZARA não aceitou comandos.".to_string())?;
        let pending = Arc::clone(&self.pending);
        let app_handle = app.clone();

        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed == "SYS: Interface neural pronta" {
                    continue;
                }
                let Ok(message) = serde_json::from_str::<Value>(trimmed) else {
                    continue;
                };
                if let Some(request_id) = message.get("request_id").and_then(Value::as_str) {
                    if let Some(sender) = pending.lock().ok().and_then(|mut requests| requests.remove(request_id)) {
                        if let Some(error) = message.get("error").and_then(Value::as_str) {
                            let _ = sender.send(Err(error.to_string()));
                        } else {
                            let response = message.get("response").or_else(|| message.get("result")).cloned().unwrap_or(message);
                            let _ = sender.send(Ok(response));
                        }
                        continue;
                    }
                }
                if message.get("type").is_some() {
                    let _ = app_handle.emit("zara-event", message);
                }
            }
        });

        *guard = Some(stdin);
        self.started.store(true, Ordering::SeqCst);
        Ok(())
    }

    fn request(&self, app: &AppHandle, request_type: String, payload: Value) -> Result<Value, String> {
        self.start_if_needed(app)?;
        let request_id = format!("tauri-{}", self.request_counter.fetch_add(1, Ordering::SeqCst) + 1);
        let (sender, receiver) = mpsc::channel();
        self.pending
            .lock()
            .map_err(|_| "Ponte ZARA bloqueada".to_string())?
            .insert(request_id.clone(), sender);

        let wire = format!("{}\n", json!({ "type": request_type, "request_id": request_id, "payload": payload }));
        let write_result = self
            .stdin
            .lock()
            .map_err(|_| "Ponte ZARA bloqueada".to_string())?
            .as_mut()
            .ok_or_else(|| "O motor da ZARA não está disponível.".to_string())?
            .write_all(wire.as_bytes());
        if let Err(error) = write_result {
            self.pending.lock().ok().and_then(|mut requests| requests.remove(&request_id));
            return Err(format!("Não consegui enviar o pedido à ZARA: {error}"));
        }

        receiver
            .recv_timeout(Duration::from_secs(60))
            .map_err(|_| "A ZARA demorou demais para responder.".to_string())?
    }
}

#[tauri::command]
fn zara_request(
    app: AppHandle,
    bridge: State<'_, ZaraBridge>,
    request_type: String,
    payload: Value,
) -> Result<Value, String> {
    bridge.request(&app, request_type, payload)
}

#[tauri::command]
fn zara_bridge_status(bridge: State<'_, ZaraBridge>) -> Value {
    json!({ "connected": bridge.started.load(Ordering::SeqCst) })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(ZaraBridge::default())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![zara_request, zara_bridge_status])
        .run(tauri::generate_context!())
        .expect("error while running ZARA");
}
