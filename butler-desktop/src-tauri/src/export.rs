use std::{
    ffi::OsStr,
    fs::{self, File, OpenOptions},
    io::{self, Write},
    path::Path,
    time::SystemTime,
};

#[cfg(unix)]
use std::io::Read;

#[cfg(any(windows, test))]
use std::path::PathBuf;

use tauri_plugin_dialog::DialogExt;

const MAX_EXPORT_BYTES: usize = 64 * 1024 * 1024;
const ALLOWED_EXPORT_EXTENSIONS: [&str; 3] = ["docx", "md", "xlsx"];
const TEMP_CREATE_ATTEMPTS: usize = 16;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ExportError {
    RequestInvalid,
    ExtensionMismatch,
    TargetInvalid,
    OverwriteNotConfirmed,
    TempCreateFailed,
    WriteFailed,
    SyncFailed,
    AtomicReplaceFailed,
    #[cfg(unix)]
    DirectorySyncFailed,
}

impl ExportError {
    const fn public_code(self) -> &'static str {
        match self {
            Self::RequestInvalid => "EXPORT_REQUEST_INVALID",
            Self::ExtensionMismatch => "EXPORT_EXTENSION_MISMATCH",
            Self::TargetInvalid => "EXPORT_TARGET_INVALID",
            Self::OverwriteNotConfirmed => "EXPORT_OVERWRITE_NOT_CONFIRMED",
            Self::TempCreateFailed => "EXPORT_TEMP_CREATE_FAILED",
            Self::WriteFailed => "EXPORT_WRITE_FAILED",
            Self::SyncFailed => "EXPORT_SYNC_FAILED",
            Self::AtomicReplaceFailed => "EXPORT_ATOMIC_REPLACE_FAILED",
            #[cfg(unix)]
            Self::DirectorySyncFailed => "EXPORT_DIRECTORY_SYNC_FAILED",
        }
    }
}

impl From<ExportError> for String {
    fn from(value: ExportError) -> Self {
        value.public_code().to_string()
    }
}

fn valid_export_request(suggested_name: &str, extension: &str, bytes: &[u8]) -> bool {
    let name = Path::new(suggested_name);
    name.components().count() == 1
        && name.file_name().and_then(OsStr::to_str) == Some(suggested_name)
        && name.extension().and_then(OsStr::to_str) == Some(extension)
        && ALLOWED_EXPORT_EXTENSIONS.contains(&extension)
        && !bytes.is_empty()
        && bytes.len() <= MAX_EXPORT_BYTES
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct TargetSnapshot {
    existed: bool,
    length: u64,
    modified: Option<SystemTime>,
    #[cfg(unix)]
    device: u64,
    #[cfg(unix)]
    inode: u64,
    #[cfg(unix)]
    status_changed_seconds: i64,
    #[cfg(unix)]
    status_changed_nanoseconds: i64,
    #[cfg(unix)]
    parent_device: u64,
    #[cfg(unix)]
    parent_inode: u64,
    #[cfg(windows)]
    creation_time: u64,
    #[cfg(windows)]
    last_write_time: u64,
    #[cfg(windows)]
    file_attributes: u32,
}

fn is_reparse_or_symlink(metadata: &fs::Metadata) -> bool {
    if metadata.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    }
    #[cfg(not(windows))]
    {
        false
    }
}

#[cfg(windows)]
fn validate_parent(parent: &Path) -> Result<(), ExportError> {
    let metadata = fs::symlink_metadata(parent).map_err(|_| ExportError::TargetInvalid)?;
    if !metadata.is_dir() || is_reparse_or_symlink(&metadata) {
        return Err(ExportError::TargetInvalid);
    }
    Ok(())
}

