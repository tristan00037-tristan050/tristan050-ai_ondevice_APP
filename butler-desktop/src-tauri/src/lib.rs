use std::{
    collections::HashMap,
    env,
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
    process::Command,
    sync::Mutex,
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::Manager;
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

mod build_identity;
#[cfg(test)]
#[path = "../distribution_flag.rs"]
mod distribution_flag_contract;
mod export;
mod runtime_trust;

const SIDECAR_ENV_CONFIG: &str = "sidecar-env.json";
const BUTLER_APP_DATA_DIR_ENV: &str = "BUTLER_APP_DATA_DIR";
const BUTLER_HOME_BOOTSTRAP_ENV: &str = "BUTLER_HOME_BOOTSTRAP_NEW_INSTALL";
const MODEL_TIER_NATIVE_TELEMETRY_ENV: &str = "BUTLER_MODEL_TIER_NATIVE_TELEMETRY_JSON";
const BUTLER_MODEL_PATH_ENV: &str = "BUTLER_MODEL_PATH";
const BOX3_V9_MODEL_PATH_ENV: &str = "BUTLER_BOX3_V9_Q4_MODEL_PATH";
const FREE_CHAT_MODEL_NAME: &str = "qwen3-4b-q4_k_m.gguf";
const BOX3_MODEL_NAME: &str = "butler-1.7b-v9-2-r2b-q4_k_m.gguf";
const HELPER4_SDK_ENV: &str = "BUTLER_HELPER4_GROUNDING_SDK_PATH";
const HELPER7_SDK_ENV: &str = "BUTLER_HELPER7_TABLE_FIGURE_SDK_PATH";
const HELPER8_SDK_ENV: &str = "BUTLER_HELPER8_COMPANY_STYLE_SDK_PATH";
const HELPER2_EMBEDDING_ENV: &str = "BUTLER_HELPER2_EMBEDDING_SDK_PATH";
const BOX3_HUMAN_APPROVAL_ENV: &str = "BUTLER_BOX3_HUMAN_APPROVAL_CONFIG_PATH";
const BOX3_HELPER_GUARD_ENV: &str = "BUTLER_BOX3_HELPER_COMPONENT_GUARD_PATH";
const BOX3_FIXED_EVAL_ENV: &str = "BUTLER_BOX3_FIXED_EVAL_REPORT_PATH";
const BOX3_EXTRA_ENV_KEYS: [&str; 7] = [
    HELPER4_SDK_ENV,
    HELPER7_SDK_ENV,
    HELPER8_SDK_ENV,
    HELPER2_EMBEDDING_ENV,
    BOX3_HUMAN_APPROVAL_ENV,
    BOX3_HELPER_GUARD_ENV,
    BOX3_FIXED_EVAL_ENV,
];

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
    for key in [
        BUTLER_MODEL_PATH_ENV,
        BOX3_V9_MODEL_PATH_ENV,
        HELPER4_SDK_ENV,
        HELPER7_SDK_ENV,
        HELPER8_SDK_ENV,
        HELPER2_EMBEDDING_ENV,
        BOX3_HUMAN_APPROVAL_ENV,
        BOX3_HELPER_GUARD_ENV,
        BOX3_FIXED_EVAL_ENV,
    ] {
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

fn push_if_resource_exists_and_unset(values: &mut Vec<(String, String)>, key: &str, path: PathBuf) {
    if path.exists() && !values.iter().any(|(k, _)| k == key) {
        values.push((key.to_string(), path.to_string_lossy().to_string()));
    }
}

fn push_free_chat_resource_env(app: &tauri::AppHandle, values: &mut Vec<(String, String)>) {
    let Ok(resource_dir) = app.path().resource_dir() else {
        append_sidecar_launch_log("free_chat_resource_dir=unavailable");
        return;
    };
    let chat_model = resource_dir.join("models").join(FREE_CHAT_MODEL_NAME);
    push_if_resource_exists_and_unset(values, BUTLER_MODEL_PATH_ENV, chat_model);
}

fn push_box3_resource_env(app: &tauri::AppHandle, values: &mut Vec<(String, String)>) {
    let Ok(resource_dir) = app.path().resource_dir() else {
        append_sidecar_launch_log("box3_resource_dir=unavailable");
        return;
    };
    let models_box3 = resource_dir.join("models").join("box3");
    let model_path = models_box3.join(BOX3_MODEL_NAME);
    let core_box3_sdk = resource_dir
        .join("butler_pc_core")
        .join("cards")
        .join("box3")
        .join("sdk");

    push_if_resource_exists_and_unset(values, BOX3_V9_MODEL_PATH_ENV, model_path.clone());
    push_if_resource_exists_and_unset(
        values,
        HELPER4_SDK_ENV,
        core_box3_sdk.join("helper4_grounding_sdk.py"),
    );
    push_if_resource_exists_and_unset(
        values,
        HELPER7_SDK_ENV,
        core_box3_sdk.join("helper7_table_figure_sdk.py"),
    );
    push_if_resource_exists_and_unset(
        values,
        HELPER8_SDK_ENV,
        core_box3_sdk.join("helper8_company_style_sdk.py"),
    );
    push_if_resource_exists_and_unset(
        values,
        HELPER2_EMBEDDING_ENV,
        models_box3.join("helper2_embedding"),
    );
    push_if_resource_exists_and_unset(
        values,
        BOX3_HUMAN_APPROVAL_ENV,
        models_box3.join("config").join("human_approval_v1.json"),
    );
    push_if_resource_exists_and_unset(
        values,
        BOX3_HELPER_GUARD_ENV,
        models_box3
            .join("config")
            .join("helper_component_guard_v1.json"),
    );
    push_if_resource_exists_and_unset(
        values,
        BOX3_FIXED_EVAL_ENV,
        models_box3.join("eval").join("fixed_eval_report_v1.json"),
    );
}

fn parse_positive_u64(text: &str) -> Option<u64> {
    let value = text.trim().parse::<u64>().ok()?;
    (value > 0).then_some(value)
}

fn parse_vm_stat_available_bytes(text: &str) -> Option<u64> {
    let page_size = text
        .lines()
        .next()
        .and_then(|line| line.split("page size of ").nth(1))
        .and_then(|tail| tail.split_whitespace().next())
        .and_then(parse_positive_u64)
        .unwrap_or(4096);
    let allowed = [
        "Pages free",
        "Pages inactive",
        "Pages speculative",
        "Pages purgeable",
    ];
    let mut pages = 0_u64;
    let mut found = false;
    for line in text.lines() {
        let Some((label, raw_value)) = line.split_once(':') else {
            continue;
        };
        if !allowed.contains(&label.trim()) {
            continue;
        }
        let digits: String = raw_value.chars().filter(char::is_ascii_digit).collect();
        if let Ok(value) = digits.parse::<u64>() {
            pages = pages.saturating_add(value);
            found = true;
        }
    }
    found.then(|| pages.saturating_mul(page_size))
}

fn command_stdout(program: &str, args: &[&str]) -> Option<String> {
    let output = Command::new(program).args(args).output().ok()?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8(output.stdout).ok()
}

fn collect_model_tier_native_telemetry_json() -> Option<String> {
    let total = command_stdout("/usr/sbin/sysctl", &["-n", "hw.memsize"])
        .and_then(|text| parse_positive_u64(&text));
    let available = command_stdout("/usr/bin/vm_stat", &[])
        .and_then(|text| parse_vm_stat_available_bytes(&text));
    let chip_family = command_stdout("/usr/sbin/sysctl", &["-n", "machdep.cpu.brand_string"])
        .map(|value| value.trim().chars().take(80).collect::<String>())
        .filter(|value| !value.is_empty());
    if total.is_none() && available.is_none() && chip_family.is_none() {
        return None;
    }
    let memory_pressure = match (total, available) {
        (Some(total), Some(available)) if available <= total => {
            let ratio = available as f64 / total as f64;
            if ratio < 0.10 {
                "CRITICAL"
            } else if ratio < 0.20 {
                "WARN"
            } else {
                "NORMAL"
            }
        }
        _ => "UNKNOWN",
    };
    serde_json::to_string(&serde_json::json!({
        "total_memory_bytes": total,
        "available_memory_bytes": available,
        "memory_pressure": memory_pressure,
        "thermal_state": "UNKNOWN",
        "chip_family": chip_family,
    }))
    .ok()
}

fn env_value<'a>(values: &'a [(String, String)], key: &str) -> Option<&'a str> {
    values
        .iter()
        .find(|(existing, _)| existing == key)
        .map(|(_, value)| value.as_str())
}

