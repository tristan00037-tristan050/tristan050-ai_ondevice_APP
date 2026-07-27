use std::{
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
mod runtime_trust;

const ASSET_BOOTSTRAP_STDIN_ENV: &str = "BUTLER_ASSET_BOOTSTRAP_STDIN";
const BUTLER_APP_DATA_DIR_ENV: &str = "BUTLER_APP_DATA_DIR";
const BUTLER_HOME_BOOTSTRAP_ENV: &str = "BUTLER_HOME_BOOTSTRAP_NEW_INSTALL";
const MODEL_TIER_NATIVE_TELEMETRY_ENV: &str = "BUTLER_MODEL_TIER_NATIVE_TELEMETRY_JSON";

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

fn resolve_sidecar_env(app: &tauri::AppHandle) -> Result<Vec<(String, String)>, String> {
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
    if let Some(telemetry) = collect_model_tier_native_telemetry_json() {
        values.push((MODEL_TIER_NATIVE_TELEMETRY_ENV.to_string(), telemetry));
    }
    append_sidecar_launch_log(&format!(
        "resolved_env asset_bootstrap={} legacy_model_paths=0",
        true
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
    let mut sidecar_env = resolve_sidecar_env(app)?;
    sidecar_env.push((ASSET_BOOTSTRAP_STDIN_ENV.to_string(), "1".to_string()));
    let bootstrap = asset_bootstrap_frame(app)?;
    let (mut rx, mut child) = app
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
    if let Err(error) = child.write(&bootstrap) {
        let _ = child.kill();
        append_sidecar_launch_log("asset_bootstrap=failed");
        return Err(format!("asset bootstrap write failed: {}", error));
    }
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

fn asset_bootstrap_frame(app: &tauri::AppHandle) -> Result<Vec<u8>, String> {
    let resource_root = app
        .path()
        .resource_dir()
        .map_err(|_| "asset resource root unavailable".to_string())?;
    let app_data_root = app
        .path()
        .app_data_dir()
        .map_err(|_| "asset app data root unavailable".to_string())?;
    fs::create_dir_all(&app_data_root)
        .map_err(|_| "asset app data root unavailable".to_string())?;

    let commit = option_env!("BUTLER_SOURCE_COMMIT_OID")
        .filter(|value| !value.is_empty())
        .unwrap_or("0000000000000000000000000000000000000000");
    let tree = option_env!("BUTLER_SOURCE_TREE_OID")
        .filter(|value| !value.is_empty())
        .unwrap_or("0000000000000000000000000000000000000000");
    let profile = if option_env!("BUTLER_RELEASE_DISTRIBUTION") == Some("1") {
        "production"
    } else {
        "development"
    };
    let oid_valid = |value: &str| {
        matches!(value.len(), 40 | 64)
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    };
    if !oid_valid(commit)
        || !oid_valid(tree)
        || (profile == "production"
            && (commit.bytes().all(|byte| byte == b'0') || tree.bytes().all(|byte| byte == b'0')))
    {
        return Err("asset native build identity invalid".to_string());
    }
    let manifest_set =
        match fs::read_to_string(resource_root.join("assets/ASSET_BUILD_CONTEXT.json")) {
            Ok(raw) => {
                let value = serde_json::from_str::<serde_json::Value>(&raw)
                    .map_err(|_| "asset build context invalid".to_string())?;
                let object = value
                    .as_object()
                    .ok_or_else(|| "asset build context invalid".to_string())?;
                let expected_keys = [
                    "schema_version",
                    "build_id",
                    "source_commit",
                    "source_tree",
                    "release_profile",
                    "manifest_set_sha256",
                    "toolchain",
                ];
                if object.len() != expected_keys.len()
                    || expected_keys.iter().any(|key| !object.contains_key(*key))
                    || value.get("schema_version").and_then(|item| item.as_u64()) != Some(1)
                    || value.get("build_id").and_then(|item| item.as_str()) != Some(commit)
                    || value.get("source_commit").and_then(|item| item.as_str()) != Some(commit)
                    || value.get("source_tree").and_then(|item| item.as_str()) != Some(tree)
                    || value.get("release_profile").and_then(|item| item.as_str()) != Some(profile)
                    || value
                        .get("toolchain")
                        .and_then(|item| item.as_object())
                        .map(|item| item.is_empty())
                        != Some(false)
                {
                    return Err("asset build context identity mismatch".to_string());
                }
                Some(
                    value
                        .get("manifest_set_sha256")
                        .and_then(|item| item.as_str())
                        .filter(|item| {
                            item.len() == 64
                                && item.bytes().all(|byte| {
                                    byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
                                })
                        })
                        .ok_or_else(|| "asset manifest set invalid".to_string())?
                        .to_string(),
                )
            }
            Err(error)
                if error.kind() == std::io::ErrorKind::NotFound && profile != "production" =>
            {
                None
            }
            Err(_) => return Err("asset build context unavailable".to_string()),
        };
    let payload = serde_json::json!({
        "schema_version": 1,
        "resource_root": resource_root,
        "app_data_root": app_data_root,
        "release_profile": profile,
        "build_id": commit,
        "source_commit": commit,
        "source_tree": tree,
        "manifest_set_sha256": manifest_set,
    });
    let payload =
        serde_json::to_vec(&payload).map_err(|_| "asset bootstrap encode failed".to_string())?;
    let payload_size =
        u32::try_from(payload.len()).map_err(|_| "asset bootstrap encode failed".to_string())?;
    let mut frame = Vec::with_capacity(4 + payload.len());
    frame.extend_from_slice(&payload_size.to_be_bytes());
    frame.extend_from_slice(&payload);
    Ok(frame)
}

#[cfg(test)]
mod tests {
    use super::*;

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
