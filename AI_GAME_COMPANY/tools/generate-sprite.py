"""Generate character sprites with a local, free, CPU-only diffusion model.

    # new pose from scratch, consistent across frames via a fixed seed
    python AI_GAME_COMPANY/tools/generate-sprite.py txt2img \
        --pose "running to the right, side view, legs mid-stride" \
        --out /tmp/dori/run_a.png

    # re-pose an existing sprite, which keeps identity far better
    python AI_GAME_COMPANY/tools/generate-sprite.py img2img \
        --init Assets/Common/Art/Runner/player.png \
        --pose "side view, facing right, running" --strength 0.6 \
        --out /tmp/dori/run_b.png

Master prompt sections 4, 8 and 9. Local only, no API, no account, no cost.

WHAT THIS CAN AND CANNOT DO - read before trusting the output.

  It CANNOT reproduce 도리 from the reference renders. A base model has never
  seen this character. txt2img gives *a* hedgehog matching the description,
  not *the* one. That is why --seed exists and defaults to a fixed value:
  frames generated with the same seed and prompt skeleton are consistent with
  EACH OTHER, which is what animation actually needs, even when they differ
  from the marketing render.

  img2img keeps identity much better because it starts from the real sprite,
  but strength is a hard trade: below ~0.5 the pose barely changes, above
  ~0.75 the character stops being 도리. Rotating a front view into a true side
  profile is a large structural change, and img2img alone often will not
  manage it. Expect to run several seeds and throw most away.

  On 4 CPU cores a 512x512 image at 30 steps takes minutes, not seconds.

Section 30 still applies: whether a generated frame is good is a human call.
This tool writes files; it does not decide they are usable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# CreativeML OpenRAIL-M, which permits commercial use with use-based
# restrictions. Registered in LICENSE_REGISTRY.json - section 8 wants the
# weights checked separately from the code that runs them.
DEFAULT_MODEL = "stable-diffusion-v1-5/stable-diffusion-v1-5"

# Fixed by default, because reproducibility is the point: the same seed with
# the same prompt skeleton is what makes a set of frames belong together.
DEFAULT_SEED = 20260902

CHARACTER = (
    "a chubby cute cartoon hedgehog character, cream coloured face and belly, "
    "brown auburn spiky quills, reddish brown hair tuft on top of the head, "
    "small rounded ears, large friendly brown eyes, small black nose, "
    "navy blue bow tie, 3d rendered mascot style, soft lighting"
)

SPRITE_STYLE = (
    "full body, centred, plain flat white background, no shadow, no text, "
    "no watermark, game sprite"
)

NEGATIVE = (
    "text, watermark, signature, logo, multiple characters, cropped, "
    "cut off, out of frame, blurry, low quality, deformed, extra limbs, "
    "busy background, scenery, furniture, glasses"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["txt2img", "img2img"])
    parser.add_argument("--pose", required=True,
                        help='the pose to draw, e.g. "running to the right, side view"')
    parser.add_argument("--out", required=True, help="output PNG path")
    parser.add_argument("--init", help="img2img only: the sprite to start from")
    parser.add_argument("--strength", type=float, default=0.6,
                        help="img2img only, 0-1. Below 0.5 barely moves; above "
                             "0.75 stops being the same character (default 0.6)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--guidance", type=float, default=8.0)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--count", type=int, default=1,
                        help="how many variations to write; each gets seed+i and "
                             "an -N suffix, so one run can produce a spread to pick from")
    return parser


def prompt_for(pose: str) -> str:
    return f"{CHARACTER}, {pose}, {SPRITE_STYLE}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        import torch
        from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline
    except ImportError as exc:
        print(f"ERROR: missing dependency ({exc}).")
        print("  pip install torch --index-url https://download.pytorch.org/whl/cpu")
        print("  pip install diffusers transformers accelerate safetensors")
        print("  All free and local; section 43 permits installing free tools.")
        return 2

    if args.mode == "img2img" and not args.init:
        print("ERROR: img2img needs --init.")
        return 2

    torch.set_num_threads(max(1, torch.get_num_threads()))
    prompt = prompt_for(args.pose)
    print(f"model  : {args.model}")
    print(f"prompt : {prompt}")
    print(f"seed   : {args.seed}  steps: {args.steps}  guidance: {args.guidance}")

    common = dict(torch_dtype=torch.float32, safety_checker=None,
                  requires_safety_checker=False)

    if args.mode == "txt2img":
        pipe = StableDiffusionPipeline.from_pretrained(args.model, **common)
    else:
        pipe = StableDiffusionImg2ImgPipeline.from_pretrained(args.model, **common)
    pipe = pipe.to("cpu")
    pipe.set_progress_bar_config(disable=None)

    init_image = None
    if args.mode == "img2img":
        from PIL import Image
        raw = Image.open(args.init).convert("RGBA")
        # Flatten onto white: the model has no alpha channel, and compositing
        # onto black would darken every edge pixel of the character.
        flat = Image.new("RGB", raw.size, (255, 255, 255))
        flat.paste(raw, mask=raw.split()[3])
        init_image = flat.resize((args.size, args.size), Image.LANCZOS)
        print(f"init   : {args.init}  strength: {args.strength}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    for index in range(args.count):
        seed = args.seed + index
        generator = torch.Generator(device="cpu").manual_seed(seed)

        if args.mode == "txt2img":
            result = pipe(prompt, negative_prompt=NEGATIVE,
                          num_inference_steps=args.steps,
                          guidance_scale=args.guidance,
                          height=args.size, width=args.size,
                          generator=generator)
        else:
            result = pipe(prompt=prompt, image=init_image,
                          negative_prompt=NEGATIVE,
                          strength=args.strength,
                          num_inference_steps=args.steps,
                          guidance_scale=args.guidance,
                          generator=generator)

        target = out_path if args.count == 1 else \
            out_path.with_name(f"{out_path.stem}-{index + 1}{out_path.suffix}")
        result.images[0].save(target)
        print(f"wrote {target}  (seed {seed})")

    print()
    print("These are RAW generations on a plain background - not sprites yet.")
    print("Run cutout-character.py on the ones worth keeping to remove the")
    print("background and size them for the game. Section 30: whether any of")
    print("them is actually good is a human call, not this tool's.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
