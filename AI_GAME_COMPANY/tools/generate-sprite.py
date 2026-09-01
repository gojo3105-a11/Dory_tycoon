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

    # BEST for a new pose that is still the same character: IP-Adapter, which
    # conditions on the reference PICTURE rather than only on words
    python AI_GAME_COMPANY/tools/generate-sprite.py txt2img \
        --ip-image Assets/Common/Art/Runner/player.png --ip-scale 0.7 \
        --pose "side view profile, facing right, running, legs mid-stride" \
        --out /tmp/dori/run_c.png --count 4

Master prompt sections 4, 8 and 9. Local only, no API, no account, no cost.

WHAT THIS CAN AND CANNOT DO - read before trusting the output.

  A base model has never seen 도리, so plain txt2img gives *a* hedgehog
  matching the description, not *the* one. Three ways out, in increasing order
  of how well they hold identity:

    --seed alone. Frames sharing a seed are consistent with EACH OTHER, which
    is what animation needs, even when they all differ from the reference.

    img2img. Starts from the real sprite, so identity survives - but strength
    is a hard trade. Below ~0.5 the pose barely changes; above ~0.75 it stops
    being 도리. Rotating a front view into a true side profile is a large
    structural change that img2img alone often will not manage.

    --ip-image (IP-Adapter). The model looks at the reference while it draws,
    so the pose is free while the character is constrained. This is the one
    worth reaching for first. --ip-scale is its own trade: high keeps identity
    but resists the new pose, low frees the pose and drifts off-character.
    Sweep it rather than guessing.

  MEMORY. The IP-Adapter stack adds a 632M OpenCLIP-ViT-H image encoder, so at
  float32 it is about 7.8 GB - past the ~5.9 GB budget on a 16 GB CPU-only
  machine, where it swaps instead of running. bfloat16 halves that to about
  4.0 GB and is the default here for exactly that reason;
  HardwareProfile.image_model_fit("sd-1.5-ipadapter") reports both.

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

# IP-Adapter (Apache-2.0). The "plus" variant conditions on PATCH embeddings
# from OpenCLIP-ViT-H rather than a single global embedding, so the output
# stays much closer to the reference - which is the whole point here. Plain
# txt2img has never seen 도리; with this it is looking at 도리 while it draws.
IP_ADAPTER_REPO = "h94/IP-Adapter"
IP_ADAPTER_SUBFOLDER = "models"
IP_ADAPTER_WEIGHT = "ip-adapter-plus_sd15.bin"

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
    parser.add_argument("--ip-image",
                        help="reference image for IP-Adapter. The model has never seen "
                             "this character; with this it conditions on the picture, "
                             "which is what keeps the output recognisably the same one")
    parser.add_argument("--ip-scale", type=float, default=0.7,
                        help="how strongly the reference constrains the result, 0-1. "
                             "High keeps identity but resists a new pose; low frees the "
                             "pose and drifts off-character (default 0.7)")
    parser.add_argument("--dtype", choices=["bfloat16", "float32"], default="bfloat16",
                        help="bfloat16 halves the weights and is REQUIRED for the "
                             "IP-Adapter stack on a 16 GB CPU-only machine: at float32 "
                             "it is about 7.8 GB against a ~5.9 GB budget and swaps "
                             "(HardwareProfile.image_model_fit says so). float32 is "
                             "there for machines with room")
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

    dtype = torch.bfloat16 if args.dtype == "bfloat16" else torch.float32
    print(f"dtype  : {args.dtype}")
    common = dict(torch_dtype=dtype, safety_checker=None,
                  requires_safety_checker=False)

    if args.mode == "txt2img":
        pipe = StableDiffusionPipeline.from_pretrained(args.model, **common)
    else:
        pipe = StableDiffusionImg2ImgPipeline.from_pretrained(args.model, **common)
    pipe = pipe.to("cpu")
    pipe.set_progress_bar_config(disable=None)

    ip_image = None
    if args.ip_image:
        from PIL import Image as PILImage
        pipe.load_ip_adapter(IP_ADAPTER_REPO, subfolder=IP_ADAPTER_SUBFOLDER,
                             weight_name=IP_ADAPTER_WEIGHT)
        pipe.set_ip_adapter_scale(args.ip_scale)

        reference = PILImage.open(args.ip_image).convert("RGBA")
        # Flatten onto white for the same reason as the init image: the image
        # encoder has no alpha channel, and compositing onto black would tell
        # it the character is outlined in black.
        flat = PILImage.new("RGB", reference.size, (255, 255, 255))
        flat.paste(reference, mask=reference.split()[3])
        ip_image = flat
        print(f"ip     : {args.ip_image}  scale: {args.ip_scale}  ({IP_ADAPTER_WEIGHT})")

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

        extra = {"ip_adapter_image": ip_image} if ip_image is not None else {}

        if args.mode == "txt2img":
            result = pipe(prompt, negative_prompt=NEGATIVE,
                          num_inference_steps=args.steps,
                          guidance_scale=args.guidance,
                          height=args.size, width=args.size,
                          generator=generator, **extra)
        else:
            result = pipe(prompt=prompt, image=init_image,
                          negative_prompt=NEGATIVE,
                          strength=args.strength,
                          num_inference_steps=args.steps,
                          guidance_scale=args.guidance,
                          generator=generator, **extra)

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
