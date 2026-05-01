use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

struct SidecarState {
    child: Mutex<Option<CommandChild>>,
}

async fn spawn_sidecar(app: &tauri::AppHandle) -> Result<CommandChild, String> {
    let (mut rx, child) = app
        .shell()
        .sidecar("butler-sidecar")
        .map_err(|e| format!("sidecar 명령 생성 실패: {}", e))?
        .args(["--port", "5903", "--host", "127.0.0.1"])
        .spawn()
        .map_err(|e| format!("sidecar 실행 실패: {}", e))?;

    // 로그 수신 — 별도 task로 분리 (spawn_sidecar를 블록하지 않음)
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    if let Ok(s) = String::from_utf8(line) {
                        print!("[sidecar] {}", s);
                    }
                }
                CommandEvent::Stderr(line) => {
                    if let Ok(s) = String::from_utf8(line) {
                        eprint!("[sidecar-err] {}", s);
                    }
                }
                CommandEvent::Error(err) => {
                    eprintln!("[sidecar-error] {}", err);
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[sidecar] 종료: code={:?}", payload.code);
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState {
            child: Mutex::new(None),
        })
        .setup(|app| {
            let app_handle = app.handle().clone();
            tauri::async_runtime::block_on(async move {
                match spawn_sidecar(&app_handle).await {
                    Ok(child) => {
                        app_handle
                            .state::<SidecarState>()
                            .child
                            .lock()
                            .unwrap()
                            .replace(child);
                        println!("[main] sidecar 시작 완료 (포트 5903)");
                    }
                    Err(e) => {
                        eprintln!("[main] sidecar 시작 실패: {}", e);
                        eprintln!("[main] Python3 및 의존성 설치를 확인하세요.");
                        eprintln!("[main] 가이드: docs/beta/getting_started_v1.md 1.4-1.5절");
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<SidecarState>();
                if let Some(child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                    println!("[main] sidecar 종료 완료");
                }
            }
        })
        .invoke_handler(tauri::generate_handler![])
        .run(tauri::generate_context!())
        .expect("Tauri 앱 실행 실패");
}