fn is_box3_model_path(value: &str) -> bool {
    let normalized = value.replace('\\', "/");
    normalized.contains(BOX3_MODEL_NAME) || normalized.contains("models/box3")
}

fn validate_model_path_invariants(values: &[(String, String)]) -> Result<(), String> {
    let main = env_value(values, BUTLER_MODEL_PATH_ENV);
    let box3 = env_value(values, BOX3_V9_MODEL_PATH_ENV);

    if let Some(main_value) = main {
        if is_box3_model_path(main_value) {
            append_sidecar_launch_log("model_path_conflict main_model_is_box3=true");
            return Err("MODEL_PATH_CONFLICT_MAIN_USES_BOX3".to_string());
        }
    }
    if let (Some(main_value), Some(box3_value)) = (main, box3) {
        if main_value == box3_value {
            append_sidecar_launch_log("model_path_conflict main_equals_box3=true");
            return Err("MODEL_PATH_CONFLICT_MAIN_EQUALS_BOX3".to_string());
        }
    }
    Ok(())
}

fn resolve_sidecar_env(app: &tauri::AppHandle) -> Result<Vec<(String, String)>, String> {
    let config = read_sidecar_env_config(app);
    let butler_model_path = env_value_or_config(&config, BUTLER_MODEL_PATH_ENV);
    let box3_v9_model_path = env_value_or_config(&config, BOX3_V9_MODEL_PATH_ENV);

    let mut values = Vec::new();
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|_| "APP_DATA_DIR_UNAVAILABLE".to_string())?;
    fs::create_dir_all(&app_data_dir).map_err(|_| "APP_DATA_DIR_CREATE_FAILED".to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&app_data_dir, fs::Permissions::from_mode(0o700))
            .map_err(|_| "APP_DATA_DIR_PERMISSION_FAILED".to_string())?;
    }
    values.push((
        BUTLER_APP_DATA_DIR_ENV.to_string(),
        app_data_dir.to_string_lossy().to_string(),
    ));
    let home_root = app_data_dir.join("home");
    let home_db = home_root.join("home.sqlite3");
    let has_existing_home = [
        home_db.clone(),
        PathBuf::from(format!("{}-wal", home_db.display())),
        PathBuf::from(format!("{}-shm", home_db.display())),
        PathBuf::from(format!("{}-journal", home_db.display())),
        home_root.join("workspace.id"),
        home_root.join("home.key"),
        home_root.join("backups"),
    ]
    .iter()
    .any(|path| path.exists());
    if !has_existing_home {
        values.push((BUTLER_HOME_BOOTSTRAP_ENV.to_string(), "1".to_string()));
    }
    if let Some(value) = butler_model_path {
        values.push((BUTLER_MODEL_PATH_ENV.to_string(), value));
    }
    if let Some(value) = box3_v9_model_path {
        values.push((BOX3_V9_MODEL_PATH_ENV.to_string(), value));
    }

    for key in BOX3_EXTRA_ENV_KEYS {
        if values.iter().any(|(existing, _)| existing == key) {
            continue;
        }
        if let Some(value) = env_value_or_config(&config, key) {
            values.push((key.to_string(), value));
        }
    }

    push_free_chat_resource_env(app, &mut values);
    push_box3_resource_env(app, &mut values);
    if let Some(telemetry) = collect_model_tier_native_telemetry_json() {
        values.push((MODEL_TIER_NATIVE_TELEMETRY_ENV.to_string(), telemetry));
    }
    validate_model_path_invariants(&values)?;

    append_sidecar_launch_log(&format!(
        "resolved_env butler_model_path={} box3_v9_model_path={}",
        values.iter().any(|(k, _)| k == BUTLER_MODEL_PATH_ENV),
        values.iter().any(|(k, _)| k == BOX3_V9_MODEL_PATH_ENV)
    ));
    Ok(values)
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
    let sidecar_env = resolve_sidecar_env(app)?;
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

