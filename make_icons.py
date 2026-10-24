from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
src = Image.open(HERE / "mylogo.png").convert("RGBA")
side = min(src.size)
src = src.crop(((src.width - side) // 2, (src.height - side) // 2, (src.width + side) // 2, (src.height + side) // 2))
BG = (31, 58, 95)

def plain(size):
    return src.resize((size, size), Image.LANCZOS)

def padded(size, share):
    canvas = Image.new("RGB", (size, size), BG)
    inner = int(size * share)
    logo = src.resize((inner, inner), Image.LANCZOS)
    canvas.paste(logo, ((size - inner) // 2, (size - inner) // 2), logo)
    return canvas

out = HERE / "frontend"
plain(192).save(out / "icon-192.png")
plain(512).save(out / "icon-512.png")
padded(512, 0.62).save(out / "icon-maskable-512.png")
padded(180, 0.80).save(out / "apple-touch-icon.png")
print("Icons replaced in frontend")
