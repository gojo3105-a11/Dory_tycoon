using System.IO;
using UnityEditor;
using UnityEngine;

namespace GameFactory.Editor
{
    /// <summary>
    /// Draws 도리 as a 2D sprite, from the reference images in
    /// Assets/Common/Character/SourceImage/.
    ///
    /// WHY THIS EXISTS. The references are rendered photos of the character on
    /// a detailed office background. Turning one into a game sprite needs
    /// segmentation - and this machine has no GPU, no image generation and no
    /// image library, which is why `orchestrator doctor` reports
    /// local_image_generation and image_to_3d as NOT_VIABLE. So the sprite is
    /// constructed from shapes matched to the reference instead: cream body,
    /// brown spike shell, auburn hair tuft, navy bow tie.
    ///
    /// This is deliberately a stand-in, not a claim to have reproduced the
    /// render. It is recognisably 도리 and it is centred on its own origin,
    /// which is what the gameplay needs; the fur texture and the detailed
    /// expression of the reference are not reproduced. The moment a cut-out PNG
    /// is dropped at Assets/Common/Art/Runner/player.png, PrefabGenerator
    /// prefers that and this file is ignored - no code change.
    ///
    /// Front-facing, matching the reference pose. A side view would read better
    /// in a runner, but inventing a profile the user has never seen would be
    /// guessing at their character rather than following it.
    /// </summary>
    public static class DoriSpriteGenerator
    {
        public const string GeneratedFolder = "Assets/Common/Character/Generated";
        public const string SpritePath = GeneratedFolder + "/Dori.png";

        // 80x96 at PPU 64 is 1.25 x 1.5 world units: a little wider than the
        // 1.09-unit ground tile and half again as tall, which matches how
        // stout the character is in the reference.
        private const int Width = 80;
        private const int Height = 96;
        private const float PixelsPerUnit = 64f;

        // Sampled from the reference render.
        private static readonly Color Cream = new Color32(0xF7, 0xE9, 0xD8, 0xFF);
        private static readonly Color CreamShade = new Color32(0xE4, 0xCE, 0xB6, 0xFF);
        private static readonly Color Spike = new Color32(0x8A, 0x5A, 0x36, 0xFF);
        private static readonly Color SpikeDark = new Color32(0x5E, 0x3B, 0x22, 0xFF);
        private static readonly Color Hair = new Color32(0xA8, 0x54, 0x28, 0xFF);
        private static readonly Color Navy = new Color32(0x2B, 0x3C, 0x6B, 0xFF);
        private static readonly Color Eye = new Color32(0x3A, 0x24, 0x14, 0xFF);
        private static readonly Color Ink = new Color32(0x25, 0x18, 0x0E, 0xFF);
        private static readonly Color Tongue = new Color32(0xD8, 0x6E, 0x7A, 0xFF);
        private static readonly Color Clear = new Color(0f, 0f, 0f, 0f);

        [MenuItem("Game Factory/Character/Regenerate Dori Sprite")]
        public static void RegenerateMenuItem()
        {
            string path = Generate();
            Debug.Log($"[DoriSpriteGenerator] Wrote {path}");
        }

        /// <summary>Generates the sprite only if it is missing. Safe to call from the pipeline.</summary>
        public static Sprite EnsureSprite()
        {
            Sprite existing = AssetDatabase.LoadAssetAtPath<Sprite>(SpritePath);
            if (existing != null) return existing;

            Generate();
            return AssetDatabase.LoadAssetAtPath<Sprite>(SpritePath);
        }

        public static string Generate()
        {
            Directory.CreateDirectory(GeneratedFolder);

            Texture2D texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            Color[] pixels = new Color[Width * Height];
            for (int i = 0; i < pixels.Length; i++) pixels[i] = Clear;

            // Normalised coordinates: x 0..1 left to right, y 0..1 feet to head.
            for (int py = 0; py < Height; py++)
            {
                for (int px = 0; px < Width; px++)
                {
                    float x = (px + 0.5f) / Width;
                    float y = (py + 0.5f) / Height;
                    Color c = SampleCharacter(x, y);
                    if (c.a > 0f) pixels[py * Width + px] = c;
                }
            }

            texture.SetPixels(pixels);
            texture.Apply();

            File.WriteAllBytes(SpritePath, texture.EncodeToPNG());
            Object.DestroyImmediate(texture);

            AssetDatabase.ImportAsset(SpritePath, ImportAssetOptions.ForceUpdate);
            ApplyImportSettings();
            return SpritePath;
        }

