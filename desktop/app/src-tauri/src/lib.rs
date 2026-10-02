//! LawPractice desktop app.
//!
//! Two ways to work:
//! * **This computer** – the app starts the bundled LawPractice server (`resources/server`) on
//!   127.0.0.1 and keeps the database, documents and backups in the user's app-data folder.
//!   No internet needed.
//! * **Firm server** – the app opens the firm's hosted LawPractice address (shared by all staff).
//!
//! The launcher (`ui/index.html`) is the only page that can call into Rust. Pages served by a
//! LawPractice server get no access to the computer; the native menu provides backups, zoom and
//! switching.

use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::webview::DownloadEvent;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_opener::OpenerExt;

const MAIN: &str = "main";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(120);

/// Runs in every page the window loads (launcher and LawPractice pages alike). The app has a
/// single window, so links that would open a new tab open in place, and `window.print()` keeps
/// working through the webview's own print dialog.
const PAGE_SCRIPT: &str = r#"
(function () {
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[target="_blank"]') : null;
    if (a && a.href) { a.removeAttribute('target'); }
  }, true);
  window.open = function (url) { if (url) { window.location.assign(url); } return window; };
})();
"#;

#[derive(Serialize, Deserialize, Default, Clone)]
struct Config {
    /// "local" or "server"; empty until the user picks one.
    #[serde(default)]
    mode: String,
    #[serde(default)]
    server_url: String,
    /// Open the chosen mode straight away next time.
    #[serde(default)]
    remember: bool,
}

#[derive(Default)]
struct AppState {
    backend: Mutex<Option<Child>>,
    local_url: Mutex<Option<String>>,
    launcher_url: Mutex<Option<Url>>,
    zoom: Mutex<f64>,
}

#[derive(Serialize)]
struct LauncherInfo {
    config: Config,
    data_dir: String,
    version: String,
    backend_available: bool,
    auto_start_local: bool,
}

// ---------------------------------------------------------------- paths & config

fn data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn config_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("settings.json"))
}

