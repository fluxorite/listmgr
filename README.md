<div align="center">

# 📂 listmgr

**An advanced terminal file lister and manager.**
See your files with colors, sizes and filters, and edit, copy, move or delete them without leaving the terminal.

Created by **Hansraj**

</div>

---

## ✨ Features

- Colored list with file and folder sizes, plus a summary of totals
- Files are color-coded by age, so recent files stand out
- Search and filter by name, folders only, or hidden items only
- Built-in functions: edit, delete, open, create, rename, copy, move, preview and info
- Partial names work, so you do not have to type the full file name
- Asks for confirmation before deleting anything
- Folder sizes are calculated in parallel and cached for speed
- Works on Termux, Linux and Windows

---

## 🎨 Color Guide

| Color | Meaning |
|-------|---------|
| 🟢 Green | File modified in the last 0-3 days |
| 🟡 Yellow | File modified 4-7 days ago |
| 🔴 Red | File modified more than 7 days ago |
| 📁 Blue | Folder |

---

## 🛠️ Functions

Type these at the `Command >` prompt. The name can be partial.

| Command | What it does |
|---------|--------------|
| `e name` | Edit the file in nano |
| `d name` | Delete a file or folder (asks y/n first) |
| `o name` | Open a folder |
| `o ..` | Go back to the parent folder |
| `n name` | Create a new file |
| `m name` | Create a new folder |
| `r old new` | Rename a file or folder |
| `c name dest` | Copy to a destination |
| `v name dest` | Move to a destination |
| `x name` | Preview the first 40 lines of a file |
| `i name` | Show info: type, path, size, permissions, modified time |
| `q` | Quit |

---

## ⚙️ Options

| Option | What it does |
|--------|--------------|
| `-h`, `--help` | Show the help message |
| `-s`, `--search SEARCH` | Show only names containing this text |
| `-d`, `--folders` | Show only folders |
| `-H`, `--hidden` | Show only hidden files and folders |
| `-l`, `--list` | Only show the list and exit (no functions) |

---

## 📦 Requirements

- Python 3
- nano (optional, used by the edit function)

If nano is not found, the script falls back to Notepad on Windows, or to your `EDITOR`, vim or vi on other systems.

---

## ⚙️ Installation

### 📱 Termux

```bash
pkg install python nano
```

### 🐧 Debian / Ubuntu

```bash
sudo apt install python3 nano
```

---

## 🚀 Usage

```bash
python listmgr.py
```

Examples:

```bash
python listmgr.py              # list + functions panel
python listmgr.py -l           # only the list, no functions
python listmgr.py -s mp4       # names containing 'mp4'
python listmgr.py -d           # only folders
python listmgr.py -H           # only hidden files and folders
python listmgr.py -d -H        # only hidden folders
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
