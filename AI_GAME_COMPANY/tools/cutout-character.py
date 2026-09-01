"""Cut a character out of a reference image and size it for the game.

    python AI_GAME_COMPANY/tools/cutout-character.py \
        --source Assets/Common/Character/SourceImage/KakaoTalk_..._09.png \
        --target Assets/Common/Art/Runner/player.png

Master prompt sections 8, 9 and 26. This is the honest answer to "there is no
GPU here": the references already contain a finished 도리, so nothing needs to
be generated - it needs to be SEPARATED from its background. That is a small
segmentation model on the CPU, about a second per image, rather than a
diffusion model that wants VRAM this machine does not have.

Licences, both permissive and both recorded in LICENSE_REGISTRY.json:
    rembg  MIT
    u2net  Apache 2.0 (the weights, downloaded on first run to ~/.u2net)

Two details that are easy to get wrong and visible when you do:

  PREMULTIPLIED RESIZE. Resizing RGBA directly makes the filter average colour
  across fully transparent pixels, whose RGB is undefined, dragging it into the
  edge as a dark halo. Multiplying by alpha first and dividing after keeps the
  outline clean.

  TRIM BEFORE SCALING. The subject occupies a fraction of the frame, so scaling
  the whole image to the target height would leave the character tiny inside a
  mostly empty sprite - and a collider sized from that sprite would be far too
  big.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_HEIGHT = 192
ALPHA_FLOOR = 0.003


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="reference image to cut out")
    parser.add_argument("--target", required=True, help="where to write the RGBA PNG")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT,
                        help=f"output height in pixels (default {DEFAULT_HEIGHT}; "
                             "at PPU 128 that is 1.5 world units)")
    parser.add_argument("--model", default="u2net",
                        help="rembg model name (default u2net)")
    parser.add_argument("--keep-margin", type=float, default=0.0,
                        help="fraction of the trimmed size to keep as transparent "
                             "margin, e.g. 0.04 for a little breathing room")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        import numpy as np
        from PIL import Image
        from rembg import new_session, remove
    except ImportError as exc:
        print(f"ERROR: missing dependency ({exc}).")
        print("  pip install \"rembg[cpu]\" onnxruntime pillow numpy")
        print("  Both are free; section 43 permits installing free tools.")
        return 2

    source = Path(args.source)
    if not source.is_file():
        print(f"ERROR: {source} not found.")
        return 2

    session = new_session(args.model)
    cut = remove(source.read_bytes(), session=session)

    import io
    image = Image.open(io.BytesIO(cut)).convert("RGBA")

    # Trim to the subject. getbbox() uses the alpha channel here, which is
    # exactly the mask the model produced.
    box = image.getbbox()
    if box is None:
        print("ERROR: the model found no subject - nothing is opaque.")
        return 1
    image = image.crop(box)

    if args.keep_margin > 0:
        pad_x = round(image.width * args.keep_margin)
        pad_y = round(image.height * args.keep_margin)
        padded = Image.new("RGBA", (image.width + pad_x * 2, image.height + pad_y * 2),
                           (0, 0, 0, 0))
        padded.paste(image, (pad_x, pad_y))
        image = padded

    # Premultiply, resize, unpremultiply.
    array = np.asarray(image).astype(np.float32)
    alpha = array[..., 3:4] / 255.0
    array[..., :3] *= alpha
    premultiplied = Image.fromarray(array.astype("uint8"), "RGBA")

    width = max(1, round(image.width * args.height / image.height))
    small = premultiplied.resize((width, args.height), Image.LANCZOS)

    out = np.asarray(small).astype(np.float32)
    out_alpha = out[..., 3:4] / 255.0
    np.divide(out[..., :3], out_alpha, out=out[..., :3], where=out_alpha > ALPHA_FLOOR)
    np.clip(out, 0, 255, out=out)

    target = Path(args.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out.astype("uint8"), "RGBA").save(target)

    print(f"{source.name}: subject {box[2]-box[0]}x{box[3]-box[1]} "
          f"-> {width}x{args.height}")
    print(f"Wrote {target}")
    print(f"  At PPU 128 that is {width/128:.2f} x {args.height/128:.2f} world units.")
    print("  SharedArtImporter sets PPU and filtering; PrefabGenerator sizes the")
    print("  collider from the sprite, so no code change is needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
