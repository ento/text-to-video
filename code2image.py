import sys
import typing as t
from pathlib import Path

from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import get_lexer_for_filename
from pygments.styles import get_style_by_name


def get_font_size(filename: Path) -> t.Optional[int]:
    parts = filename.stem.split("_")
    if not parts:
        return None
    try:
        return int(parts[-1], 10)
    except ValueError:
        return None


def main(input_path: Path, output_path: Path):
    code = input_path.read_text()
    lexer = get_lexer_for_filename(input_path)
    formatter_args = dict(line_numbers=False)
    font_size = get_font_size(input_path) or 16
    if font_size:
        formatter_args["font_size"] = font_size
    if input_path.suffix == ".md":
        formatter_args["line_pad"] = 3
    if input_path.suffix == ".md" and input_path.stem.endswith("_emoji"):
        formatter_args["font_size"] = 109
        formatter_args["font_name"] = "Noto Color Emoji"
    formatter_args["style"] = get_style_by_name("github-dark")
    output = highlight(code, lexer, ImageFormatter(**formatter_args))
    output_path.write_bytes(output)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
