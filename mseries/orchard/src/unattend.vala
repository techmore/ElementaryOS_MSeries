/* Windows unattended-install answer file (autounattend.xml) that loads the virtio-win drivers.
 *
 * Everything in this file is a pure function of its inputs (no I/O), so it can be unit tested:
 *   - WindowsUnattend.generate() builds the answer file;
 *   - WindowsUnattend.driver_paths() lists the virtio-win folders per guest architecture;
 *   - WindowsUnattend.merge_media() / remove_media() edit a vm.conf EXTRA_MEDIA list.
 *
 * What the answer file does (Microsoft's unattend schema, urn:schemas-microsoft-com:unattend):
 *   windowsPE   Microsoft-Windows-PnpCustomizationsWinPE DriverPaths: storage (viostor, vioscsi), network
 *               (NetKVM) and input (vioinput) drivers are loaded while Setup runs, so Setup can read the
 *               installer media and the disk without "Install driver / A media driver your computer needs
 *               is missing" and without the manual Browse step.
 *   specialize  Microsoft-Windows-PnpCustomizationsNonWinPE DriverPaths: the full set (display viogpudo,
 *               balloon, serial, rng, pvpanic as well) is staged in the installed system's driver store,
 *               plus a pnputil fallback per driver for the case where DriverPaths skips a folder.
 *   oobeSystem  optional local administrator account, so the Microsoft-account and network pages are skipped.
 *
 * Disk handling is opt-in: with wipe_disk off there is no DiskConfiguration, so Setup still asks which
 * disk to use and nothing is erased.
 *
 * The virtio-win ISO is attached as a second CD, so its drive letter is not known in advance; every
 * driver folder is therefore listed for each letter D..K. Folders that do not exist are ignored. */

public class UnattendOptions : Object {
    /* Guest architecture: "aarch64" (Windows 11 ARM64) or "x86_64" (Windows 11 amd64). */
    public string arch { get; set; default = "aarch64"; }
    /* Optional local administrator. Both fields empty means "do not create an account". */
    public string account { get; set; default = ""; }
    public string password { get; set; default = ""; }
    /* Windows language tag for Setup and the new system, e.g. en-US. */
    public string locale { get; set; default = "en-US"; }
    /* Best effort: also set BypassNRO so OOBE does not insist on a network or Microsoft account. */
    public bool skip_network { get; set; default = false; }
    /* DANGEROUS (opt-in): partition and format the guest's first virtual disk without asking. */
    public bool wipe_disk { get; set; default = false; }
}

public class WindowsUnattend : Object {
    /* Drive letters the extra CD/USB media can get while Setup runs. C: is the system disk, A:/B: are legacy. */
    public const string[] DRIVE_LETTERS = { "D", "E", "F", "G", "H", "I", "J", "K" };
    /* Needed while Setup is running: disk, network, input. */
    public const string[] SETUP_DRIVERS = { "viostor", "vioscsi", "NetKVM", "vioinput" };
    /* Staged into the installed system. */
    public const string[] SYSTEM_DRIVERS = { "viostor", "vioscsi", "NetKVM", "vioinput", "viogpudo", "Balloon", "vioserial", "viorng", "pvpanic" };
    /* Folder of virtio-win's per-Windows-version tree: Windows 11 / Server 2025. */
    public const string WINDOWS_DIR = "w11";

    private const string PUBLIC_KEY_TOKEN = "31bf3856ad364e35";

    /* Setup's processorArchitecture attribute for a Machine Lab architecture, or null if unsupported. */
    public static string? processor_arch (string arch) {
        switch (arch) {
            case "aarch64": return "arm64";
            case "x86_64": return "amd64";
            default: return null;
        }
    }

    /* The folder name virtio-win uses for that architecture, or null if unsupported. */
    public static string? virtio_arch (string arch) {
        switch (arch) {
            case "aarch64": return "ARM64";
            case "x86_64": return "amd64";
            default: return null;
        }
    }

