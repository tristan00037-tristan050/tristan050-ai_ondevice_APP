use std::{
    collections::HashMap,
    env,
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::Mutex,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::Manager;
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

mod build_identity;
// build script 전용 모듈이라 라이브러리 빌드에는 들어가지 않는다. 그대로 두면 게이트 판정
// 규칙이 `cargo test` 에서 한 번도 실행되지 않으므로, 시험 빌드에만 끌어와 회귀 시험이
// CI 에서 실제로 돌게 한다.
#[cfg(test)]
#[path = "../build_gate.rs"]
mod build_gate_contract;
#[cfg(test)]
#[path = "../distribution_flag.rs"]
mod distribution_flag_contract;
mod export;
mod helper1_trust;
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

#[derive(Clone, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Box5AuthorizedRequest {
    action: String,
    route_selector: String,
    resource_id: String,
    parent_resource_id: Option<String>,
    body_json: Option<String>,
    idempotency_key: Option<String>,
    if_match_version: Option<u64>,
}

#[derive(Debug)]
struct CompiledBox5Route {
    action: String,
    resource: String,
    path: String,
    body: Vec<u8>,
    idempotency_key: Option<String>,
    if_match_version: Option<u64>,
}

#[derive(serde::Serialize)]
struct Box5AuthorityRequest<'a> {
    schema_version: &'static str,
    request_nonce: &'a str,
    action: &'a str,
    resource: &'a str,
    body_sha256: String,
    session_binding_sha256: String,
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Box5AuthorityResponse {
    schema_version: String,
    request_nonce: String,
    assertion: String,
    expires_at: u64,
}

#[derive(serde::Serialize)]
struct Box5RendererResponse {
    status: u16,
    content_type: String,
    body: String,
}

struct Box5Secret(String);

impl std::fmt::Debug for Box5Secret {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("[REDACTED]")
    }
}

impl Drop for Box5Secret {
    fn drop(&mut self) {
        // SAFETY: bytes are only overwritten in place and the String length and
        // UTF-8 validity (zero bytes are valid UTF-8) remain unchanged.
        unsafe { self.0.as_bytes_mut().fill(0) }
    }
}

fn box5_safe_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

