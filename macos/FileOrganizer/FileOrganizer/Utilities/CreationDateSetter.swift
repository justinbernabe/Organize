import Foundation
import Darwin

/// Sets macOS file creation (birth) date via setattrlist syscall.
/// Direct Darwin module call — no ctypes or subprocess needed.
struct CreationDateSetter {
    private static let ATTR_CMN_CRTIME: attrgroup_t = 0x00000200

    static func set(path: String, date: Date) -> Bool {
        var attrList = attrlist()
        attrList.bitmapcount = u_short(ATTR_BIT_MAP_COUNT)
        attrList.commonattr = ATTR_CMN_CRTIME

        var ts = timespec(
            tv_sec: Int(date.timeIntervalSince1970),
            tv_nsec: 0
        )

        return setattrlist(
            path,
            &attrList,
            &ts,
            MemoryLayout<timespec>.size,
            0
        ) == 0
    }
}
