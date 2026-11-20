import os
import re
import sys
import stat
import time
import shlex
import shutil
import argparse
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Enables ANSI colors in old Windows cmd (harmless on other systems)
os.system("")

# Makes emojis print correctly on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEVELOPER = "Hansraj"
PROG = "listmgr.py"

GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

PANEL_W = 34
BIG_FILE = 10 * 1024 * 1024
ANSI_RE = re.compile(r'\033\[[0-9;]*m')

# Messages from the last action, shown above the prompt
MESSAGES = []

# Folder size cache: path -> (mtime, size)
SIZE_CACHE = {}

# Commands that can change folder contents (cache is cleared after them)
CHANGING_CMDS = ("d", "c", "v", "r", "n", "m", "e")

PANEL_LINES = [
    "FUNCTIONS",
    "-" * 30,
    "e name        Edit (nano)",
    "d name        Delete",
    "o name        Open folder",
    "o ..          Go back",
    "n name        New file",
    "m name        New folder",
    "r old new     Rename",
    "c name dest   Copy",
    "v name dest   Move",
    "x name        Preview file",
    "i name        Info",
    "q             Quit",
    "",
    "name can be partial",
]


def clear_screen():
    # Fast clear: also wipes the scrollback, so no old list stays above
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\033[H\033[2J\033[3J")
        sys.stdout.flush()


def ok(msg):
    MESSAGES.append(f"{GREEN}✔ {msg}{RESET}")


def err(msg):
    MESSAGES.append(f"{RED}✘ {msg}{RESET}")


def note(msg):
    MESSAGES.append(msg)


def confirm(question):
    try:
        return input(f"{YELLOW}{question} (y/n): {RESET}").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def is_hidden(entry):
    # Linux/macOS/Termux: name starts with a dot
    if entry.name.startswith('.'):
        return True
    # Windows: hidden file attribute
    try:
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2))
    except OSError:
        return False


def get_dir_bytes(path):
    # Fast iterative scan using scandir (no recursion, no symlink following)
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def cached_dir_bytes(entry):
    try:
        mtime = entry.stat().st_mtime
    except OSError:
        return get_dir_bytes(entry.path)
    hit = SIZE_CACHE.get(entry.path)
    if hit and hit[0] == mtime:
        return hit[1]
    size = get_dir_bytes(entry.path)
    SIZE_CACHE[entry.path] = (mtime, size)
    return size


def visible_len(text):
    return len(ANSI_RE.sub("", text))


def merge_side_by_side(left, right, left_w):
    lines = []
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        pad = " " * max(left_w - visible_len(l), 0)
        sep = f"{CYAN}|{RESET}" if r else " "
        lines.append(f"{l}{pad} {sep} {CYAN}{r}{RESET}" if r else l)
    return lines


def build_list(search=None, only_folders=False, only_hidden=False):
    """Scan current folder, apply filters. Returns data used for display and commands."""
    entries = sorted(os.scandir("."), key=lambda e: e.name.lower())

    all_folders = []
    all_files = []
    for e in entries:
        try:
            if e.is_dir():
                all_folders.append(e)
            elif e.is_file():
                all_files.append(e)
        except OSError:
            pass

    # Folder sizes are calculated in parallel, cached, and reused for the total
    with ThreadPoolExecutor(max_workers=8) as pool:
        sizes = list(pool.map(cached_dir_bytes, all_folders))
    folder_size_map = {d.name: s for d, s in zip(all_folders, sizes)}

    total_bytes = sum(sizes)
    for f in all_files:
        try:
            total_bytes += f.stat().st_size
        except OSError:
            pass

    def keep(e):
        if only_hidden and not is_hidden(e):
            return False
        if search and search.lower() not in e.name.lower():
            return False
        return True

    folders = [d for d in all_folders if keep(d)]
    files = [] if only_folders else [f for f in all_files if keep(f)]
    return folders, files, folder_size_map, total_bytes


def file_list(search=None, only_folders=False, only_hidden=False, panel=True, loading=False):
    # "Loading..." is shown only while the list is really being built,
    # and is erased the moment it is ready (no artificial delay).
    if loading:
        sys.stdout.write(f"{CYAN}Loading...{RESET}")
        sys.stdout.flush()

    folders, files, folder_size_map, total_bytes = build_list(search, only_folders, only_hidden)

    if loading:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    now = time.time()
    shown = folders + files
    name_width = max([len(x.name) + 1 for x in shown] + [10]) + 2
    line_width = name_width + 20 + 12

    # Centered header: each line is centered on its own width
    term_w = shutil.get_terminal_size((80, 24)).columns
    line1 = f"✦ Created by:- {DEVELOPER} ✦"
    line2 = f"⌨ {PROG} -h for help"
    print(f"{' ' * max((term_w - len(line1)) // 2, 0)}{BOLD}{CYAN}{line1}{RESET}")
    print(f"{' ' * max((term_w - len(line2)) // 2, 0)}{CYAN}{line2}{RESET}")

    mode = []
    if only_folders:
        mode.append("Only Folders")
    if only_hidden:
        mode.append("Only Hidden")
    if search:
        mode.append(f"Search: '{search}'")
    if mode:
        print(f"{BOLD}{CYAN}Mode: {' | '.join(mode)}{RESET}")

    print(f"\n{GREEN}🟢 0-3 Days{RESET} | {YELLOW}🟡 4-7 Days{RESET} | {RED}🔴 >7 Days{RESET} | {BLUE}📁 Folder{RESET}")

    left = ["-" * line_width]

    if not shown:
        left.append("Nothing found.")

    # Folders first
    for d in folders:
        try:
            dt = datetime.fromtimestamp(d.stat().st_mtime).strftime('%d-%m-%Y %H:%M')
        except OSError:
            dt = "unknown"
        d_size = format_size(folder_size_map[d.name])
        left.append(f"{BOLD}{BLUE}{(d.name + '/'):<{name_width}} {dt:<20} {d_size}{RESET}")

    # Then files
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        age_days = (now - st.st_mtime) / 86400
        dt = datetime.fromtimestamp(st.st_mtime).strftime('%d-%m-%Y %H:%M')
        color = GREEN if age_days <= 3 else (YELLOW if age_days <= 7 else RED)
        left.append(f"{color}{f.name:<{name_width}} {dt:<20} {format_size(st.st_size)}{RESET}")

    left.append("-" * line_width)
    left.append(f"{BOLD}{CYAN}Summary:{RESET}")
    left.append(f"{'Total Files':<15}: {len(files)}")
    left.append(f"{'Total Folders':<15}: {len(folders)}")
    left.append(f"{'Folder Size':<15}: {format_size(total_bytes)}")
    left.append("-" * line_width)

    if panel:
        if term_w >= line_width + 3 + PANEL_W:
            # Wide screen: functions on the right side
            for line in merge_side_by_side(left, PANEL_LINES, line_width):
                print(line)
        else:
            # Narrow screen (phone): functions below the list
            for line in left:
                print(line)
            for line in PANEL_LINES:
                print(f"{CYAN}{line}{RESET}")
    else:
        for line in left:
            print(line)

    return folders + files


# ------------------------------------------------------------ functions
def get_editor():
    nano = shutil.which("nano")
    if nano:
        return [nano]
    if os.name == "nt":
        return ["notepad"]
    env = os.environ.get("EDITOR")
    if env:
        return shlex.split(env)
    for c in ("vim", "vi"):
        path = shutil.which(c)
        if path:
            return [path]
    return None


def find_item(items, text):
    """Exact name first, then partial match. Asks if several match."""
    for it in items:
        if it.name == text:
            return it
    matches = [it for it in items if text.lower() in it.name.lower()]
    if not matches:
        err(f"'{text}' not found in the current list.")
        return None
    if len(matches) == 1:
        return matches[0]
    err(f"{len(matches)} items match '{text}'. Type more of the name:")
    for m in matches[:15]:
        note(f"   {m.name}{'/' if m.is_dir() else ''}")
    return None


def do_edit(item):
    if item.is_dir():
        err("This is a folder. Use: o name")
        return
    try:
        size = item.stat().st_size
    except OSError:
        size = 0
    if size > BIG_FILE and not confirm(f"File is {format_size(size)}. Open anyway?"):
        return
    editor = get_editor()
    if not editor:
        err("No editor found. Install nano (Termux: pkg install nano).")
        return
    try:
        subprocess.call(editor + [item.path])
        ok(f"Closed editor for '{item.name}'")
    except OSError as e:
        err(f"Could not start editor: {e}")


def do_delete(item):
    if item.is_dir():
        print(f"{RED}{BOLD}WARNING: this folder and everything inside it will be deleted.{RESET}")
    if not confirm(f"Delete '{item.name}'?"):
        err("Cancelled.")
        return
    try:
        if item.is_symlink():
            os.unlink(item.path)
        elif item.is_dir():
            shutil.rmtree(item.path)
        else:
            os.remove(item.path)
        ok(f"Deleted '{item.name}'")
    except OSError as e:
        err(f"Delete failed: {e}")


def do_open(items, arg):
    if arg == "..":
        target = ".."
    else:
        item = find_item(items, arg)
        if not item:
            return
        if not item.is_dir():
            err("This is a file. Use: e name  or  x name")
            return
        target = item.path
    try:
        os.chdir(target)
    except OSError as e:
        err(f"Cannot open: {e}")


def do_new_file(name):
    if os.path.exists(name):
        err(f"'{name}' already exists.")
        return
    try:
        open(name, "w").close()
        ok(f"Created file '{name}'")
    except OSError as e:
        err(f"Failed: {e}")


def do_new_folder(name):
    if os.path.exists(name):
        err(f"'{name}' already exists.")
        return
    try:
        os.makedirs(name)
        ok(f"Created folder '{name}'")
    except OSError as e:
        err(f"Failed: {e}")


def do_rename(item, new):
    if os.path.exists(new):
        err(f"'{new}' already exists.")
        return
    try:
        os.rename(item.path, new)
        ok(f"Renamed '{item.name}' to '{new}'")
    except OSError as e:
        err(f"Rename failed: {e}")


def do_copy_move(item, dest, move):
    final = os.path.join(dest, item.name) if os.path.isdir(dest) else dest
    if os.path.exists(final):
        err(f"'{final}' already exists.")
        return
    try:
        if move:
            shutil.move(item.path, final)
            ok(f"Moved '{item.name}' to '{final}'")
        elif item.is_dir():
            shutil.copytree(item.path, final)
            ok(f"Copied folder '{item.name}' to '{final}'")
        else:
            shutil.copy2(item.path, final)
            ok(f"Copied '{item.name}' to '{final}'")
    except (OSError, shutil.Error) as e:
        err(f"Failed: {e}")


def do_preview(item):
    if item.is_dir():
        err("This is a folder.")
        return
    try:
        with open(item.path, "rb") as f:
            if b"\x00" in f.read(1024):
                err("Binary file, preview not available.")
                return
        clear_screen()
        print(f"{BOLD}{CYAN}--- {item.name} (first 40 lines) ---{RESET}")
        with open(item.path, "r", encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if n > 40:
                    print(f"{YELLOW}... (more lines not shown){RESET}")
                    break
                print(line.rstrip("\n")[:200])
        print(f"{BOLD}{CYAN}--- end ---{RESET}")
    except OSError as e:
        err(f"Cannot read: {e}")
        return
    input(f"\n{CYAN}Press Enter to go back...{RESET}")


def python_file_type(path):
    """Fallback file-type detection (used when the 'file' command is missing, e.g. Windows)."""
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
    except OSError:
        return "unknown"

    if not head:
        return "empty"

    # Known binary signatures
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG image"
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG image"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "GIF image"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "WebP image"
    if head.startswith(b"%PDF"):
        return "PDF document"
    if head.startswith(b"PK\x03\x04"):
        return "Zip archive"
    if head.startswith(b"\x1f\x8b"):
        return "gzip compressed data"
    if head.startswith(b"\x7fELF"):
        return "ELF executable"
    if head.startswith(b"SQLite format 3\x00"):
        return "SQLite database"
    if head[4:8] == b"ftyp":
        return "MP4/MOV video"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "MP3 audio"

    # Text encodings
    if head.startswith(b"\xef\xbb\xbf"):
        kind = "UTF-8 text (with BOM)"
    elif head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "UTF-16 text"
    elif b"\x00" in head:
        return "binary data"
    else:
        try:
            head.decode("ascii")
            kind = "ASCII text"
        except UnicodeDecodeError:
            try:
                head.decode("utf-8")
                kind = "UTF-8 text"
            except UnicodeDecodeError:
                # A multi-byte char may be cut at the 8192 boundary
                try:
                    head[:-3].decode("utf-8")
                    kind = "UTF-8 text"
                except UnicodeDecodeError:
                    return "ISO-8859 text / binary data"

    if b"\r\n" in head:
        kind += ", with CRLF line terminators"
    return kind


def get_file_type(path):
    """Uses the system 'file' command if available, otherwise Python detection."""
    if shutil.which("file"):
        try:
            r = subprocess.run(
                ["file", "-b", path],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                universal_newlines=True,
                timeout=5,
            )
            out = r.stdout.strip()
            if r.returncode == 0 and out:
                return out
        except (OSError, subprocess.SubprocessError):
            pass
    return python_file_type(path)


def do_info(item):
    try:
        st = os.stat(item.path)
    except OSError as e:
        err(f"Cannot read info: {e}")
        return
    size = get_dir_bytes(item.path) if item.is_dir() else st.st_size
    ftype = "Folder" if item.is_dir() else get_file_type(item.path)
    clear_screen()
    print(f"{BOLD}{CYAN}--- Info ---{RESET}")
    print(f"{'Name':<12}: {item.name}")
    print(f"{'Type':<12}: {ftype}")
    print(f"{'Path':<12}: {os.path.abspath(item.path)}")
    print(f"{'Size':<12}: {format_size(size)} ({size} bytes)")
    print(f"{'Permissions':<12}: {stat.filemode(st.st_mode)}")
    print(f"{'Modified':<12}: {datetime.fromtimestamp(st.st_mtime).strftime('%d-%m-%Y %H:%M:%S')}")
    input(f"\n{CYAN}Press Enter to go back...{RESET}")


def run_command(items, raw):
    """Returns 'quit' to exit, True to redraw list."""
    raw = raw.strip()
    if not raw:
        return True
    try:
        parts = shlex.split(raw, posix=(os.name != "nt"))
    except ValueError as e:
        err(f"Invalid input: {e}")
        return True
    parts = [p.strip('"\'') for p in parts]
    cmd, args = parts[0].lower(), parts[1:]

    if cmd in ("q", "quit", "exit"):
        return "quit"

    need = {"e": 1, "d": 1, "o": 1, "n": 1, "m": 1, "r": 2, "c": 2, "v": 2, "x": 1, "i": 1}
    if cmd not in need:
        err(f"Unknown command '{cmd}'. Commands are shown in the FUNCTIONS panel.")
        return True
    if len(args) < need[cmd]:
        err("Missing input. Example: " + {
            "e": "e notes", "d": "d notes", "o": "o backup", "n": "n new.txt",
            "m": "m backup", "r": "r old.txt new.txt", "c": "c notes backup",
            "v": "v notes backup", "x": "x notes", "i": "i notes",
        }[cmd])
        return True

    if cmd == "n":
        do_new_file(args[0])
    elif cmd == "m":
        do_new_folder(args[0])
    elif cmd == "o":
        do_open(items, args[0])
    else:
        item = find_item(items, args[0])
        if not item:
            return True
        if cmd == "e":
            do_edit(item)
        elif cmd == "d":
            do_delete(item)
        elif cmd == "r":
            do_rename(item, args[1])
        elif cmd == "c":
            do_copy_move(item, args[1], move=False)
        elif cmd == "v":
            do_copy_move(item, args[1], move=True)
        elif cmd == "x":
            do_preview(item)
        elif cmd == "i":
            do_info(item)
    return True


def interactive(search, only_folders, only_hidden):
    while True:
        # Clear the previous screen (also at start), then build the list
        clear_screen()
        items = file_list(search, only_folders, only_hidden, panel=True, loading=True)

        # Show result of the last action just above the prompt
        if MESSAGES:
            print()
            for m in MESSAGES:
                print(m)
            MESSAGES.clear()

        try:
            raw = input(f"\n{BOLD}{CYAN}Command > {RESET}")
        except (EOFError, KeyboardInterrupt):
            print()
            return

        cmd = raw.strip().split(" ")[0].lower()
        result = run_command(items, raw)
        if cmd in CHANGING_CMDS:
            SIZE_CACHE.clear()
        if result == "quit":
            return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Advanced file lister with colors, sizes, filters and file functions.",
        epilog=(
            "examples:\n"
            f"  {PROG}                 list + functions panel (edit, delete, ...)\n"
            f"  {PROG} -l              only the list, no functions\n"
            f"  {PROG} -s mp4          names containing 'mp4'\n"
            f"  {PROG} -d              only folders\n"
            f"  {PROG} -H              only hidden files/folders\n"
            f"  {PROG} -d -H           only hidden folders\n"
            "\n"
            "functions (type at the Command > prompt, name can be partial):\n"
            "  e name=edit in nano    d name=delete (asks y/n)\n"
            "  o name=open folder     o ..=go back\n"
            "  n name=new file        m name=new folder\n"
            "  r old new=rename       c name dest=copy     v name dest=move\n"
            "  x name=preview         i name=info          q=quit\n"
        ),
        formatter_class=argparse.RawDescriptionHel