fn compile_box5_route(request: &Box5AuthorizedRequest) -> Result<CompiledBox5Route, String> {
    if !box5_safe_identifier(&request.resource_id)
        || request
            .parent_resource_id
            .as_deref()
            .is_some_and(|value| !box5_safe_identifier(value))
        || request.idempotency_key.as_deref().is_some_and(|value| {
            value.len() < 8
                || value.len() > 128
                || !value.bytes().all(|byte| {
                    byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-')
                })
        })
        || request.if_match_version == Some(0)
    {
        return Err("BOX5_INTENT_INVALID".to_string());
    }
    let (resource_type, path, body_required, mutation_headers) =
        match (request.action.as_str(), request.route_selector.as_str()) {
            ("ASSIGNMENT_CREATE", "ACTION_NONCE_THIS_ONLY") => (
                "ACCOUNTING_TRANSACTION",
                format!(
                    "/v1/accounting/unaccounted/{}/action-nonce?scope=THIS_ONLY",
                    request.resource_id
                ),
                false,
                false,
            ),
            ("RULE_FUTURE_CREATE", "ACTION_NONCE_FUTURE") => (
                "ACCOUNTING_TRANSACTION",
                format!(
                    "/v1/accounting/unaccounted/{}/action-nonce?scope=SAME_VENDOR_FUTURE",
                    request.resource_id
                ),
                false,
                false,
            ),
            ("ASSIGNMENT_CREATE" | "RULE_FUTURE_CREATE", "ASSIGNMENT_MUTATION") => (
                "ACCOUNTING_TRANSACTION",
                format!("/v1/accounting/unaccounted/{}/assign", request.resource_id),
                true,
                true,
            ),
            ("RULE_DEACTIVATE", "RULE_DEACTIVATE") => (
                "LEARNED_RULE",
                format!(
                    "/v1/accounting/learned-rules/{}/deactivate",
                    request.resource_id
                ),
                false,
                true,
            ),
            ("RULE_APPLICATION_REVERT", "RULE_APPLICATION_REVERT") => (
                "ACCOUNTING_TRANSACTION",
                format!(
                    "/v1/accounting/review/transactions/{}/rule-application/revert",
                    request.resource_id
                ),
                false,
                true,
            ),
            ("QUARANTINE_ROW_RECOMPILE", "QUARANTINE_ROW_RECOMPILE") => {
                let batch = request
                    .parent_resource_id
                    .as_deref()
                    .ok_or_else(|| "BOX5_RESOURCE_BINDING_INVALID".to_string())?;
                (
                    "QUARANTINED_ROW",
                    format!(
                        "/v1/accounting/review/batches/{}/quarantine/{}/recompile",
                        batch, request.resource_id
                    ),
                    true,
                    true,
                )
            }
            ("CONFLICT_RESOLVE", "CONFLICT_RESOLVE") => (
                "RULE_CONFLICT",
                format!(
                    "/v1/accounting/rule-conflicts/{}/resolve",
                    request.resource_id
                ),
                true,
                true,
            ),
            _ => return Err("BOX5_RESOURCE_BINDING_INVALID".to_string()),
        };
    if mutation_headers != (request.idempotency_key.is_some() && request.if_match_version.is_some())
        || (!mutation_headers
            && (request.idempotency_key.is_some() || request.if_match_version.is_some()))
        || body_required != request.body_json.is_some()
    {
        return Err("BOX5_INTENT_INVALID".to_string());
    }
    let body = request
        .body_json
        .as_deref()
        .map(str::as_bytes)
        .unwrap_or_default();
    if body.len() > 1_048_576 {
        return Err("BOX5_BODY_SIZE_INVALID".to_string());
    }
    if !body.is_empty() {
        let parsed: serde_json::Value =
            serde_json::from_slice(body).map_err(|_| "BOX5_BODY_JSON_INVALID".to_string())?;
        if !parsed.is_object() {
            return Err("BOX5_BODY_JSON_INVALID".to_string());
        }
    }
    Ok(CompiledBox5Route {
        action: request.action.clone(),
        resource: format!("{}:{}", resource_type, request.resource_id),
        path,
        body: body.to_vec(),
        idempotency_key: request.idempotency_key.clone(),
        if_match_version: request.if_match_version,
    })
}

fn box5_random_nonce() -> Result<String, String> {
    use base64::Engine;
    use ring::rand::{SecureRandom, SystemRandom};

    let mut bytes = [0_u8; 24];
    SystemRandom::new()
        .fill(&mut bytes)
        .map_err(|_| "BLOCK_NATIVE_RANDOM_UNAVAILABLE".to_string())?;
    Ok(base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(bytes))
}

fn hex_sha256(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};

    format!("{:x}", Sha256::digest(bytes))
}