fn target_snapshot(path: &Path) -> Result<TargetSnapshot, ExportError> {
    #[cfg(unix)]
    let parent_metadata = {
        use std::os::unix::fs::MetadataExt;
        let parent = path.parent().ok_or(ExportError::TargetInvalid)?;
        let metadata = fs::symlink_metadata(parent).map_err(|_| ExportError::TargetInvalid)?;
        if !metadata.is_dir() || is_reparse_or_symlink(&metadata) {
            return Err(ExportError::TargetInvalid);
        }
        (metadata.dev(), metadata.ino())
    };
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if !metadata.is_file() || is_reparse_or_symlink(&metadata) {
                return Err(ExportError::TargetInvalid);
            }
            #[cfg(unix)]
            use std::os::unix::fs::MetadataExt;
            #[cfg(windows)]
            use std::os::windows::fs::MetadataExt;
            Ok(TargetSnapshot {
                existed: true,
                length: metadata.len(),
                modified: metadata.modified().ok(),
                #[cfg(unix)]
                device: metadata.dev(),
                #[cfg(unix)]
                inode: metadata.ino(),
                #[cfg(unix)]
                status_changed_seconds: metadata.ctime(),
                #[cfg(unix)]
                status_changed_nanoseconds: metadata.ctime_nsec(),
                #[cfg(unix)]
                parent_device: parent_metadata.0,
                #[cfg(unix)]
                parent_inode: parent_metadata.1,
                #[cfg(windows)]
                creation_time: metadata.creation_time(),
                #[cfg(windows)]
                last_write_time: metadata.last_write_time(),
                #[cfg(windows)]
                file_attributes: metadata.file_attributes(),
            })
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(TargetSnapshot {
            existed: false,
            length: 0,
            modified: None,
            #[cfg(unix)]
            device: 0,
            #[cfg(unix)]
            inode: 0,
            #[cfg(unix)]
            status_changed_seconds: 0,
            #[cfg(unix)]
            status_changed_nanoseconds: 0,
            #[cfg(unix)]
            parent_device: parent_metadata.0,
            #[cfg(unix)]
            parent_inode: parent_metadata.1,
            #[cfg(windows)]
            creation_time: 0,
            #[cfg(windows)]
            last_write_time: 0,
            #[cfg(windows)]
            file_attributes: 0,
        }),
        Err(_) => Err(ExportError::TargetInvalid),
    }
}

#[cfg(windows)]
fn snapshot_unchanged(path: &Path, expected: &TargetSnapshot) -> Result<(), ExportError> {
    let actual = target_snapshot(path)?;
    if &actual != expected {
        return Err(ExportError::OverwriteNotConfirmed);
    }
    Ok(())
}

#[cfg(unix)]
fn fill_nonce(bytes: &mut [u8]) -> io::Result<()> {
    File::open("/dev/urandom")?.read_exact(bytes)
}

#[cfg(windows)]
fn fill_nonce(bytes: &mut [u8]) -> io::Result<()> {
    #[link(name = "bcrypt")]
    extern "system" {
        fn BCryptGenRandom(algorithm: isize, buffer: *mut u8, length: u32, flags: u32) -> i32;
    }
    const BCRYPT_USE_SYSTEM_PREFERRED_RNG: u32 = 0x00000002;
    let status = unsafe {
        BCryptGenRandom(
            0,
            bytes.as_mut_ptr(),
            bytes
                .len()
                .try_into()
                .map_err(|_| io::ErrorKind::InvalidInput)?,
            BCRYPT_USE_SYSTEM_PREFERRED_RNG,
        )
    };
    if status == 0 {
        Ok(())
    } else {
        Err(io::Error::other("CSPRNG_UNAVAILABLE"))
    }
}

#[cfg(windows)]
fn create_temporary(parent: &Path, name: &OsStr) -> Result<(PathBuf, File), ExportError> {
    for _ in 0..TEMP_CREATE_ATTEMPTS {
        let mut nonce = [0_u8; 16];
        fill_nonce(&mut nonce).map_err(|_| ExportError::TempCreateFailed)?;
        let suffix = nonce
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let temporary = parent.join(format!(".{}.{}.tmp", name.to_string_lossy(), suffix));
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(&temporary) {
            Ok(file) => return Ok((temporary, file)),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err(ExportError::TempCreateFailed),
        }
    }
    Err(ExportError::TempCreateFailed)
}

