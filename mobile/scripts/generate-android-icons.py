"""Package the generated Xiaohe icon at Android launcher densities (Pillow required)."""

from pathlib import Path
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "android" / "app" / "src" / "main" / "res"
SOURCE = ROOT / "public" / "images" / "icon.png"
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def main() -> None:
    if not RES.is_dir():
        raise SystemExit("Generate mobile/android with npm run android:add first.")
    with Image.open(SOURCE) as source:
        icon = source.convert("RGBA")
        background = Image.new("RGBA", icon.size, icon.getpixel((0, 0)))
        background.alpha_composite(icon)
        icon = background.convert("RGB")
        for density, scale in DENSITIES.items():
            folder = RES / f"mipmap-{density}"
            folder.mkdir(parents=True, exist_ok=True)
            legacy = icon.resize((round(48 * scale), round(48 * scale)), Image.Resampling.LANCZOS)
            legacy.save(folder / "ic_launcher.png")
            legacy.save(folder / "ic_launcher_round.png")
            foreground = Image.new("RGB", (round(108 * scale), round(108 * scale)), icon.getpixel((0, 0)))
            art = icon.resize((round(76 * scale), round(76 * scale)), Image.Resampling.LANCZOS)
            offset = (foreground.width - art.width) // 2
            foreground.paste(art, (offset, offset))
            foreground.save(folder / "ic_launcher_foreground.png")

    adaptive = RES / "mipmap-anydpi-v26"
    adaptive.mkdir(parents=True, exist_ok=True)
    xml = '''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
'''
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        (adaptive / name).write_text(xml, encoding="utf-8")
    colors = RES / "values" / "ic_launcher_background.xml"
    colors.write_text('''<?xml version="1.0" encoding="utf-8"?>
<resources><color name="ic_launcher_background">#EFF4E3</color></resources>
''', encoding="utf-8")
    print("Packaged Xiaohe launcher icons for all five Android densities.")


if __name__ == "__main__":
    main()
