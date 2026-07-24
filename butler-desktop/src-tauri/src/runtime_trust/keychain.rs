#[cfg(target_os = "macos")]
mod platform {
    use std::ffi::{c_char, c_void, CString};
    use std::fs::{File, OpenOptions};
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
    use std::ptr;

    use crate::runtime_trust::state::TrustedState;

    type CFTypeRef = *const c_void;
    type CFStringRef = *const c_void;
    type CFDataRef = *const c_void;
    type CFDictionaryRef = *const c_void;
    type CFAllocatorRef = *const c_void;
    type CFIndex = isize;
    type CFTypeId = usize;
    type OSStatus = i32;

    const UTF8: u32 = 0x0800_0100;
    const ITEM_NOT_FOUND: OSStatus = -25300;
    const DUPLICATE_ITEM: OSStatus = -25299;

    #[link(name = "CoreFoundation", kind = "framework")]
    extern "C" {
        static kCFAllocatorDefault: CFAllocatorRef;
        static kCFBooleanTrue: CFTypeRef;
        fn CFStringCreateWithCString(
            allocator: CFAllocatorRef,
            value: *const c_char,
            encoding: u32,
        ) -> CFStringRef;
        fn CFDataCreate(allocator: CFAllocatorRef, bytes: *const u8, length: CFIndex) -> CFDataRef;
        fn CFDictionaryCreate(
            allocator: CFAllocatorRef,
            keys: *const *const c_void,
            values: *const *const c_void,
            count: CFIndex,
            key_callbacks: *const c_void,
            value_callbacks: *const c_void,
        ) -> CFDictionaryRef;
        fn CFGetTypeID(value: CFTypeRef) -> CFTypeId;
        fn CFDataGetTypeID() -> CFTypeId;
        fn CFDataGetLength(value: CFDataRef) -> CFIndex;
        fn CFDataGetBytePtr(value: CFDataRef) -> *const u8;
        fn CFRelease(value: CFTypeRef);
    }

    #[link(name = "Security", kind = "framework")]
    extern "C" {
        static kSecClass: CFTypeRef;
        static kSecClassGenericPassword: CFTypeRef;
        static kSecAttrService: CFTypeRef;
        static kSecAttrAccount: CFTypeRef;
        static kSecAttrAccessible: CFTypeRef;
        static kSecAttrAccessibleWhenUnlockedThisDeviceOnly: CFTypeRef;
        static kSecValueData: CFTypeRef;
        static kSecReturnData: CFTypeRef;
        static kSecMatchLimit: CFTypeRef;
        static kSecMatchLimitOne: CFTypeRef;
        static kSecUseDataProtectionKeychain: CFTypeRef;
        fn SecItemCopyMatching(query: CFDictionaryRef, result: *mut CFTypeRef) -> OSStatus;
        fn SecItemAdd(attributes: CFDictionaryRef, result: *mut CFTypeRef) -> OSStatus;
        fn SecItemUpdate(query: CFDictionaryRef, attributes: CFDictionaryRef) -> OSStatus;
        fn SecItemDelete(query: CFDictionaryRef) -> OSStatus;
    }

