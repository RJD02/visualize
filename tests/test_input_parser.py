from pathlib import Path

from src.input_parser import parse_files


def test_parse_files_text(tmp_path: Path):
    file_path = tmp_path / "a.py"
    file_path.write_text("class A: pass", encoding="utf-8")
    result = parse_files([str(file_path)])
    assert "class A" in result
