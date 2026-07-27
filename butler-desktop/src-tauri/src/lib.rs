use std::{
    env,
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Read, Write},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::Manager;

mod asset_trust_root;
#[path = "../asset_trust_root_constants.rs"]
mod asset_trust_root_constants;
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

const ASSET_BOOTSTRAP_FD_ENV: &str = "BUTLER_BOOTSTRAP_FD";
const BUTLER_APP_DATA_DIR_ENV: &str = "BUTLER_APP_DATA_DIR";
const BUTLER_HOME_BOOTSTRAP_ENV: &str = "BUTLER_HOME_BOOTSTRAP_NEW_INSTALL";
const MODEL_TIER_NATIVE_TELEMETRY_ENV: &str = "BUTLER_MODEL_TIER_NATIVE_TELEMETRY_JSON";

struct SidecarState {
    child: Mutex<Option<Child>>,
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

fn configure_sidecar_environment(
    command: &mut Command,
    bootstrap_fd: i32,
    sidecar_env: &[(String, String)],
) {
    command
        .env_clear()
        .env("LANG", "C.UTF-8")
        .env("LC_ALL", "C.UTF-8")
        .env(ASSET_BOOTSTRAP_FD_ENV, bootstrap_fd.to_string());
    for (name, value) in sidecar_env {
        command.env(name, value);
    }
}

fn stop_sidecar(app: &tauri::AppHandle, reason: &str) {
    let child_opt = {
        let state = app.state::<SidecarState>();
        let x = state.child.lock().unwrap().take();
        x
    };
    if let Some(mut child) = child_opt {
        let _ = child.kill();
        append_sidecar_launch_log(&format!("stop_sidecar reason={}", reason));
        println!("[main] sidecar 종료 완료 ({})", reason);
    }
}

#[cfg(unix)]
fn open_asset_root(app: &tauri::AppHandle) -> Result<std::fs::File, String> {
    use std::ffi::CString;
    use std::os::fd::FromRawFd;
    use std::os::unix::ffi::OsStrExt;

    let asset_root = app
        .path()
        .resource_dir()
        .map_err(|_| "ASSET_RESOURCE_ROOT_UNAVAILABLE".to_string())?
        .join("assets");
    let raw = CString::new(asset_root.as_os_str().as_bytes())
        .map_err(|_| "ASSET_RESOURCE_ROOT_INVALID".to_string())?;
    let fd = unsafe {
        libc::open(
            raw.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err("ASSET_RESOURCE_ROOT_UNAVAILABLE".to_string());
    }
    Ok(unsafe { std::fs::File::from_raw_fd(fd) })
}

#[cfg(unix)]
fn read_asset_root_file(root_fd: i32, name: &str, limit: u64) -> Result<String, String> {
    use std::ffi::CString;
    use std::os::fd::FromRawFd;

    if name.is_empty() || name.contains('/') || name.contains("..") {
        return Err("ASSET_RELATIVE_PATH_INVALID".to_string());
    }
    let raw = CString::new(name).map_err(|_| "ASSET_RELATIVE_PATH_INVALID".to_string())?;
    let fd = unsafe {
        libc::openat(
            root_fd,
            raw.as_ptr(),
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err("ASSET_BUILD_CONTEXT_UNAVAILABLE".to_string());
    }
    let mut file = unsafe { std::fs::File::from_raw_fd(fd) };
    let metadata = file
        .metadata()
        .map_err(|_| "ASSET_BUILD_CONTEXT_INVALID".to_string())?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > limit {
        return Err("ASSET_BUILD_CONTEXT_INVALID".to_string());
    }
    let mut raw_text = String::new();
    file.read_to_string(&mut raw_text)
        .map_err(|_| "ASSET_BUILD_CONTEXT_INVALID".to_string())?;
    Ok(raw_text)
}

#[cfg(unix)]
fn sidecar_command_paths(app: &tauri::AppHandle) -> Result<(PathBuf, PathBuf), String> {
    let resource_root = app
        .path()
        .resource_dir()
        .map_err(|_| "SIDECAR_RESOURCE_ROOT_UNAVAILABLE".to_string())?;
    let bundled = (
        resource_root.join("python/bin/python3"),
        resource_root.join("butler_sidecar.py"),
    );
    let selected = if bundled.0.is_file() && bundled.1.is_file() {
        bundled
    } else if cfg!(debug_assertions) {
        (
            PathBuf::from("/usr/bin/python3"),
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../..")
                .join("butler_sidecar.py"),
        )
    } else {
        return Err("SIDECAR_BUNDLE_INCOMPLETE".to_string());
    };
    for path in [&selected.0, &selected.1] {
        let metadata =
            fs::symlink_metadata(path).map_err(|_| "SIDECAR_EXECUTABLE_INVALID".to_string())?;
        if metadata.file_type().is_symlink() || !metadata.is_file() || !path.is_absolute() {
            return Err("SIDECAR_EXECUTABLE_INVALID".to_string());
        }
    }
    Ok(selected)
}

#[cfg(unix)]
async fn spawn_sidecar(app: &tauri::AppHandle) -> Result<Child, String> {
    use std::os::fd::{AsRawFd, FromRawFd};
    use std::os::unix::process::CommandExt;

    append_sidecar_launch_log("spawn_sidecar=start");
    let sidecar_env = resolve_sidecar_env(app)?;
    let asset_root = open_asset_root(app)?;
    let asset_root_fd = asset_root.as_raw_fd();
    let bootstrap = asset_bootstrap_frame(app, asset_root_fd)?;
    let mut pipe_fds = [-1_i32; 2];
    if unsafe { libc::pipe(pipe_fds.as_mut_ptr()) } != 0 {
        return Err("ASSET_BOOTSTRAP_PIPE_FAILED".to_string());
    }
    let bootstrap_read = unsafe { std::fs::File::from_raw_fd(pipe_fds[0]) };
    let mut bootstrap_write = unsafe { std::fs::File::from_raw_fd(pipe_fds[1]) };
    bootstrap_write
        .write_all(&bootstrap)
        .map_err(|_| "ASSET_BOOTSTRAP_WRITE_FAILED".to_string())?;
    drop(bootstrap_write);

    let (python, sidecar) = sidecar_command_paths(app)?;
    let bootstrap_fd = bootstrap_read.as_raw_fd();
    let mut command = Command::new(python);
    configure_sidecar_environment(&mut command, bootstrap_fd, &sidecar_env);
    command
        .arg(sidecar)
        .args(["--port", "8765", "--host", "127.0.0.1"])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    unsafe {
        command.pre_exec(move || {
            for fd in [bootstrap_fd, asset_root_fd] {
                if libc::fcntl(fd, libc::F_SETFD, 0) < 0 {
                    return Err(std::io::Error::last_os_error());
                }
            }
            Ok(())
        });
    }
    let mut child = command
        .spawn()
        .map_err(|_| "SIDECAR_SPAWN_FAILED".to_string())?;
    drop(bootstrap_read);
    drop(asset_root);
    append_sidecar_launch_log("spawn_sidecar=ok");
    if let Some(stdout) = child.stdout.take() {
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                append_sidecar_launch_log(&format!("stdout {}", line));
            }
        });
    }
    if let Some(stderr) = child.stderr.take() {
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                append_sidecar_launch_log(&format!("stderr {}", line));
            }
        });
    }
    Ok(child)
}

