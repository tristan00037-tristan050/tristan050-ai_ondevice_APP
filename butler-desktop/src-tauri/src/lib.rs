use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

const SIDECAR_HOST: &str = "127.0.0.1";
const SIDECAR_PORT: &str = "5903";

// src-tauri/ 기준 레포 루트 (컴파일 타임 상수)
const REPO_ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");

static SIDECAR_CHILD: Mutex<Option<Child>> = Mutex::new(None);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|_app| {
            spawn_sidecar();
            Ok(())
        })
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                kill_sidecar();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn spawn_sidecar() {
    std::thread::spawn(|| {
        let repo_root = PathBuf::from(REPO_ROOT);
        let sidecar_py = repo_root.join("butler_sidecar.py");

        if !sidecar_py.exists() {
            eprintln!(
                "[Butler] sidecar script not found at {}",
                sidecar_py.display()
            );
            return;
        }

        match Command::new("python3")
            .arg(&sidecar_py)
            .arg("--host")
            .arg(SIDECAR_HOST)
            .arg("--port")
            .arg(SIDECAR_PORT)
            .current_dir(&repo_root)
            .spawn()
        {
            Ok(child) => {
                *SIDECAR_CHILD.lock().unwrap() = Some(child);
                println!(
                    "[Butler] sidecar started on http://{}:{}",
                    SIDECAR_HOST, SIDECAR_PORT
                );
            }
            Err(e) => {
                eprintln!("[Butler] failed to spawn sidecar: {}", e);
            }
        }
    });
}

fn kill_sidecar() {
    if let Ok(mut guard) = SIDECAR_CHILD.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
        }
    }
}