#[cfg(windows)]
fn publish(temporary: &Path, target: &Path, expected: &TargetSnapshot) -> Result<(), ExportError> {
    use std::os::windows::ffi::OsStrExt;
    type Bool = i32;
    type Dword = u32;
    #[link(name = "Kernel32")]
    extern "system" {
        fn ReplaceFileW(
            replaced: *const u16,
            replacement: *const u16,
            backup: *const u16,
            flags: Dword,
            exclude: *mut core::ffi::c_void,
            reserved: *mut core::ffi::c_void,
        ) -> Bool;
        fn MoveFileExW(existing: *const u16, new_name: *const u16, flags: Dword) -> Bool;
    }
    const MOVEFILE_WRITE_THROUGH: Dword = 0x00000008;
    fn wide(path: &Path) -> Vec<u16> {
        path.as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    snapshot_unchanged(target, expected)?;
    let source = wide(temporary);
    let destination = wide(target);
    let ok = unsafe {
        if expected.existed {
            ReplaceFileW(
                destination.as_ptr(),
                source.as_ptr(),
                std::ptr::null(),
                0,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
            )
        } else {
            // Publish a new destination without an overwrite flag.
            MoveFileExW(
                source.as_ptr(),
                destination.as_ptr(),
                MOVEFILE_WRITE_THROUGH,
            )
        }
    };
    if ok == 0 {
        Err(ExportError::AtomicReplaceFailed)
    } else {
        Ok(())
    }
}

#[cfg(windows)]
fn atomic_write_export(
    path: &Path,
    payload: &[u8],
    confirmed: &TargetSnapshot,
) -> Result<(), ExportError> {
    let parent = path.parent().ok_or(ExportError::TargetInvalid)?;
    let name = path.file_name().ok_or(ExportError::TargetInvalid)?;
    validate_parent(parent)?;
    let (temporary, mut file) = create_temporary(parent, name)?;
    let result = (|| {
        file.write_all(payload)
            .map_err(|_| ExportError::WriteFailed)?;
        file.sync_all().map_err(|_| ExportError::SyncFailed)?;
        drop(file);
        publish(&temporary, path, confirmed)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(unix)]
fn atomic_write_export(
    path: &Path,
    payload: &[u8],
    confirmed: &TargetSnapshot,
) -> Result<(), ExportError> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd};
    use std::os::unix::ffi::OsStrExt;
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};

    fn c_name(name: &OsStr) -> Result<CString, ExportError> {
        CString::new(name.as_bytes()).map_err(|_| ExportError::TargetInvalid)
    }

    fn snapshot_at(
        directory: &File,
        name: &CString,
        expected: &TargetSnapshot,
    ) -> Result<(), ExportError> {
        let mut stat = std::mem::MaybeUninit::<libc::stat>::uninit();
        let result = unsafe {
            libc::fstatat(
                directory.as_raw_fd(),
                name.as_ptr(),
                stat.as_mut_ptr(),
                libc::AT_SYMLINK_NOFOLLOW,
            )
        };
        if result == 0 {
            let stat = unsafe { stat.assume_init() };
            let actual = TargetSnapshot {
                existed: true,
                length: stat
                    .st_size
                    .try_into()
                    .map_err(|_| ExportError::TargetInvalid)?,
                modified: None,
                device: stat
                    .st_dev
                    .try_into()
                    .map_err(|_| ExportError::TargetInvalid)?,
                inode: stat.st_ino,
                status_changed_seconds: stat.st_ctime,
                status_changed_nanoseconds: stat.st_ctime_nsec,
                parent_device: expected.parent_device,
                parent_inode: expected.parent_inode,
            };
            // Rename/exchange itself may update timestamps. Device + inode are
            // the stable identity of the exact file the dialog confirmed.
            if !expected.existed
                || actual.device != expected.device
                || actual.inode != expected.inode
            {
                return Err(ExportError::OverwriteNotConfirmed);
            }
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if error.raw_os_error() == Some(libc::ENOENT) && !expected.existed {
            return Ok(());
        }
        Err(ExportError::OverwriteNotConfirmed)
    }

    #[cfg(target_os = "macos")]
    fn exchange_at(directory: &File, left: &CString, right: &CString) -> io::Result<()> {
        unsafe extern "C" {
            fn renameatx_np(
                from_fd: libc::c_int,
                from: *const libc::c_char,
                to_fd: libc::c_int,
                to: *const libc::c_char,
                flags: libc::c_uint,
            ) -> libc::c_int;
        }
        const RENAME_SWAP: libc::c_uint = 0x0000_0002;
        let result = unsafe {
            renameatx_np(
                directory.as_raw_fd(),
                left.as_ptr(),
                directory.as_raw_fd(),
                right.as_ptr(),
                RENAME_SWAP,
            )
        };
        if result == 0 {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }

    #[cfg(target_os = "linux")]
    fn exchange_at(directory: &File, left: &CString, right: &CString) -> io::Result<()> {
        const RENAME_EXCHANGE: libc::c_uint = 0x0000_0002;
        let result = unsafe {
            libc::syscall(
                libc::SYS_renameat2,
                directory.as_raw_fd(),
                left.as_ptr(),
                directory.as_raw_fd(),
                right.as_ptr(),
                RENAME_EXCHANGE,
            )
        };
        if result == 0 {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }

    #[cfg(not(any(target_os = "macos", target_os = "linux")))]
    fn exchange_at(_directory: &File, _left: &CString, _right: &CString) -> io::Result<()> {
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "ATOMIC_EXCHANGE_UNAVAILABLE",
        ))
    }

    let parent = path.parent().ok_or(ExportError::TargetInvalid)?;
    let name = c_name(path.file_name().ok_or(ExportError::TargetInvalid)?)?;
    let mut parent_options = OpenOptions::new();
    parent_options
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC);
    let directory = parent_options
        .open(parent)
        .map_err(|_| ExportError::TargetInvalid)?;
    let parent_metadata = directory
        .metadata()
        .map_err(|_| ExportError::TargetInvalid)?;
    if parent_metadata.dev() != confirmed.parent_device
        || parent_metadata.ino() != confirmed.parent_inode
    {
        return Err(ExportError::OverwriteNotConfirmed);
    }

    let mut temporary_name = None;
    let mut temporary_file = None;
    for _ in 0..TEMP_CREATE_ATTEMPTS {
        let mut nonce = [0_u8; 16];
        fill_nonce(&mut nonce).map_err(|_| ExportError::TempCreateFailed)?;
        let suffix = nonce
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let candidate = CString::new(format!(
            ".{}.{}.tmp",
            path.file_name()
                .ok_or(ExportError::TargetInvalid)?
                .to_string_lossy(),
            suffix
        ))
        .map_err(|_| ExportError::TempCreateFailed)?;
        let fd = unsafe {
            libc::openat(
                directory.as_raw_fd(),
                candidate.as_ptr(),
                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_CLOEXEC | libc::O_NOFOLLOW,
                0o600,
            )
        };
        if fd >= 0 {
            temporary_name = Some(candidate);
            temporary_file = Some(unsafe { File::from_raw_fd(fd) });
            break;
        }
        if io::Error::last_os_error().raw_os_error() != Some(libc::EEXIST) {
            return Err(ExportError::TempCreateFailed);
        }
    }
    let temporary = temporary_name.ok_or(ExportError::TempCreateFailed)?;
    let mut file = temporary_file.ok_or(ExportError::TempCreateFailed)?;
    let result = (|| {
        file.write_all(payload)
            .map_err(|_| ExportError::WriteFailed)?;
        file.sync_all().map_err(|_| ExportError::SyncFailed)?;
        drop(file);
        if confirmed.existed {
            // Exchange is atomic. The exact displaced inode is then available at
            // `temporary`, so identity validation cannot race with publication.
            exchange_at(&directory, &temporary, &name)
                .map_err(|_| ExportError::AtomicReplaceFailed)?;
            if let Err(error) = snapshot_at(&directory, &temporary, confirmed) {
                exchange_at(&directory, &temporary, &name)
                    .map_err(|_| ExportError::AtomicReplaceFailed)?;
                return Err(error);
            }
        } else {
            snapshot_at(&directory, &name, confirmed)?;
            let published = unsafe {
                libc::linkat(
                    directory.as_raw_fd(),
                    temporary.as_ptr(),
                    directory.as_raw_fd(),
                    name.as_ptr(),
                    0,
                )
            };
            if published != 0 {
                return Err(ExportError::AtomicReplaceFailed);
            }
        }
        let removed = unsafe { libc::unlinkat(directory.as_raw_fd(), temporary.as_ptr(), 0) };
        if removed != 0 {
            return Err(ExportError::AtomicReplaceFailed);
        }
        directory
            .sync_all()
            .map_err(|_| ExportError::DirectorySyncFailed)
    })();
    if result.is_err() {
        unsafe {
            libc::unlinkat(directory.as_raw_fd(), temporary.as_ptr(), 0);
        }
    }
    result
}