    struct Owned(CFTypeRef);
    impl Drop for Owned {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe { CFRelease(self.0) };
            }
        }
    }

    unsafe fn text(value: &str) -> Result<Owned, &'static str> {
        let value = CString::new(value).map_err(|_| "BLOCK_TRUST_STATE_CAS")?;
        let reference = CFStringCreateWithCString(kCFAllocatorDefault, value.as_ptr(), UTF8);
        if reference.is_null() {
            return Err("BLOCK_TRUST_STATE_CAS");
        }
        Ok(Owned(reference))
    }

    unsafe fn data(value: &[u8]) -> Result<Owned, &'static str> {
        let reference = CFDataCreate(kCFAllocatorDefault, value.as_ptr(), value.len() as CFIndex);
        if reference.is_null() {
            return Err("BLOCK_TRUST_STATE_CAS");
        }
        Ok(Owned(reference))
    }

    unsafe fn dictionary(pairs: &[(CFTypeRef, CFTypeRef)]) -> Result<Owned, &'static str> {
        let keys: Vec<CFTypeRef> = pairs.iter().map(|pair| pair.0).collect();
        let values: Vec<CFTypeRef> = pairs.iter().map(|pair| pair.1).collect();
        let reference = CFDictionaryCreate(
            kCFAllocatorDefault,
            keys.as_ptr(),
            values.as_ptr(),
            pairs.len() as CFIndex,
            ptr::null(),
            ptr::null(),
        );
        if reference.is_null() {
            return Err("BLOCK_TRUST_STATE_CAS");
        }
        Ok(Owned(reference))
    }

    unsafe fn base_query(service: CFTypeRef, account: CFTypeRef) -> Result<Owned, &'static str> {
        dictionary(&[
            (kSecClass, kSecClassGenericPassword),
            (kSecAttrService, service),
            (kSecAttrAccount, account),
            (kSecUseDataProtectionKeychain, kCFBooleanTrue),
        ])
    }

    struct ProcessLock(File);

    impl Drop for ProcessLock {
        fn drop(&mut self) {
            unsafe {
                libc::flock(self.0.as_raw_fd(), libc::LOCK_UN);
            }
        }
    }

    fn process_lock() -> Result<ProcessLock, &'static str> {
        let uid = unsafe { libc::getuid() };
        let path = format!("/tmp/com.butler.firstscreen.trusted-state.{uid}.lock");
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .mode(0o600)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(path)
            .map_err(|_| "BLOCK_TRUST_STATE_CAS")?;
        let metadata = file.metadata().map_err(|_| "BLOCK_TRUST_STATE_CAS")?;
        if !metadata.file_type().is_file()
            || metadata.uid() != uid
            || metadata.nlink() != 1
            || metadata.mode() & 0o077 != 0
        {
            return Err("BLOCK_TRUST_STATE_CAS");
        }
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) } != 0 {
            return Err("BLOCK_TRUST_STATE_CAS");
        }
        Ok(ProcessLock(file))
    }

    fn read_unlocked() -> Result<Option<Vec<u8>>, &'static str> {
        unsafe {
            let service = text("com.butler.firstscreen.trusted-state.v3")?;
            let account = text("native-authority")?;
            let query = dictionary(&[
                (kSecClass, kSecClassGenericPassword),
                (kSecAttrService, service.0),
                (kSecAttrAccount, account.0),
                (kSecUseDataProtectionKeychain, kCFBooleanTrue),
                (kSecReturnData, kCFBooleanTrue),
                (kSecMatchLimit, kSecMatchLimitOne),
            ])?;
            let mut result: CFTypeRef = ptr::null();
            let status = SecItemCopyMatching(query.0, &mut result);
            if status == ITEM_NOT_FOUND {
                return Ok(None);
            }
            if status != 0 || result.is_null() {
                return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
            }
            let owned = Owned(result);
            if CFGetTypeID(owned.0) != CFDataGetTypeID() {
                return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
            }
            let length = CFDataGetLength(owned.0 as CFDataRef);
            if !(1..=1_048_576).contains(&length) {
                return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
            }
            let bytes =
                std::slice::from_raw_parts(CFDataGetBytePtr(owned.0 as CFDataRef), length as usize);
            Ok(Some(bytes.to_vec()))
        }
    }

    fn write_unlocked(value: &[u8], exists: bool) -> Result<(), &'static str> {
        unsafe {
            let service = text("com.butler.firstscreen.trusted-state.v3")?;
            let account = text("native-authority")?;
            let value = data(value)?;
            let query = base_query(service.0, account.0)?;
            let update = dictionary(&[(kSecValueData, value.0)])?;
            let status = if exists {
                SecItemUpdate(query.0, update.0)
            } else {
                let add = dictionary(&[
                    (kSecClass, kSecClassGenericPassword),
                    (kSecAttrService, service.0),
                    (kSecAttrAccount, account.0),
                    (kSecUseDataProtectionKeychain, kCFBooleanTrue),
                    (
                        kSecAttrAccessible,
                        kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
                    ),
                    (kSecValueData, value.0),
                ])?;
                let added = SecItemAdd(add.0, ptr::null_mut());
                if added == DUPLICATE_ITEM {
                    SecItemUpdate(query.0, update.0)
                } else {
                    added
                }
            };
            if status == 0 {
                Ok(())
            } else {
                Err("BLOCK_TRUST_STATE_CAS")
            }
        }
    }

    fn delete_unlocked() -> Result<(), &'static str> {
        unsafe {
            let service = text("com.butler.firstscreen.trusted-state.v3")?;
            let account = text("native-authority")?;
            let query = base_query(service.0, account.0)?;
            let status = SecItemDelete(query.0);
            if status == 0 || status == ITEM_NOT_FOUND {
                Ok(())
            } else {
                Err("BLOCK_TRUST_STATE_CAS")
            }
        }
    }

    pub fn read() -> Result<Option<Vec<u8>>, &'static str> {
        read_unlocked()
    }

    pub fn compare_and_swap(
        expected_generation: u64,
        value: &[u8],
    ) -> Result<Vec<u8>, &'static str> {
        let _lock = process_lock()?;
        let previous = read_unlocked()?;
        let observed_generation = match previous.as_deref() {
            None => 0,
            Some(raw) => {
                serde_json::from_slice::<TrustedState>(raw)
                    .map_err(|_| "BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?
                    .generation
            }
        };
        if observed_generation != expected_generation {
            return Err("BLOCK_TRUST_STATE_CAS");
        }
        write_unlocked(value, previous.is_some())?;
        let read_back = read_unlocked()?.ok_or("BLOCK_TRUST_STATE_CAS")?;
        if read_back != value {
            match previous {
                Some(raw) => write_unlocked(&raw, true)?,
                None => delete_unlocked()?,
            }
            return Err("BLOCK_TRUST_STATE_CAS");
        }
        Ok(read_back)
    }
}

#[cfg(target_os = "macos")]
pub use platform::{compare_and_swap, read};

#[cfg(not(target_os = "macos"))]
pub fn read() -> Result<Option<Vec<u8>>, &'static str> {
    Ok(None)
}

#[cfg(not(target_os = "macos"))]
pub fn compare_and_swap(_expected_generation: u64, _value: &[u8]) -> Result<Vec<u8>, &'static str> {
    Err("UNVERIFIED_PLATFORM_EVIDENCE_MISSING")
}
