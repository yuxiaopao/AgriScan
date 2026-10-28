"""Package generated crop sprite strips; never draws or synthesizes character art.

Uses the same connected-component extraction as build-mascot.py, at 2x display
resolution. Keeps originals and an explicit report of any source-edge repairs.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from build_mascot_support import module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-dir", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = root / "design/xiaohe-crops"
    public = root / "frontend/public/images/xiaohe-crops"
    public.mkdir(parents=True, exist_ok=True)
    extract = module("crop_extract", args.skill_dir / "scripts/extract_strip_frames.py")
    manifest = json.loads((work / "prompts.json").read_text(encoding="utf-8"))
    reports = []
    contact = Image.new("RGB", (5 * 216, 4 * 252), "#f7f7f0")
    draw = ImageDraw.Draw(contact)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = ImageFont.truetype(str(font_path), 17) if font_path.exists() else ImageFont.load_default()
    for row, crop in enumerate(manifest["crops"]):
        key = crop["id"]
        source = Image.open(work / "source" / (key + ".png")).convert("RGBA")
        # Transparent generation fringes can join adjacent figures. Segment only
        # the opaque character cores; copy original RGBA pixels, never redraw.
        groups = None
        for alpha_threshold in (128, 160, 192, 224):
            segmentation = source.copy()
            segmentation.putalpha(source.getchannel("A").point(lambda p: 255 if p > alpha_threshold else 0))
            candidate = extract.component_frame_groups(segmentation, 8)
            if not candidate:
                continue
            candidate_areas = [sum(c["area"] for c in group) for group in candidate]
            median_area = sorted(candidate_areas)[4]
            if all(median_area * .7 < area < median_area * 1.3 for area in candidate_areas):
                groups = candidate
                break
        if not groups or len(groups) != 8:
            raise ValueError(key + ": expected eight separated characters")
        bounds = [extract.component_bounds(group) for group in groups]
        areas = [sum(c["area"] for c in group) for group in groups]
        middle = sorted(areas)[4]
        if any(area < middle * .7 or area > middle * 1.3 for area in areas):
            raise ValueError(key + ": merged or partial character detected " + str(areas))
        valid = [i for i, box in enumerate(bounds) if box[0] > 0 and box[2] < source.width and box[1] > 0 and box[3] < source.height]
        if len(valid) < 6:
            raise ValueError(key + ": too many clipped source poses")
        repaired = []
        for i in range(8):
            if i not in valid:
                replacement = 0 if i == 7 and 0 in valid else min(valid, key=lambda j: abs(i-j))
                groups[i] = groups[replacement]
                repaired.append({"frame": i, "source_frame": replacement, "reason": "source touches canvas edge"})
        bounds = [extract.component_bounds(group) for group in groups]
        top = min(box[1] for box in bounds) - 4
        bottom = max(box[3] for box in bounds) + 4
        width = max(box[2] - box[0] for box in bounds) + 8
        height = bottom - top
        scale = min(352 / width, 384 / height)
        frames = []
        folder = work / "frames" / key
        folder.mkdir(parents=True, exist_ok=True)
        for i, (group, box) in enumerate(zip(groups, bounds)):
            pixels = extract.component_group_image(source, group, padding=4)
            viewport = Image.new("RGBA", (width, height))
            viewport.alpha_composite(pixels, ((width - pixels.width)//2, max(0, box[1]-4)-top))
            resized = viewport.resize((round(width*scale), round(height*scale)), Image.Resampling.LANCZOS)
            frame = Image.new("RGBA", (384, 416))
            frame.alpha_composite(resized, ((384-resized.width)//2, (416-resized.height)//2))
            box_final = frame.getchannel("A").point(lambda p: 255 if p > 16 else 0).getbbox()
            assert box_final and box_final[0] >= 8 and box_final[1] >= 8 and box_final[2] <= 376 and box_final[3] <= 408, (key, i, box_final)
            frame.save(folder / f"{i:02d}.png")
            frames.append(frame)
        strip = Image.new("RGBA", (3072, 416))
        for i, frame in enumerate(frames):
            strip.alpha_composite(frame, (384*i, 0))
        strip.save(public / (key + ".webp"), quality=88, method=6, exact=True)
        frames[0].save(public / (key + "-still.webp"), quality=88, method=6, exact=True)
        thumb = frames[0].resize((192,208), Image.Resampling.LANCZOS)
        x, y = (row % 5)*216+12, (row//5)*252+7
        contact.paste(thumb,(x,y),thumb)
        draw.text((x+12,y+214),crop["crop"],font=font,fill="#334b37")
        reports.append({"id":key,"crop":crop["crop"],"frames":8,"unique_frames":len({frame.tobytes() for frame in frames}),"source_adjustments":repaired,"segmentation_alpha_threshold":alpha_threshold,"bytes":(public/(key+".webp")).stat().st_size})
        print(json.dumps(reports[-1],ensure_ascii=False),flush=True)
    contact.save(work / "contact-sheet.jpg",quality=92)
    (work/"frame-review.json").write_text(json.dumps({"ok":True,"cell":[384,416],"crops":reports,"total_animation_bytes":sum(r["bytes"] for r in reports)},ensure_ascii=False,indent=2),encoding="utf-8")

if __name__ == "__main__":
    main()