#[tauri::command]
pub async fn save_export_file(
    app: tauri::AppHandle,
    request: tauri::ipc::Request<'_>,
) -> Result<bool, String> {
    let tauri::ipc::InvokeBody::Raw(bytes) = request.body() else {
        return Err(ExportError::RequestInvalid.into());
    };
    let suggested_name = request
        .headers()
        .get("butler-export-name")
        .and_then(|value| value.to_str().ok())
        .ok_or_else(|| String::from(ExportError::RequestInvalid))?;
    let extension = request
        .headers()
        .get("butler-export-extension")
        .and_then(|value| value.to_str().ok())
        .ok_or_else(|| String::from(ExportError::RequestInvalid))?;
    if !valid_export_request(suggested_name, extension, bytes) {
        return Err(ExportError::RequestInvalid.into());
    }
    let selected = app
        .dialog()
        .file()
        .set_file_name(suggested_name)
        .add_filter("Butler export", &[extension])
        .blocking_save_file();
    let Some(selected) = selected else {
        return Ok(false);
    };
    let path = selected
        .into_path()
        .map_err(|_| String::from(ExportError::TargetInvalid))?;
    if path.extension().and_then(OsStr::to_str) != Some(extension) {
        return Err(ExportError::ExtensionMismatch.into());
    }
    // The native dialog performed the overwrite confirmation for this exact path.
    // Capture it immediately and reject any subsequent concurrent change.
    let confirmed = target_snapshot(&path).map_err(String::from)?;
    atomic_write_export(&path, bytes, &confirmed).map_err(String::from)?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    fn test_root(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "butler-export-{name}-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn validates_export_names_extensions_and_size() {
        assert!(valid_export_request("result.xlsx", "xlsx", &[1]));
        assert!(!valid_export_request("../result.xlsx", "xlsx", &[1]));
        assert!(!valid_export_request("result.docx", "xlsx", &[1]));
        assert!(!valid_export_request("result.exe", "exe", &[1]));
        assert!(!valid_export_request("result.xlsx", "xlsx", &[]));
        assert!(valid_export_request(
            "result.xlsx",
            "xlsx",
            &vec![0; MAX_EXPORT_BYTES]
        ));
        assert!(!valid_export_request(
            "result.xlsx",
            "xlsx",
            &vec![0; MAX_EXPORT_BYTES + 1]
        ));
    }

    #[test]
    fn all_public_error_codes_are_stable_and_sanitized() {
        let codes = [
            ExportError::RequestInvalid,
            ExportError::ExtensionMismatch,
            ExportError::TargetInvalid,
            ExportError::OverwriteNotConfirmed,
            ExportError::TempCreateFailed,
            ExportError::WriteFailed,
            ExportError::SyncFailed,
            ExportError::AtomicReplaceFailed,
            #[cfg(unix)]
            ExportError::DirectorySyncFailed,
        ];
        assert!(codes
            .iter()
            .all(|code| code.public_code().starts_with("EXPORT_")));
    }

    #[test]
    fn publishes_new_file_at_exact_path_without_implicit_extension_change() {
        let root = test_root("exact-path");
        let target = root.join("report.xlsx");
        let snapshot = target_snapshot(&target).unwrap();
        atomic_write_export(&target, b"workbook", &snapshot).unwrap();
        assert_eq!(fs::read(&target).unwrap(), b"workbook");
        assert!(!root.join("report.xlsx.xlsx").exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(any(target_os = "macos", target_os = "linux"))]
    #[test]
    fn atomically_replaces_the_exact_confirmed_file() {
        let root = test_root("confirmed-replace");
        let target = root.join("report.md");
        fs::write(&target, b"confirmed").unwrap();
        let snapshot = target_snapshot(&target).unwrap();
        atomic_write_export(&target, b"replacement", &snapshot).unwrap();
        assert_eq!(fs::read(&target).unwrap(), b"replacement");
        assert_eq!(
            fs::read_dir(&root).unwrap().count(),
            1,
            "the displaced inode must not remain as a temporary file"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn refuses_publish_after_confirmed_target_identity_changes() {
        let root = test_root("identity-swap");
        let target = root.join("report.md");
        fs::write(&target, b"first").unwrap();
        let confirmed = target_snapshot(&target).unwrap();
        fs::remove_file(&target).unwrap();
        fs::write(&target, b"other").unwrap();
        assert_eq!(
            atomic_write_export(&target, b"replacement", &confirmed).unwrap_err(),
            ExportError::OverwriteNotConfirmed
        );
        assert_eq!(fs::read(&target).unwrap(), b"other");
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlink_target_and_symlink_parent() {
        use std::os::unix::fs::symlink;

        let root = test_root("symlink");
        let real = root.join("real");
        fs::create_dir(&real).unwrap();
        let real_file = real.join("report.md");
        fs::write(&real_file, b"original").unwrap();
        let linked_file = root.join("linked.md");
        symlink(&real_file, &linked_file).unwrap();
        assert_eq!(
            target_snapshot(&linked_file).unwrap_err(),
            ExportError::TargetInvalid
        );

        let linked_parent = root.join("linked-parent");
        symlink(&real, &linked_parent).unwrap();
        assert_eq!(
            target_snapshot(&linked_parent.join("new.md")).unwrap_err(),
            ExportError::TargetInvalid
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn refuses_publish_after_confirmed_parent_directory_is_swapped() {
        let root = test_root("parent-swap");
        let selected_parent = root.join("selected");
        let moved_parent = root.join("selected-before-swap");
        fs::create_dir(&selected_parent).unwrap();
        let target = selected_parent.join("report.md");
        let confirmed = target_snapshot(&target).unwrap();

        fs::rename(&selected_parent, &moved_parent).unwrap();
        fs::create_dir(&selected_parent).unwrap();
        assert_eq!(
            atomic_write_export(&target, b"must-not-publish", &confirmed).unwrap_err(),
            ExportError::OverwriteNotConfirmed
        );
        assert!(!target.exists());
        assert!(!moved_parent.join("report.md").exists());
        fs::remove_dir_all(root).unwrap();
    }
}