#[cfg(test)]
mod tests {
    use super::*;

    fn env_pair(key: &str, value: &str) -> (String, String) {
        (key.to_string(), value.to_string())
    }

    #[test]
    fn model_path_rejects_box3_as_main_model() {
        let values = vec![env_pair(
            BUTLER_MODEL_PATH_ENV,
            "/Applications/Butler.app/Contents/Resources/models/box3/butler-1.7b-v9-2-r2b-q4_k_m.gguf",
        )];

        assert_eq!(
            validate_model_path_invariants(&values).unwrap_err(),
            "MODEL_PATH_CONFLICT_MAIN_USES_BOX3"
        );
    }

    #[test]
    fn model_path_rejects_identical_main_and_box3_paths() {
        let shared = "/tmp/models/shared.gguf";
        let values = vec![
            env_pair(BUTLER_MODEL_PATH_ENV, shared),
            env_pair(BOX3_V9_MODEL_PATH_ENV, shared),
        ];

        assert_eq!(
            validate_model_path_invariants(&values).unwrap_err(),
            "MODEL_PATH_CONFLICT_MAIN_EQUALS_BOX3"
        );
    }

    #[test]
    fn model_path_allows_separate_free_chat_and_box3_models() {
        let values = vec![
            env_pair(BUTLER_MODEL_PATH_ENV, "/tmp/models/qwen3-4b-q4_k_m.gguf"),
            env_pair(
                BOX3_V9_MODEL_PATH_ENV,
                "/tmp/models/box3/butler-1.7b-v9-2-r2b-q4_k_m.gguf",
            ),
        ];

        assert!(validate_model_path_invariants(&values).is_ok());
    }

