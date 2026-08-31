from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    assert "%LOCALAPPDATA%\\wing\\omnis-wing\\venv\\Scripts" in doc
    assert "Get-Command wing        # should print C:\\Users\\<you>\\AppData\\Local\\wing\\omnis-wing\\venv\\Scripts\\wing.exe" in doc
    assert '$wingBin = "$InstallDir\\venv\\Scripts"' in install