fn box5_verify_helper(helper: &Path) -> Result<(), String> {
    let metadata =
        fs::symlink_metadata(helper).map_err(|_| "BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string())?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o111 == 0 {
            return Err("BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string());
        }
    }
    #[cfg(target_os = "macos")]
    {
        let verified = Command::new("/usr/bin/codesign")
            .args(["--verify", "--strict", "--verbose=2"])
            .arg(helper)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|_| "BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string())?;
        if !verified.success() {
            return Err("BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string());
        }
        let identity = Command::new("/usr/bin/codesign")
            .args(["-d", "--verbose=4"])
            .arg(helper)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .output()
            .map_err(|_| "BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string())?;
        let details = String::from_utf8(identity.stderr)
            .map_err(|_| "BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string())?;
        if !identity.status.success()
            || !details
                .lines()
                .any(|line| line == "Identifier=com.butler.box5.user-authority.v2")
        {
            return Err("BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string());
        }
        Ok(())
    }
    #[cfg(not(target_os = "macos"))]
    {
        Err("BLOCK_MACOS_NATIVE_AUTHORITY_REQUIRED".to_string())
    }
}

fn box5_issue_assertion(
    helper: &Path,
    route: &CompiledBox5Route,
    session_binding_sha256: &str,
) -> Result<Box5Secret, String> {
    box5_verify_helper(helper)?;
    let request_nonce = box5_random_nonce()?;
    let request = Box5AuthorityRequest {
        schema_version: "2.0",
        request_nonce: &request_nonce,
        action: &route.action,
        resource: &route.resource,
        body_sha256: hex_sha256(&route.body),
        session_binding_sha256: session_binding_sha256.to_string(),
    };
    let mut wire =
        serde_json::to_vec(&request).map_err(|_| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?;
    wire.push(b'\n');
    let mut child = Command::new(helper)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string())?;
    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?;
    stdin
        .write_all(&wire)
        .map_err(|_| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?;
    wire.fill(0);
    drop(stdin);
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?;
    let output_reader = std::thread::spawn(move || {
        let mut output = Vec::new();
        stdout.take(16_385).read_to_end(&mut output).map(|_| output)
    });
    // The helper may present macOS device-owner authentication. Keep this
    // bounded, but allow a human a realistic approval window.
    let deadline = Instant::now() + Duration::from_secs(30);
    let status = loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|_| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?
        {
            break status;
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err("BLOCK_NATIVE_AUTHORITY_TIMEOUT".to_string());
        }
        std::thread::sleep(Duration::from_millis(10));
    };
    let output = output_reader
        .join()
        .map_err(|_| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?
        .map_err(|_| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?;
    if !status.success() || output.is_empty() || output.len() > 16_384 {
        return Err("BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string());
    }
    let text =
        std::str::from_utf8(&output).map_err(|_| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?;
    if text.trim_end_matches('\n').contains('\n') {
        return Err("BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string());
    }
    let response: Box5AuthorityResponse = serde_json::from_str(text.trim_end())
        .map_err(|_| "BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string())?;
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "BLOCK_NATIVE_CLOCK_INVALID".to_string())?
        .as_secs();
    if response.schema_version != "2.0"
        || response.request_nonce != request_nonce
        || response.expires_at <= now
        || response.expires_at > now + 300
        || response.assertion.len() > 16_384
        || response.assertion.split('.').count() != 3
        || response
            .assertion
            .bytes()
            .any(|byte| !byte.is_ascii() || byte.is_ascii_whitespace())
    {
        return Err("BLOCK_NATIVE_AUTHORITY_PROTOCOL".to_string());
    }
    Ok(Box5Secret(response.assertion))
}

fn box5_read_capability_token(path: &Path) -> Result<Box5Secret, String> {
    let metadata =
        fs::symlink_metadata(path).map_err(|_| "CAPABILITY_TOKEN_UNAVAILABLE".to_string())?;
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
    let token = fs::read_to_string(path)
        .map_err(|_| "CAPABILITY_TOKEN_UNAVAILABLE".to_string())?
        .trim()
        .to_string();
    if token.is_empty()
        || token.len() > 256
        || token
            .bytes()
            .any(|byte| !byte.is_ascii() || byte.is_ascii_whitespace())
    {
        return Err("CAPABILITY_TOKEN_INVALID".to_string());
    }
    Ok(Box5Secret(token))
}

fn box5_send_loopback(
    route: &CompiledBox5Route,
    token: &Box5Secret,
    assertion: &Box5Secret,
) -> Result<Box5RendererResponse, String> {
    let address: SocketAddr = "127.0.0.1:8765"
        .parse()
        .map_err(|_| "BLOCK_LOOPBACK_TARGET_INVALID".to_string())?;
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_secs(2))
        .map_err(|_| "BLOCK_LOOPBACK_UNAVAILABLE".to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .map_err(|_| "BLOCK_LOOPBACK_UNAVAILABLE".to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|_| "BLOCK_LOOPBACK_UNAVAILABLE".to_string())?;
    let mut request = format!(
        "POST {} HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nConnection: close\r\nAccept: application/json, application/problem+json\r\nAuthorization: Bearer {}\r\nButler-User-Authorization: {}\r\nContent-Length: {}\r\n",
        route.path,
        token.0,
        assertion.0,
        route.body.len()
    );
    if !route.body.is_empty() {
        request.push_str("Content-Type: application/json\r\n");
    }
    if let Some(key) = &route.idempotency_key {
        request.push_str(&format!("Idempotency-Key: {}\r\n", key));
    }
    if let Some(version) = route.if_match_version {
        request.push_str(&format!("If-Match: W/\"{}\"\r\n", version));
    }
    request.push_str("\r\n");
    stream
        .write_all(request.as_bytes())
        .and_then(|_| stream.write_all(&route.body))
        .map_err(|_| "BLOCK_LOOPBACK_UNAVAILABLE".to_string())?;
    unsafe { request.as_bytes_mut().fill(0) }
    let mut response = Vec::new();
    stream
        .take(1_065_000)
        .read_to_end(&mut response)
        .map_err(|_| "BLOCK_LOOPBACK_RESPONSE_INVALID".to_string())?;
    if response.len() >= 1_065_000 {
        return Err("BLOCK_LOOPBACK_RESPONSE_TOO_LARGE".to_string());
    }
    let separator = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "BLOCK_LOOPBACK_RESPONSE_INVALID".to_string())?;
    let header = std::str::from_utf8(&response[..separator])
        .map_err(|_| "BLOCK_LOOPBACK_RESPONSE_INVALID".to_string())?;
    let mut lines = header.split("\r\n");
    let status_line = lines
        .next()
        .ok_or_else(|| "BLOCK_LOOPBACK_RESPONSE_INVALID".to_string())?;
    let mut status_parts = status_line.split_ascii_whitespace();
    if status_parts.next() != Some("HTTP/1.1") {
        return Err("BLOCK_LOOPBACK_RESPONSE_INVALID".to_string());
    }
    let status: u16 = status_parts
        .next()
        .and_then(|value| value.parse().ok())
        .filter(|value| (100..=599).contains(value))
        .ok_or_else(|| "BLOCK_LOOPBACK_RESPONSE_INVALID".to_string())?;
    if (300..400).contains(&status) {
        return Err("BLOCK_LOOPBACK_REDIRECT_FORBIDDEN".to_string());
    }
    let mut content_type: Option<String> = None;
    let mut content_length: Option<usize> = None;
    for line in lines {
        let (name, value) = line
            .split_once(':')
            .ok_or_else(|| "BLOCK_LOOPBACK_RESPONSE_INVALID".to_string())?;
        let value = value.trim();
        if name.eq_ignore_ascii_case("content-type") {
            if content_type.is_some() {
                return Err("BLOCK_LOOPBACK_RESPONSE_INVALID".to_string());
            }
            content_type = Some(value.to_ascii_lowercase());
        } else if name.eq_ignore_ascii_case("content-length") {
            if content_length.is_some() {
                return Err("BLOCK_LOOPBACK_RESPONSE_INVALID".to_string());
            }
            content_length = Some(
                value
                    .parse()
                    .map_err(|_| "BLOCK_LOOPBACK_RESPONSE_INVALID".to_string())?,
            );
        } else if name.eq_ignore_ascii_case("transfer-encoding") {
            return Err("BLOCK_LOOPBACK_TRANSFER_ENCODING_FORBIDDEN".to_string());
        }
    }
    let content_type = content_type
        .filter(|value| value == "application/json" || value == "application/problem+json")
        .ok_or_else(|| "BLOCK_LOOPBACK_CONTENT_TYPE_INVALID".to_string())?;
    let body = &response[separator + 4..];
    if body.len() > 1_048_576 || content_length != Some(body.len()) {
        return Err("BLOCK_LOOPBACK_RESPONSE_INVALID".to_string());
    }
    let body = String::from_utf8(body.to_vec())
        .map_err(|_| "BLOCK_LOOPBACK_RESPONSE_INVALID".to_string())?;
    Ok(Box5RendererResponse {
        status,
        content_type,
        body,
    })
}

fn execute_box5_authorized_request(
    token_path: PathBuf,
    helper_path: PathBuf,
    request: Box5AuthorizedRequest,
) -> Result<Box5RendererResponse, String> {
    let route = compile_box5_route(&request)?;
    let token = box5_read_capability_token(&token_path)?;
    let session_binding_sha256 = hex_sha256(token.0.as_bytes());
    let assertion = box5_issue_assertion(&helper_path, &route, &session_binding_sha256)?;
    box5_send_loopback(&route, &token, &assertion)
}

#[tauri::command]
async fn box5_authorized_request(
    app: tauri::AppHandle,
    request: Box5AuthorizedRequest,
) -> Result<Box5RendererResponse, String> {
    let app_data = app
        .path()
        .app_data_dir()
        .map_err(|_| "APP_DATA_DIR_UNAVAILABLE".to_string())?;
    let resources = app
        .path()
        .resource_dir()
        .map_err(|_| "BLOCK_HUMAN_AUTHORITY_UNRESOLVED".to_string())?;
    let token_path = app_data.join("ipc").join("sidecar.capability");
    let helper_path = resources.join("box5").join("Box5UserAuthority");
    tauri::async_runtime::spawn_blocking(move || {
        execute_box5_authorized_request(token_path, helper_path, request)
    })
    .await
    .map_err(|_| "BLOCK_NATIVE_AUTHORITY_RUNTIME".to_string())?
}

#[cfg(test)]
mod box5_authorization_tests {
    use super::{compile_box5_route, Box5AuthorizedRequest};

    fn request() -> Box5AuthorizedRequest {
        Box5AuthorizedRequest {
            action: "ASSIGNMENT_CREATE".to_string(),
            route_selector: "ASSIGNMENT_MUTATION".to_string(),
            resource_id: "txn_1234567890abcdef".to_string(),
            parent_resource_id: None,
            body_json: Some("{}".to_string()),
            idempotency_key: Some("request-12345678".to_string()),
            if_match_version: Some(1),
        }
    }

    #[test]
    fn native_intent_compiler_owns_exact_route_and_resource() {
        let compiled = compile_box5_route(&request()).unwrap();
        assert_eq!(
            compiled.path,
            "/v1/accounting/unaccounted/txn_1234567890abcdef/assign"
        );
        assert_eq!(
            compiled.resource,
            "ACCOUNTING_TRANSACTION:txn_1234567890abcdef"
        );
    }

    #[test]
    fn action_and_route_selector_mismatch_is_rejected() {
        let mut candidate = request();
        candidate.action = "RULE_DEACTIVATE".to_string();
        assert_eq!(
            compile_box5_route(&candidate).unwrap_err(),
            "BOX5_RESOURCE_BINDING_INVALID"
        );
    }

    #[test]
    fn mutation_headers_are_typed_and_required() {
        let mut candidate = request();
        candidate.idempotency_key = None;
        assert_eq!(
            compile_box5_route(&candidate).unwrap_err(),
            "BOX5_INTENT_INVALID"
        );
        let mut candidate = request();
        candidate.if_match_version = Some(0);
        assert_eq!(
            compile_box5_route(&candidate).unwrap_err(),
            "BOX5_INTENT_INVALID"
        );
    }
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