    /* Driver folders on the virtio-win ISO for one architecture, relative to the ISO root, e.g.
     * NetKVM\w11\ARM64. Empty when the architecture is unsupported. */
    public static string[] driver_folders (string arch, string[] drivers) {
        string? va = virtio_arch (arch);
        string[] folders = {};
        if (va == null) {
            return folders;
        }
        foreach (var d in drivers) {
            folders += "%s\\%s\\%s".printf (d, WINDOWS_DIR, va);
        }
        return folders;
    }

    /* Every absolute path a DriverPaths list should contain: each folder under each drive letter. */
    public static string[] driver_paths (string arch, string[] drivers) {
        string[] paths = {};
        foreach (var folder in driver_folders (arch, drivers)) {
            foreach (var letter in DRIVE_LETTERS) {
                paths += "%s:\\%s".printf (letter, folder);
            }
        }
        return paths;
    }

    public static string xml_escape (string s) {
        return s.replace ("&", "&amp;").replace ("<", "&lt;").replace (">", "&gt;").replace ("\"", "&quot;").replace ("'", "&apos;");
    }

    /* Windows local account names: up to 20 characters, none of " / \ [ ] : ; | = , + * ? < > @,
     * not only dots or spaces, no control characters. */
    public static bool valid_account_name (string name) {
        if (name == "" || name.char_count () > 20) {
            return false;
        }
        if (name.strip () == "" || name.strip ().replace (".", "") == "") {
            return false;
        }
        int idx = 0;
        unichar c;
        while (name.get_next_char (ref idx, out c)) {
            if (c < 32 || c == 127 || "\"/\\[]:;|=,+*?<>@".index_of_char (c) >= 0) {
                return false;
            }
        }
        return true;
    }

    public static bool valid_locale (string tag) {
        try {
            return new Regex ("^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){1,2}$").match (tag);
        } catch (RegexError e) {
            return false;
        }
    }