    #[test]
    fn model_path_detects_box3_model_name_without_raw_path_dependency() {
        assert!(is_box3_model_path(BOX3_MODEL_NAME));
        assert!(!is_box3_model_path(FREE_CHAT_MODEL_NAME));
    }

    #[test]
    fn vm_stat_parser_sums_only_available_page_classes() {
        let sample = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n\
Pages free: 10.\n\
Pages active: 900.\n\
Pages inactive: 20.\n\
Pages speculative: 3.\n\
Pages purgeable: 2.\n";
        assert_eq!(parse_vm_stat_available_bytes(sample), Some(35 * 16_384));
    }

    #[test]
    fn vm_stat_parser_rejects_missing_available_measurements() {
        assert_eq!(parse_vm_stat_available_bytes("Pages active: 900.\n"), None);
        assert_eq!(parse_positive_u64("0"), None);
    }
}

#[tauri::command]
fn get_sidecar_capability_token(app: tauri::AppHandle) -> Result<String, String> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|_| "APP_DATA_DIR_UNAVAILABLE".to_string())?;
    let token_path = app_data_dir.join("ipc").join("sidecar.capability");
    let metadata = fs::symlink_metadata(&token_path)
        .map_err(|_| "CAPABILITY_TOKEN_UNAVAILABLE".to_string())?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("CAPABILITY_TOKEN_TYPE_INVALID".to_string());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o777 != 0o600 {
            return Err("CAPABILITY_TOKEN_MODE_INVALID".to_string());
        }
    }
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
            // Trust continuity is restored and validated before any sidecar
            // process can observe or serve product state.  Corruption blocks
            // startup; it never falls back to a fresh v1 bootstrap.
            let authority = runtime_trust::initialize_authority().map_err(std::io::Error::other)?;
            app.manage(authority);
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
        .invoke_handler(tauri::generate_handler![
            get_sidecar_capability_token,
            build_identity::get_native_build_context_digest,
            build_identity::get_native_release_distribution,
            runtime_trust::commands::verify_and_commit_trust_update,
            runtime_trust::commands::get_runtime_trust_status,
            export::save_export_file
        ])
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