#[cfg(not(unix))]
async fn spawn_sidecar(_app: &tauri::AppHandle) -> Result<Child, String> {
    Err("BLOCK_PLATFORM_UNSUPPORTED".to_string())
}

fn asset_bootstrap_frame(app: &tauri::AppHandle, asset_root_fd: i32) -> Result<Vec<u8>, String> {
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
        match read_asset_root_file(asset_root_fd, "ASSET_BUILD_CONTEXT.json", 64 * 1024) {
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
            Err(_) if profile != "production" => None,
            Err(_) => return Err("asset build context unavailable".to_string()),
        };
    let trust_root = asset_trust_root::embedded_asset_trust_root().map_err(str::to_string)?;
    let security_state = asset_trust_root::AssetSecurityState::from_root(&trust_root, false);
    if profile == "production" {
        security_state
            .require_distribution()
            .map_err(str::to_string)?;
    }
    let payload = serde_json::json!({
        "schema_version": 1,
        "asset_root_fd": asset_root_fd,
        "app_data_root": app_data_root,
        "release_profile": profile,
        "build_id": commit,
        "source_commit": commit,
        "source_tree": tree,
        "manifest_set_sha256": manifest_set,
        "trust_root_status": trust_root.status,
        "root_policy_sha256": trust_root.policy_sha256,
        "trusted_keys": trust_root.keys,
        "trust_epoch": trust_root.current_epoch,
        "revoked_key_ids": trust_root.revoked_key_ids,
        "security_state": security_state,
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

    #[cfg(unix)]
    #[test]
    fn native_launcher_clears_poisoned_parent_environment() {
        let mut command = Command::new("/usr/bin/env");
        command
            .env(concat!("PYTEST_", "CURRENT_TEST"), "attacker")
            .env(concat!("HELPER1_", "SDK_PATH"), "/attacker")
            .env(concat!("BGE_M3_", "MODEL_DIR"), "/attacker")
            .env("PATH", "/attacker")
            .env("PYTHONPATH", "/attacker")
            .env("LD_PRELOAD", "/attacker")
            .env("DYLD_INSERT_LIBRARIES", "/attacker");
        configure_sidecar_environment(
            &mut command,
            17,
            &[(
                "BUTLER_APP_DATA_DIR".to_string(),
                "/private/app".to_string(),
            )],
        );
        let output = command.output().expect("absolute env command runs");
        assert!(output.status.success());
        let actual = String::from_utf8(output.stdout).expect("env output is utf8");
        let rows: std::collections::BTreeSet<&str> = actual.lines().collect();
        assert_eq!(
            rows,
            std::collections::BTreeSet::from([
                "BUTLER_APP_DATA_DIR=/private/app",
                "BUTLER_BOOTSTRAP_FD=17",
                "LANG=C.UTF-8",
                "LC_ALL=C.UTF-8",
            ])
        );
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

#[tauri::command]
fn get_asset_security_state() -> Result<asset_trust_root::AssetSecurityState, String> {
    asset_trust_root::current_asset_security_state(false).map_err(str::to_string)
}

#[tauri::command]
fn authorize_asset_external_handoff() -> Result<(), String> {
    let state = get_asset_security_state()?;
    state.require_external_handoff().map_err(str::to_string)
}

#[tauri::command]
fn authorize_asset_auto_update() -> Result<(), String> {
    let state = get_asset_security_state()?;
    state.require_auto_update().map_err(str::to_string)
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
            let child = tauri::async_runtime::block_on(spawn_sidecar(&app_handle))
                .map_err(std::io::Error::other)?;
            {
                let state = app_handle.state::<SidecarState>();
                *state.child.lock().unwrap() = Some(child);
            }
            append_sidecar_launch_log("setup_spawn_sidecar=ok");
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
            get_asset_security_state,
            authorize_asset_external_handoff,
            authorize_asset_auto_update,
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