    /* Builds the answer file. Returns null and sets `error` (a sentence for the user) when the options
     * cannot make a valid file. */
    public static string? generate (UnattendOptions o, out string error) {
        error = "";
        string? pa = processor_arch (o.arch);
        if (pa == null) {
            error = "Unsupported guest architecture “%s”: use ARM64 or x86-64.".printf (o.arch);
            return null;
        }
        if (!valid_locale (o.locale)) {
            error = "“%s” is not a Windows language tag (for example en-US).".printf (o.locale);
            return null;
        }
        bool account = o.account != "" || o.password != "";
        if (account) {
            if (!valid_account_name (o.account)) {
                error = "Use an account name of up to 20 characters without \" / \\ [ ] : ; | = , + * ? < > @.";
                return null;
            }
            if (o.password == "") {
                error = "A local account needs a password.";
                return null;
            }
            for (int i = 0; i < o.password.length; i++) {
                if ((uint8) o.password[i] < 32 || (uint8) o.password[i] == 127) {
                    error = "The password cannot contain control characters.";
                    return null;
                }
            }
        }

        var sb = new StringBuilder ();
        sb.append ("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n");
        sb.append ("<!-- Generated by Machine Lab. Loads the virtio-win drivers during Windows Setup. -->\n");
        sb.append ("<unattend xmlns=\"urn:schemas-microsoft-com:unattend\" xmlns:wcm=\"http://schemas.microsoft.com/WMIConfig/2002/State\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">\n");

        // ---- windowsPE ----
        sb.append ("  <settings pass=\"windowsPE\">\n");
        sb.append (open_component ("Microsoft-Windows-International-Core-WinPE", pa));
        sb.append ("      <SetupUILanguage>\n        <UILanguage>%s</UILanguage>\n      </SetupUILanguage>\n".printf (xml_escape (o.locale)));
        sb.append (locale_elements (o.locale, "      "));
        sb.append ("    </component>\n");
        if (o.wipe_disk) {
            sb.append (open_component ("Microsoft-Windows-Setup", pa));
            sb.append (DISK_CONFIGURATION);
            sb.append (IMAGE_INSTALL);
            sb.append ("    </component>\n");
        }
        sb.append (open_component ("Microsoft-Windows-PnpCustomizationsWinPE", pa));
        sb.append (driver_paths_xml (driver_paths (o.arch, SETUP_DRIVERS)));
        sb.append ("    </component>\n");
        sb.append ("  </settings>\n");

        // ---- specialize ----
        sb.append ("  <settings pass=\"specialize\">\n");
        sb.append (open_component ("Microsoft-Windows-PnpCustomizationsNonWinPE", pa));
        sb.append (driver_paths_xml (driver_paths (o.arch, SYSTEM_DRIVERS)));
        sb.append ("    </component>\n");
        sb.append (open_component ("Microsoft-Windows-Deployment", pa));
        sb.append ("      <RunSynchronous>\n");
        int order = 1;
        if (o.skip_network) {
            sb.append (run_command (order++, "reg add HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\OOBE /v BypassNRO /t REG_DWORD /d 1 /f",
                                    "Let OOBE continue without a network or Microsoft account"));
        }
        foreach (var folder in driver_folders (o.arch, SYSTEM_DRIVERS)) {
            sb.append (run_command (order++, pnputil_command (folder), "Install " + folder.split ("\\")[0] + " with pnputil"));
        }
        sb.append ("      </RunSynchronous>\n");
        sb.append ("    </component>\n");
        sb.append ("  </settings>\n");

        // ---- oobeSystem ----
        sb.append ("  <settings pass=\"oobeSystem\">\n");
        sb.append (open_component ("Microsoft-Windows-International-Core", pa));
        sb.append (locale_elements (o.locale, "      "));
        sb.append ("    </component>\n");
        if (account) {
            sb.append (open_component ("Microsoft-Windows-Shell-Setup", pa));
            sb.append ("      <OOBE>\n");
            sb.append ("        <HideLocalAccountScreen>true</HideLocalAccountScreen>\n");
            sb.append ("        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>\n");
            sb.append ("        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>\n");
            sb.append ("      </OOBE>\n");
            sb.append ("      <UserAccounts>\n        <LocalAccounts>\n          <LocalAccount wcm:action=\"add\">\n");
            sb.append ("            <Password>\n              <Value>%s</Value>\n              <PlainText>true</PlainText>\n            </Password>\n".printf (xml_escape (o.password)));
            sb.append ("            <DisplayName>%s</DisplayName>\n".printf (xml_escape (o.account)));
            sb.append ("            <Group>Administrators</Group>\n");
            sb.append ("            <Name>%s</Name>\n".printf (xml_escape (o.account)));
            sb.append ("          </LocalAccount>\n        </LocalAccounts>\n      </UserAccounts>\n");
            sb.append ("    </component>\n");
        }
        sb.append ("  </settings>\n");
        sb.append ("</unattend>\n");
        return sb.str;
    }

    // ---- building blocks ----

    private static string open_component (string name, string pa) {
        return "    <component name=\"%s\" processorArchitecture=\"%s\" publicKeyToken=\"%s\" language=\"neutral\" versionScope=\"nonSxS\">\n".printf (name, pa, PUBLIC_KEY_TOKEN);
    }

    private static string locale_elements (string locale, string indent) {
        string l = xml_escape (locale);
        return "%s<InputLocale>%s</InputLocale>\n%s<SystemLocale>%s</SystemLocale>\n%s<UILanguage>%s</UILanguage>\n%s<UserLocale>%s</UserLocale>\n".printf (
            indent, l, indent, l, indent, l, indent, l);
    }

    private static string driver_paths_xml (string[] paths) {
        var sb = new StringBuilder ("      <DriverPaths>\n");
        int key = 1;
        foreach (var p in paths) {
            sb.append ("        <PathAndCredentials wcm:action=\"add\" wcm:keyValue=\"%d\">\n          <Path>%s</Path>\n        </PathAndCredentials>\n".printf (key++, xml_escape (p)));
        }
        sb.append ("      </DriverPaths>\n");
        return sb.str;
    }

    private static string run_command (int order, string command, string description) {
        return "        <RunSynchronousCommand wcm:action=\"add\">\n          <Order>%d</Order>\n          <Path>%s</Path>\n          <Description>%s</Description>\n        </RunSynchronousCommand>\n".printf (
            order, xml_escape (command), xml_escape (description));
    }

    /* cmd /c loop over the possible drive letters; installs the folder's drivers where it exists. */
    private static string pnputil_command (string folder) {
        return "cmd /c for %i in (D E F G H I J K) do @if exist %i:\\" + folder + "\\ pnputil /add-driver %i:\\" + folder + "\\*.inf /install";
    }

    /* UEFI/GPT layout: 100 MB EFI system partition, 16 MB MSR, Windows on the rest. Only used with wipe_disk. */
    private const string DISK_CONFIGURATION =
"""      <DiskConfiguration>
        <Disk wcm:action="add">
          <DiskID>0</DiskID>
          <WillWipeDisk>true</WillWipeDisk>
          <CreatePartitions>
            <CreatePartition wcm:action="add">
              <Order>1</Order>
              <Type>EFI</Type>
              <Size>100</Size>
            </CreatePartition>
            <CreatePartition wcm:action="add">
              <Order>2</Order>
              <Type>MSR</Type>
              <Size>16</Size>
            </CreatePartition>
            <CreatePartition wcm:action="add">
              <Order>3</Order>
              <Type>Primary</Type>
              <Extend>true</Extend>
            </CreatePartition>
          </CreatePartitions>
          <ModifyPartitions>
            <ModifyPartition wcm:action="add">
              <Order>1</Order>
              <PartitionID>1</PartitionID>
              <Label>System</Label>
              <Format>FAT32</Format>
            </ModifyPartition>
            <ModifyPartition wcm:action="add">
              <Order>2</Order>
              <PartitionID>2</PartitionID>
            </ModifyPartition>
            <ModifyPartition wcm:action="add">
              <Order>3</Order>
              <PartitionID>3</PartitionID>
              <Label>Windows</Label>
              <Letter>C</Letter>
              <Format>NTFS</Format>
            </ModifyPartition>
          </ModifyPartitions>
        </Disk>
        <WillShowUI>OnError</WillShowUI>
      </DiskConfiguration>
""";

    private const string IMAGE_INSTALL =
"""      <ImageInstall>
        <OSImage>
          <InstallTo>
            <DiskID>0</DiskID>
            <PartitionID>3</PartitionID>
          </InstallTo>
          <WillShowUI>OnError</WillShowUI>
        </OSImage>
      </ImageInstall>
""";

    // ---- vm.conf EXTRA_MEDIA (a space-separated list) ----

    public static bool path_is_listable (string path) {
        return path != "" && !path.contains (" ") && !path.contains ("\t") && !path.contains ("\n");
    }

    private static string[] media_entries (string list) {
        string[] entries = {};
        foreach (var e in list.split (" ")) {
            if (e.strip () != "") {
                entries += e.strip ();
            }
        }
        return entries;
    }

    /* True when the list already holds a virtio-win ISO (any path or version). */
    public static bool has_virtio_win (string existing) {
        foreach (var e in media_entries (existing)) {
            if (Path.get_basename (e).down ().has_prefix ("virtio-win")) {
                return true;
            }
        }
        return false;
    }

    /* Keeps every existing entry and appends each addition that is not already listed. A virtio-win ISO
     * that is already attached (by any path) is not added a second time. */
    public static string merge_media (string existing, string[] additions) {
        string[] entries = media_entries (existing);
        foreach (var add in additions) {
            bool have = false;
            bool is_virtio = Path.get_basename (add).down ().has_prefix ("virtio-win");
            foreach (var e in entries) {
                if (e == add || (is_virtio && Path.get_basename (e).down ().has_prefix ("virtio-win"))) {
                    have = true;
                }
            }
            if (!have) {
                entries += add;
            }
        }
        return string.joinv (" ", entries);
    }

    /* Drops one entry; every other entry is kept in order. */
    public static string remove_media (string existing, string path) {
        string[] kept = {};
        foreach (var e in media_entries (existing)) {
            if (e != path) {
                kept += e;
            }
        }
        return string.joinv (" ", kept);
    }
}
