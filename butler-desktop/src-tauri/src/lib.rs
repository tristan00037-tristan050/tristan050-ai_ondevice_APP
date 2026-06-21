use std::{
    collections::HashMap,
    env,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::Manager;
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const SIDECAR_ENV_CONFIG: &str = "sidecar-env.json";
const BUTLER_MODEL_PATH_ENV: &str = "BUTLER_MODEL_PATH";
const BOX3_V9_MODEL_PATH_ENV: &str = "BUTLER_BOX3_V9_Q4_MODEL_PATH";

struct SidecarState {
    child: Mutex<Option<CommandChild>>,
}

fn sidecar_launch_log_path() -> PathBuf {
    let base = env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(env::temp_dir);
    base.join("Library")
        .join("Logs")
        .join("Butler")
        .join("sidecar-launch.log")
}

fn append_sidecar_launch_log(message: &str) {
    let path = sidecar_launch_log_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&path) {
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let _ = writeln!(file, "{} {}", ts, message);
    }
}

fn read_sidecar_env_config(app: &tauri::AppHandle) -> HashMap<String, String> {
    let mut values = HashMap::new();
    let Ok(config_dir) = app.path().app_config_dir() else {
        append_sidecar_launch_log("config_dir=unavailable");
        return values;
    };
    let config_path = config_dir.join(SIDECAR_ENV_CONFIG);
    let Ok(text) = fs::read_to_string(&config_path) else {
        append_sidecar_launch_log("sidecar_env_config=missing");
        return values;
    };
    let Ok(json) = serde_json::from_str::<serde_json::Value>(&text) else {
        append_sidecar_launch_log("sidecar_env_config=invalid_json");
        return values;
    };
    let Some(object) = json.as_object() else {
        append_sidecar_launch_log("sidecar_env_config=not_object");
        return values;
    };
    for key in [BUTLER_MODEL_PATH_ENV, BOX3_V9_MODEL_PATH_ENV] {
        if let Some(value) = object.get(key).and_then(|v| v.as_str()) {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                values.insert(key.to_string(), trimmed.to_string());
            }
        }
    }
    values
}

fn env_value_or_config(config: &HashMap<String, String>, key: &str) -> Option<String> {
    env::var(key)
        .ok()
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty())
        .or_else(|| config.get(key).cloned())
}

fn resolve_sidecar_env(app: &tauri::AppHandle) -> Vec<(String, String)> {
    let config = read_sidecar_env_config(app);
    let mut butler_model_path = env_value_or_config(&config, BUTLER_MODEL_PATH_ENV);
    let mut box3_v9_model_path = env_value_or_config(&config, BOX3_V9_MODEL_PATH_ENV);

    if butler_model_path.is_none() {
        butler_model_path = box3_v9_model_path.clone();
    }
    if box3_v9_model_path.is_none() {
        box3_v9_model_path = butler_model_path.clone();
    }

    let mut values = Vec::new();
    if let Some(value) = butler_model_path {
        values.push((BUTLER_MODEL_PATH_ENV.to_string(), value));
    }
    if let Some(value) = box3_v9_model_path {
        values.push((BOX3_V9_MODEL_PATH_ENV.to_string(), value));
    }
    append_sidecar_launch_log(&format!(
        "resolved_env butler_model_path={} box3_v9_model_path={}",
        values.iter().any(|(k, _)| k == BUTLER_MODEL_PATH_ENV),
        values.iter().any(|(k, _)| k == BOX3_V9_MODEL_PATH_ENV)
    ));
    values
}

fn stop_sidecar(app: &tauri::AppHandle, reason: &str) {
    let child_opt = {
        let state = app.state::<SidecarState>();
        let x = state.child.lock().unwrap().take();
        x
    };
    if let Some(child) = child_opt {
        let _ = child.kill();
        append_sidecar_launch_log(&format!("stop_sidecar reason={}", reason));
        println!("[main] sidecar 종료 완료 ({})", reason);
    }
}