fn load_config(app: &AppHandle) -> Config {
    config_path(app)
        .ok()
        .and_then(|p| fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_config(app: &AppHandle, config: &Config) -> Result<(), String> {
    let text = serde_json::to_string_pretty(config).map_err(|e| e.to_string())?;
    fs::write(config_path(app)?, text).map_err(|e| e.to_string())
}

/// The bundled server program: `<resources>/server/lawpractice-server[.exe]`.
/// During development `LAWPRACTICE_SERVER_BIN` can point at a PyInstaller build instead.
fn backend_binary(app: &AppHandle) -> Option<PathBuf> {
    if let Ok(path) = std::env::var("LAWPRACTICE_SERVER_BIN") {
        let path = PathBuf::from(path);
        if path.exists() {
            return Some(path);
        }
    }
    let name = if cfg!(windows) { "lawpractice-server.exe" } else { "lawpractice-server" };
    let path = app.path().resource_dir().ok()?.join("server").join(name);
    path.exists().then_some(path)
}

// ---------------------------------------------------------------- local server

fn free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();
    Ok(port)
}

fn healthy(port: u16) -> bool {
    let addr = format!("127.0.0.1:{port}");
    let Ok(mut stream) = TcpStream::connect_timeout(&addr.parse().unwrap(), Duration::from_millis(500)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(3)));
    if stream
        .write_all(b"GET /health/ HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut response = String::new();
    let _ = stream.read_to_string(&mut response);
    response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200")
}

fn spawn_backend(app: &AppHandle, binary: &Path, data: &Path, port: u16) -> Result<Child, String> {
    let log = fs::File::create(data.join("server.log")).map_err(|e| e.to_string())?;
    let log_err = log.try_clone().map_err(|e| e.to_string())?;
    let mut command = Command::new(binary);
    command
        .args(["serve", "--watch-parent", "--port", &port.to_string(), "--data"])
        .arg(data)
        .stdin(Stdio::piped()) // the server exits when this pipe closes, i.e. when the app quits
        .stdout(log)
        .stderr(log_err);
    if let Some(dir) = binary.parent() {
        command.current_dir(dir);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let _ = app; // kept for future per-app environment
    command.spawn().map_err(|e| format!("Could not start the LawPractice server: {e}"))
}

/// Start the bundled server if it isn't running and wait until it answers.
fn ensure_local_server(app: &AppHandle) -> Result<String, String> {
    let state = app.state::<AppState>();
    if let Some(url) = state.local_url.lock().unwrap().clone() {
        if let Some(port) = Url::parse(&url).ok().and_then(|u| u.port()) {
            if healthy(port) {
                return Ok(url);
            }
        }
    }
    let binary = backend_binary(app).ok_or(
        "This copy of LawPractice doesn't include the built-in server. Reinstall it, or connect to your firm's server.",
    )?;
    let data = data_dir(app)?;
    let port = free_port()?;
    let mut child = spawn_backend(app, &binary, &data, port)?;

    let started = Instant::now();
    loop {
        if healthy(port) {
            break;
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!(
                "The LawPractice server stopped while starting ({status}). Details are in {}",
                data.join("server.log").display()
            ));
        }
        if started.elapsed() > STARTUP_TIMEOUT {
            let _ = child.kill();
            return Err("The LawPractice server took too long to start. Please try again.".into());
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    let url = format!("http://127.0.0.1:{port}/");
    *state.backend.lock().unwrap() = Some(child);
    *state.local_url.lock().unwrap() = Some(url.clone());
    Ok(url)
}

fn stop_backend(app: &AppHandle) {
    let state = app.state::<AppState>();
    let child = state.backend.lock().unwrap().take();
    if let Some(mut child) = child {
        drop(child.stdin.take()); // lets the server shut down on its own
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            if let Ok(Some(_)) = child.try_wait() {
                return;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        let _ = child.kill();
        let _ = child.wait();
    }
    *state.local_url.lock().unwrap() = None;
}

fn run_backup(app: &AppHandle) -> Result<PathBuf, String> {
    let binary = backend_binary(app).ok_or("Backups are only available when working on this computer.")?;
    let data = data_dir(app)?;
    let mut command = Command::new(&binary);
    command.args(["backup", "--data"]).arg(&data);
    if let Some(dir) = binary.parent() {
        command.current_dir(dir);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    let output = command.output().map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).into_owned());
    }
    let path = String::from_utf8_lossy(&output.stdout).trim().lines().last().unwrap_or("").to_string();
    Ok(PathBuf::from(path))
}

// ---------------------------------------------------------------- navigation

fn main_window(app: &AppHandle) -> Result<WebviewWindow, String> {
    app.get_webview_window(MAIN).ok_or_else(|| "The main window is not open.".to_string())
}

fn go_to(app: &AppHandle, url: &str) -> Result<(), String> {
    let url = Url::parse(url).map_err(|e| e.to_string())?;
    main_window(app)?.navigate(url).map_err(|e| e.to_string())
}

fn show_launcher(app: &AppHandle) {
    let launcher = app.state::<AppState>().launcher_url.lock().unwrap().clone();
    if let (Some(url), Ok(window)) = (launcher, main_window(app)) {
        let _ = window.navigate(url);
    }
}

/// Accepts "firm.example.com", "https://firm.example.com/..." etc. and returns the site root.
fn normalise_server_url(input: &str) -> Result<String, String> {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return Err("Enter your firm's LawPractice address.".into());
    }
    let with_scheme = if trimmed.contains("://") { trimmed.to_string() } else { format!("https://{trimmed}") };
    let url = Url::parse(&with_scheme).map_err(|_| "That doesn't look like a web address.".to_string())?;
    let host = url.host_str().unwrap_or_default().to_string();
    if host.is_empty() {
        return Err("That doesn't look like a web address.".into());
    }
    let local = host == "localhost"
        || host.starts_with("127.")
        || host.starts_with("192.168.")
        || host.starts_with("10.")
        || host.ends_with(".local");
    match url.scheme() {
        "https" => {}
        "http" if local => {}
        "http" => return Err("For security the firm server must use https://".into()),
        _ => return Err("The address must start with https://".into()),
    }
    let mut root = format!("{}://{}", url.scheme(), host);
    if let Some(port) = url.port() {
        root.push_str(&format!(":{port}"));
    }
    root.push('/');
    Ok(root)
}

// ---------------------------------------------------------------- launcher commands

#[tauri::command]
fn launcher_info(app: AppHandle) -> Result<LauncherInfo, String> {
    let config = load_config(&app);
    Ok(LauncherInfo {
        auto_start_local: config.remember && config.mode == "local",
        config,
        data_dir: data_dir(&app)?.display().to_string(),
        version: app.package_info().version.to_string(),
        backend_available: backend_binary(&app).is_some(),
    })
}

/// Starts the built-in server and returns its address. The launcher page then navigates itself:
/// a navigation issued from Rust while this call's reply is still in flight can be dropped by
/// the webview.
#[tauri::command]
async fn open_local(app: AppHandle, remember: bool) -> Result<String, String> {
    let handle = app.clone();
    let url = tauri::async_runtime::spawn_blocking(move || ensure_local_server(&handle))
        .await
        .map_err(|e| e.to_string())??;
    let mut config = load_config(&app);
    config.mode = "local".into();
    config.remember = remember;
    save_config(&app, &config)?;
    Ok(url)
}

#[tauri::command]
fn open_server(app: AppHandle, url: String, remember: bool) -> Result<String, String> {
    let root = normalise_server_url(&url)?;
    let mut config = load_config(&app);
    config.mode = "server".into();
    config.server_url = root.clone();
    config.remember = remember;
    save_config(&app, &config)?;
    Ok(root)
}

#[tauri::command]
fn backup_now(app: AppHandle) -> Result<String, String> {
    run_backup(&app).map(|p| p.display().to_string())
}

#[tauri::command]
fn open_data_folder(app: AppHandle) -> Result<(), String> {
    let dir = data_dir(&app)?;
    app.opener().open_path(dir.display().to_string(), None::<&str>).map_err(|e| e.to_string())
}

fn message(app: &AppHandle, text: &str, kind: MessageDialogKind) {
    app.dialog().message(text).title("LawPractice").kind(kind).show(|_| {});
}

/// Back up, then copy the backup to a folder the user picks (a USB drive, a synced cloud folder…).
fn backup_to_folder(app: &AppHandle) {
    let handle = app.clone();
    app.dialog().file().set_title("Choose where to save a copy of the backup").pick_folder(move |folder| {
        let Some(folder) = folder.and_then(|f| f.into_path().ok()) else { return };
        let result = run_backup(&handle).and_then(|zip| {
            let name = zip.file_name().ok_or("Backup file missing")?.to_owned();
            let target = folder.join(name);
            fs::copy(&zip, &target).map_err(|e| e.to_string())?;
            Ok(target)
        });
        match result {
            Ok(target) => message(&handle, &format!("Backup copied to:\n{}", target.display()), MessageDialogKind::Info),
            Err(e) => message(&handle, &format!("The backup could not be copied: {e}"), MessageDialogKind::Error),
        }
    });
}

/// Replace this computer's data with a backup. The server is stopped first, the current data
/// is backed up automatically by the restore step, then the server starts again.
fn restore_from_backup(app: &AppHandle) {
    let handle = app.clone();
    app.dialog()
        .file()
        .set_title("Choose a LawPractice backup to restore")
        .add_filter("LawPractice backup", &["zip"])
        .pick_file(move |file| {
            let Some(archive) = file.and_then(|f| f.into_path().ok()) else { return };
            let confirm_handle = handle.clone();
            handle
                .dialog()
                .message(format!(
                    "Replace all data on this computer with the backup\n{}?\n\nYour current data is backed up first, so this can be undone.",
                    archive.display()
                ))
                .title("Restore backup")
                .kind(MessageDialogKind::Warning)
                .buttons(MessageDialogButtons::OkCancelCustom("Restore".into(), "Cancel".into()))
                .show(move |confirmed| {
                    if !confirmed {
                        return;
                    }
                    let app = confirm_handle.clone();
                    std::thread::spawn(move || {
                        let result = (|| -> Result<String, String> {
                            let binary = backend_binary(&app).ok_or("The built-in server is missing.")?;
                            stop_backend(&app);
                            let mut command = Command::new(&binary);
                            command.args(["restore", "--data"]).arg(data_dir(&app)?).arg(&archive);
                            #[cfg(windows)]
                            {
                                use std::os::windows::process::CommandExt;
                                command.creation_flags(0x0800_0000);
                            }
                            let output = command.output().map_err(|e| e.to_string())?;
                            if !output.status.success() {
                                return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
                            }
                            ensure_local_server(&app)
                        })();
                        match result {
                            Ok(url) => {
                                let _ = go_to(&app, &url);
                                message(&app, "The backup has been restored.", MessageDialogKind::Info);
                            }
                            Err(e) => message(&app, &format!("Restore failed: {e}"), MessageDialogKind::Error),
                        }
                    });
                });
        });
}

// ---------------------------------------------------------------- menu

fn build_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let home = MenuItem::with_id(app, "home", "Dashboard", true, Some("CmdOrCtrl+Shift+H"))?;
    let back = MenuItem::with_id(app, "back", "Back", true, Some("Alt+Left"))?;
    let forward = MenuItem::with_id(app, "forward", "Forward", true, Some("Alt+Right"))?;
    let reload = MenuItem::with_id(app, "reload", "Reload", true, Some("CmdOrCtrl+R"))?;
    let print = MenuItem::with_id(app, "print", "Print…", true, Some("CmdOrCtrl+P"))?;
    let backup = MenuItem::with_id(app, "backup", "Back up now", true, None::<&str>)?;
    let backup_to = MenuItem::with_id(app, "backup_to", "Back up to USB or another folder…", true, None::<&str>)?;
    let restore = MenuItem::with_id(app, "restore", "Restore from a backup…", true, None::<&str>)?;
    let data = MenuItem::with_id(app, "data", "Open data and backups folder", true, None::<&str>)?;
    let switch = MenuItem::with_id(app, "switch", "Switch computer / firm server…", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Exit", true, Some("CmdOrCtrl+Q"))?;
    let file = Submenu::with_items(
        app,
        "File",
        true,
        &[&home, &print, &PredefinedMenuItem::separator(app)?, &backup, &backup_to, &restore, &data, &switch,
          &PredefinedMenuItem::separator(app)?, &quit],
    )?;
    let edit = Submenu::with_items(
        app,
        "Edit",
        true,
        &[
            &PredefinedMenuItem::undo(app, None)?,
            &PredefinedMenuItem::redo(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, None)?,
            &PredefinedMenuItem::copy(app, None)?,
            &PredefinedMenuItem::paste(app, None)?,
            &PredefinedMenuItem::select_all(app, None)?,
        ],
    )?;
    let zoom_in = MenuItem::with_id(app, "zoom_in", "Zoom in", true, Some("CmdOrCtrl+="))?;
    let zoom_out = MenuItem::with_id(app, "zoom_out", "Zoom out", true, Some("CmdOrCtrl+-"))?;
    let zoom_reset = MenuItem::with_id(app, "zoom_reset", "Actual size", true, Some("CmdOrCtrl+0"))?;
    let view = Submenu::with_items(
        app,
        "View",
        true,
        &[&back, &forward, &reload, &PredefinedMenuItem::separator(app)?, &zoom_in, &zoom_out, &zoom_reset],
    )?;
    let about = MenuItem::with_id(app, "about", "About LawPractice", true, None::<&str>)?;
    let help = Submenu::with_items(app, "Help", true, &[&about])?;
    Menu::with_items(app, &[&file, &edit, &view, &help])
}

fn on_menu(app: &AppHandle, id: &str) {
    let Ok(window) = main_window(app) else { return };
    let state = app.state::<AppState>();
    match id {
        "home" => {
            let config = load_config(app);
            let target = match config.mode.as_str() {
                "local" => state.local_url.lock().unwrap().clone(),
                "server" if !config.server_url.is_empty() => Some(config.server_url),
                _ => None,
            };
            match target {
                Some(url) => {
                    let _ = go_to(app, &url);
                }
                None => show_launcher(app),
            }
        }
        "back" => {
            let _ = window.eval("history.back()");
        }
        "forward" => {
            let _ = window.eval("history.forward()");
        }
        "reload" => {
            let _ = window.eval("location.reload()");
        }
        "print" => {
            let _ = window.print();
        }
        "zoom_in" | "zoom_out" | "zoom_reset" => {
            let mut zoom = state.zoom.lock().unwrap();
            *zoom = match id {
                "zoom_in" => (*zoom + 0.1).min(2.0),
                "zoom_out" => (*zoom - 0.1).max(0.6),
                _ => 1.0,
            };
            let _ = window.set_zoom(*zoom);
        }
        "backup" => match run_backup(app) {
            Ok(path) => message(
                app,
                &format!(
                    "Backup saved:\n{}\n\nKeep copies away from this computer too: use \"Back up to USB or another folder\".",
                    path.display()
                ),
                MessageDialogKind::Info,
            ),
            Err(e) => message(app, &format!("Backup failed: {e}"), MessageDialogKind::Error),
        },
        "backup_to" => backup_to_folder(app),
        "restore" => restore_from_backup(app),
        "data" => {
            let _ = open_data_folder(app.clone());
        }
        "switch" => {
            let mut config = load_config(app);
            config.remember = false;
            let _ = save_config(app, &config);
            show_launcher(app);
        }
        "about" => {
            let text = format!(
                "LawPractice {}\nPractice management and trust accounting for law firms.\n\nData folder:\n{}",
                app.package_info().version,
                data_dir(app).map(|p| p.display().to_string()).unwrap_or_default()
            );
            message(app, &text, MessageDialogKind::Info);
        }
        "quit" => app.exit(0),
        _ => {}
    }
}

// ---------------------------------------------------------------- downloads

/// Fee notes, statements, CSV exports and documents are saved to the Downloads folder and
/// opened with the computer's default program.
fn handle_download(app: &AppHandle, event: DownloadEvent<'_>) -> bool {
    match event {
        DownloadEvent::Requested { url, destination } => {
            let downloads = app
                .path()
                .download_dir()
                .or_else(|_| app.path().home_dir().map(|h| h.join("Downloads")))
                .unwrap_or_else(|_| std::env::temp_dir());
            let _ = fs::create_dir_all(&downloads);
            let suggested = destination
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .filter(|n| !n.is_empty())
                .or_else(|| url.path_segments().and_then(|mut s| s.next_back()).map(str::to_string))
                .filter(|n| !n.is_empty())
                .unwrap_or_else(|| "download".into());
            *destination = unique_path(&downloads, &suggested);
            true
        }
        DownloadEvent::Finished { path, success, .. } => {
            if success {
                if let Some(path) = path {
                    let _ = app.opener().open_path(path.display().to_string(), None::<&str>);
                }
            }
            true
        }
        _ => true,
    }
}

fn unique_path(dir: &Path, name: &str) -> PathBuf {
    let candidate = dir.join(name);
    if !candidate.exists() {
        return candidate;
    }
    let (stem, ext) = match name.rsplit_once('.') {
        Some((s, e)) => (s.to_string(), format!(".{e}")),
        None => (name.to_string(), String::new()),
    };
    (1..1000)
        .map(|i| dir.join(format!("{stem} ({i}){ext}")))
        .find(|p| !p.exists())
        .unwrap_or(candidate)
}

// ---------------------------------------------------------------- app

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // A second launch just brings the running window forward (two copies would share
            // the same database).
            if let Some(window) = app.get_webview_window(MAIN) {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState { zoom: Mutex::new(1.0), ..Default::default() })
        .invoke_handler(tauri::generate_handler![
            launcher_info,
            open_local,
            open_server,
            backup_now,
            open_data_folder
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            let download_handle = handle.clone();
            let window = WebviewWindowBuilder::new(app, MAIN, WebviewUrl::App("index.html".into()))
                .title("LawPractice")
                .inner_size(1366.0, 820.0)
                .min_inner_size(1024.0, 680.0)
                .maximized(true)
                .menu(build_menu(&handle)?)
                .initialization_script(PAGE_SCRIPT)
                .on_download(move |_webview, event| handle_download(&download_handle, event))
                .build()?;
            *app.state::<AppState>().launcher_url.lock().unwrap() = window.url().ok();
            app.on_menu_event(|app, event| on_menu(app, event.id().as_ref()));

            // Reopen the remembered choice straight away.
            let config = load_config(&handle);
            if config.remember {
                match config.mode.as_str() {
                    "server" if !config.server_url.is_empty() => {
                        let _ = go_to(&handle, &config.server_url);
                    }
                    _ => {} // "local": the launcher starts it (it shows progress while it waits)
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building LawPractice");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            stop_backend(app);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn server_urls_are_normalised() {
        assert_eq!(normalise_server_url("firm.example.com").unwrap(), "https://firm.example.com/");
        assert_eq!(
            normalise_server_url(" https://firm.example.com/matters/12/ ").unwrap(),
            "https://firm.example.com/"
        );
        assert_eq!(normalise_server_url("http://192.168.1.20:8000").unwrap(), "http://192.168.1.20:8000/");
        assert!(normalise_server_url("http://firm.example.com").is_err());
        assert!(normalise_server_url("").is_err());
        assert!(normalise_server_url("ftp://x").is_err());
    }

    #[test]
    fn download_names_never_overwrite() {
        let dir = std::env::temp_dir().join(format!("lp-test-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("INV00001.pdf"), b"x").unwrap();
        assert_eq!(unique_path(&dir, "INV00001.pdf"), dir.join("INV00001 (1).pdf"));
        assert_eq!(unique_path(&dir, "new.csv"), dir.join("new.csv"));
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn free_port_is_usable() {
        let port = free_port().unwrap();
        assert!(port > 0);
        assert!(!healthy(port));
    }
}