        /// <summary>
        /// Painter's order: spike shell, then the cream front, then the face.
        /// Later tests win, so each one only has to describe its own shape.
        /// </summary>
        private static Color SampleCharacter(float x, float y)
        {
            Color result = Clear;

            // --- feet: two small pads the body sits on ---
            if (InEllipse(x, y, 0.37f, 0.055f, 0.10f, 0.05f) ||
                InEllipse(x, y, 0.63f, 0.055f, 0.10f, 0.05f))
            {
                result = Cream;
            }

            // --- spike shell: an ellipse whose radius is modulated by a
            //     sawtooth in angle, which is what makes the quills ---
            float shellDx = (x - 0.5f) / 0.46f;
            float shellDy = (y - 0.47f) / 0.44f;
            float shellR = Mathf.Sqrt(shellDx * shellDx + shellDy * shellDy);
            float angle = Mathf.Atan2(shellDy, shellDx);
            // 22 quills around the shell; 0.09 amplitude keeps them read as
            // spikes rather than noise at this resolution.
            float quill = 1f - 0.09f * Mathf.Abs(Mathf.Sin(angle * 11f));
            if (shellR <= quill)
            {
                result = shellR > quill - 0.16f ? SpikeDark : Spike;
            }

            // --- arms: small cream paws at the sides ---
            if (InEllipse(x, y, 0.20f, 0.34f, 0.075f, 0.10f) ||
                InEllipse(x, y, 0.80f, 0.34f, 0.075f, 0.10f))
            {
                result = Cream;
            }

            // --- cream front (belly and face are one continuous shape) ---
            if (InEllipse(x, y, 0.5f, 0.44f, 0.335f, 0.375f))
            {
                // A soft shade along the bottom edge gives the belly volume
                // without needing a gradient.
                bool lower = y < 0.24f && !InEllipse(x, y, 0.5f, 0.46f, 0.30f, 0.34f);
                result = lower ? CreamShade : Cream;
            }

            // --- ears ---
            if (InEllipse(x, y, 0.29f, 0.70f, 0.065f, 0.055f) ||
                InEllipse(x, y, 0.71f, 0.70f, 0.065f, 0.055f))
            {
                result = Spike;
            }

            // --- hair tuft: three quills leaning left, as in the reference ---
            if (InTriangle(x, y, 0.44f, 0.74f, 0.52f, 0.74f, 0.40f, 0.95f) ||
                InTriangle(x, y, 0.50f, 0.74f, 0.58f, 0.74f, 0.50f, 0.97f) ||
                InTriangle(x, y, 0.56f, 0.74f, 0.64f, 0.74f, 0.63f, 0.92f))
            {
                result = Hair;
            }

            // --- eyes: large, with a highlight, which is most of the charm ---
            if (InEllipse(x, y, 0.385f, 0.615f, 0.075f, 0.085f) ||
                InEllipse(x, y, 0.615f, 0.615f, 0.075f, 0.085f))
            {
                result = Eye;
                if (InEllipse(x, y, 0.365f, 0.645f, 0.028f, 0.030f) ||
                    InEllipse(x, y, 0.595f, 0.645f, 0.028f, 0.030f))
                {
                    result = Color.white;
                }
            }

            // --- nose ---
            if (InEllipse(x, y, 0.5f, 0.545f, 0.040f, 0.030f)) result = Ink;

            // --- open smile ---
            if (InEllipse(x, y, 0.5f, 0.485f, 0.075f, 0.048f) && y < 0.505f)
            {
                result = Ink;
                if (InEllipse(x, y, 0.5f, 0.470f, 0.048f, 0.026f)) result = Tongue;
            }

            // --- bow tie: two wings and a knot ---
            if (InTriangle(x, y, 0.50f, 0.395f, 0.50f, 0.365f, 0.36f, 0.345f) ||
                InTriangle(x, y, 0.50f, 0.395f, 0.36f, 0.345f, 0.36f, 0.415f) ||
                InTriangle(x, y, 0.50f, 0.395f, 0.50f, 0.365f, 0.64f, 0.345f) ||
                InTriangle(x, y, 0.50f, 0.395f, 0.64f, 0.345f, 0.64f, 0.415f) ||
                InEllipse(x, y, 0.50f, 0.380f, 0.035f, 0.030f))
            {
                result = Navy;
            }

            return result;
        }

        private static bool InEllipse(float x, float y, float cx, float cy, float rx, float ry)
        {
            float dx = (x - cx) / rx;
            float dy = (y - cy) / ry;
            return dx * dx + dy * dy <= 1f;
        }

        private static bool InTriangle(float px, float py,
            float ax, float ay, float bx, float by, float cx, float cy)
        {
            float d1 = Sign(px, py, ax, ay, bx, by);
            float d2 = Sign(px, py, bx, by, cx, cy);
            float d3 = Sign(px, py, cx, cy, ax, ay);
            bool hasNeg = d1 < 0f || d2 < 0f || d3 < 0f;
            bool hasPos = d1 > 0f || d2 > 0f || d3 > 0f;
            return !(hasNeg && hasPos);
        }

        private static float Sign(float px, float py, float ax, float ay, float bx, float by)
        {
            return (px - bx) * (ay - by) - (ax - bx) * (py - by);
        }

        /// <summary>
        /// Set explicitly rather than left to SharedArtImporter: this file lives
        /// under Assets/Common/Character/, not Assets/Common/Art/, so that
        /// postprocessor does not cover it.
        /// </summary>
        private static void ApplyImportSettings()
        {
            TextureImporter importer = AssetImporter.GetAtPath(SpritePath) as TextureImporter;
            if (importer == null) return;

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = PixelsPerUnit;
            importer.filterMode = FilterMode.Point;
            importer.mipmapEnabled = false;
            importer.alphaIsTransparency = true;
            importer.textureCompression = TextureImporterCompression.Uncompressed;

            TextureImporterSettings settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;
            settings.spriteAlignment = (int)SpriteAlignment.Center;
            importer.SetTextureSettings(settings);

            importer.SaveAndReimport();
        }
    }
}