async fn spawn_sidecar(app: &tauri::AppHandle) -> Result<Option<CommandChild>, String> {
    // dev 외부 sidecar 모드: 앱이 자체 sidecar를 띄우지 않고 외부(수동) sidecar를 사용
    if env::var("BUTLER_SIDECAR_EXTERNAL").ok().as_deref() == Some("1") {
        append_sidecar_launch_log("spawn_sidecar=external_skip");
        return Ok(None);
    }
    append_sidecar_launch_log("spawn_sidecar=start");
    let sidecar_env = resolve_sidecar_env(app);
    let (mut rx, child) = app
        .shell()
        .sidecar("butler-sidecar")
        .map_err(|e| {
            let message = format!("sidecar 명령 생성 실패: {}", e);
            append_sidecar_launch_log(&message);
            message
        })?
        .args(["--port", "8765", "--host", "127.0.0.1"])
        .envs(sidecar_env)
        .spawn()
        .map_err(|e| {
            let message = format!("sidecar 실행 실패: {}", e);
            append_sidecar_launch_log(&message);
            message
        })?;
    append_sidecar_launch_log("spawn_sidecar=ok");

    // 로그 수신 — 별도 task로 분리 (spawn_sidecar를 블록하지 않음)
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    if let Ok(s) = String::from_utf8(line) {
                        append_sidecar_launch_log(&format!("stdout {}", s.trim_end()));
                        print!("[sidecar] {}", s);
                    }
                }
                CommandEvent::Stderr(line) => {
                    if let Ok(s) = String::from_utf8(line) {
                        append_sidecar_launch_log(&format!("stderr {}", s.trim_end()));
                        eprint!("[sidecar-err] {}", s);
                    }
                }
                CommandEvent::Error(err) => {
                    append_sidecar_launch_log(&format!("event_error {}", err));
                    eprintln!("[sidecar-error] {}", err);
                }
                CommandEvent::Terminated(payload) => {
                    append_sidecar_launch_log(&format!("terminated code={:?}", payload.code));
                    eprintln!("[sidecar] 종료: code={:?}", payload.code);
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(Some(child))
}

#[tauri::command]
fn get_sidecar_capability_token() -> Result<String, String> {
    let home = env::var("HOME").map_err(|_| "HOME_UNAVAILABLE".to_string())?;
    let token_path = Path::new(&home).join(".butler").join("sidecar_token");
    let token =
        fs::read_to_string(&token_path).map_err(|_| "CAPABILITY_TOKEN_UNAVAILABLE".to_string())?;
    let trimmed = token.trim().to_string();
    if trimmed.is_empty() {
        return Err("CAPABILITY_TOKEN_EMPTY".to_string());
    }
    Ok(trimmed)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(SidecarState {
            child: Mutex::new(None),
        })
        .setup(|app| {
            let app_handle = app.handle().clone();
            tauri::async_runtime::block_on(async move {
                match spawn_sidecar(&app_handle).await {
                    Ok(Some(child)) => {
                        // 명시적 블록으로 MutexGuard를 state보다 먼저 drop
                        {
                            let state = app_handle.state::<SidecarState>();
                            *state.child.lock().unwrap() = Some(child);
                        }
                        println!("[main] sidecar 시작 완료 (포트 8765)");
                    }
                    Ok(None) => {
                        append_sidecar_launch_log("setup_spawn_sidecar=external");
                        println!("[main] 외부 sidecar 사용 모드 (BUTLER_SIDECAR_EXTERNAL=1)");
                    }
                    Err(e) => {
                        append_sidecar_launch_log(&format!("setup_spawn_sidecar=failed {}", e));
                        eprintln!("[main] sidecar 시작 실패: {}", e);
                        eprintln!("[main] Python3 및 의존성 설치를 확인하세요.");
                        eprintln!("[main] 가이드: docs/beta/getting_started_v1.md 1.4-1.5절");
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                stop_sidecar(window.app_handle(), "window_close_requested");
            }
            if matches!(event, tauri::WindowEvent::Destroyed) {
                stop_sidecar(window.app_handle(), "window_destroyed");
            }
        })
        .invoke_handler(tauri::generate_handler![get_sidecar_capability_token])
        .build(tauri::generate_context!())
        .expect("Tauri 앱 빌드 실패")
        .run(|app_handle, event| match event {
            tauri::RunEvent::ExitRequested { .. } => {
                stop_sidecar(app_handle, "app_exit_requested");
            }
            tauri::RunEvent::Exit => {
                stop_sidecar(app_handle, "app_exit");
            }
            _ => {}
        });
}
