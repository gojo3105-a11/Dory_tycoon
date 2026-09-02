using System.IO;
using UnityEditor;
using UnityEngine;

namespace GameFactory.Editor
{
    /// <summary>
    /// Generates the panel/card/pill sprites the casual UI is built from, plus
    /// the sky gradient behind the level.
    ///
    /// WHY GENERATED AND NOT LICENSED. The approved pack (kenney-ui-pack) is a
    /// button and checkbox pack - its INVENTORY has no panel, card or ribbon
    /// sprite at all, so there is nothing to map. These are flat rounded
    /// rectangles in the palette the design settled on, which is a shape a
    /// generator produces exactly and a stock asset only approximates.
    ///
    /// All three panels are 9-sliced with the same border, so one Image can be
    /// a 640px-wide game-over card or a 76px-tall coin pill and keep the same
    /// outline thickness at both sizes.
    /// </summary>
    public static class UiSpriteGenerator
    {
        public const string UiFolder = "Assets/Common/Art/UI";

        public const string CreamPanelPath = UiFolder + "/panel_cream.png";
        public const string GoldPanelPath = UiFolder + "/panel_gold.png";
        public const string DimPanelPath = UiFolder + "/panel_dim.png";
        public const string SkyPath = UiFolder + "/sky.png";

        // 96px square with a 40px corner radius, sliced at 44. Two 44px borders
        // leave an 8px stretchable middle, which is the smallest Unity will
        // accept without complaining and all a flat fill needs.
        private const int PanelSize = 96;
        private const float CornerRadius = 40f;
        private const float OutlineWidth = 7f;
        private const float PanelBorder = 44f;

        // PPU 100 matches the Canvas reference, so a 44px border draws as 44
        // canvas units - i.e. the outline keeps the thickness it was drawn at.
        private const float UiPixelsPerUnit = 100f;

        // The palette the casual direction settled on.
        private static readonly Color Ink = new Color32(0x5B, 0x3A, 0x22, 0xFF);
        private static readonly Color Cream = new Color32(0xFF, 0xF6, 0xE4, 0xFF);
        private static readonly Color Gold = new Color32(0xFF, 0xC5, 0x31, 0xFF);
        private static readonly Color DimFill = new Color32(0xEF, 0xE6, 0xD3, 0xFF);
        private static readonly Color DimInk = new Color32(0x9A, 0x8A, 0x72, 0xFF);

        private static readonly Color SkyTop = new Color32(0x6F, 0xCB, 0xF2, 0xFF);
        private static readonly Color SkyMid = new Color32(0xA8, 0xE4, 0xFA, 0xFF);
        private static readonly Color SkyBottom = new Color32(0xD9, 0xF3, 0xE4, 0xFF);

        [MenuItem("Game Factory/UI/Regenerate UI Sprites")]
        public static void RegenerateMenuItem()
        {
            Generate();
            Debug.Log($"[UiSpriteGenerator] Wrote panel and sky sprites to {UiFolder}");
        }

        /// <summary>Generates anything that is missing. Safe to call from the pipeline.</summary>
        public static void EnsureSprites()
        {
            if (AssetDatabase.LoadAssetAtPath<Sprite>(CreamPanelPath) != null &&
                AssetDatabase.LoadAssetAtPath<Sprite>(GoldPanelPath) != null &&
                AssetDatabase.LoadAssetAtPath<Sprite>(DimPanelPath) != null &&
                AssetDatabase.LoadAssetAtPath<Sprite>(SkyPath) != null)
            {
                return;
            }

            Generate();
        }

        public static void Generate()
        {
            Directory.CreateDirectory(EditorPaths.ToAbsolutePath(UiFolder));

            WritePanel(CreamPanelPath, Cream, Ink);
            WritePanel(GoldPanelPath, Gold, Ink);
            WritePanel(DimPanelPath, DimFill, DimInk);
            WriteSky();

            AssetDatabase.Refresh();
        }

        private static void WritePanel(string path, Color fill, Color outline)
        {
            Texture2D texture = new Texture2D(PanelSize, PanelSize, TextureFormat.RGBA32, false);
            Color[] pixels = new Color[PanelSize * PanelSize];

            float half = PanelSize * 0.5f;

            for (int py = 0; py < PanelSize; py++)
            {
                for (int px = 0; px < PanelSize; px++)
                {
                    // Distance to the rounded-rectangle edge: negative inside,
                    // positive outside. One expression gives both the silhouette
                    // and the outline band, so the two can never disagree.
                    float distance = RoundedBoxDistance(
                        px + 0.5f - half, py + 0.5f - half,
                        half, half, CornerRadius);

                    // A 1px falloff either side of the edge; without it the
                    // corners stair-step badly once a card is scaled up.
                    float coverage = Mathf.Clamp01(0.5f - distance);
                    if (coverage <= 0f)
                    {
                        pixels[py * PanelSize + px] = new Color(0f, 0f, 0f, 0f);
                        continue;
                    }

                    float inner = Mathf.Clamp01(0.5f - (distance + OutlineWidth));
                    Color c = Color.Lerp(outline, fill, inner);
                    c.a = coverage;
                    pixels[py * PanelSize + px] = c;
                }
            }

            texture.SetPixels(pixels);
            texture.Apply();

            File.WriteAllBytes(path, texture.EncodeToPNG());
            Object.DestroyImmediate(texture);

            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
            ApplyImportSettings(path, new Vector4(PanelBorder, PanelBorder, PanelBorder, PanelBorder));
        }

        /// <summary>
        /// Signed distance from (x, y) - measured from the box centre - to the
        /// edge of a rounded box with the given half-extents.
        /// </summary>
        private static float RoundedBoxDistance(float x, float y, float halfWidth, float halfHeight, float radius)
        {
            float qx = Mathf.Abs(x) - (halfWidth - radius);
            float qy = Mathf.Abs(y) - (halfHeight - radius);
            float outsideX = Mathf.Max(qx, 0f);
            float outsideY = Mathf.Max(qy, 0f);
            float outside = Mathf.Sqrt(outsideX * outsideX + outsideY * outsideY);
            float inside = Mathf.Min(Mathf.Max(qx, qy), 0f);
            return outside + inside - radius;
        }

        /// <summary>
        /// The sky, as a 1-pixel-wide vertical gradient. The camera's solid
        /// clear colour was a near-black #1A1A26, which is why the game read as
        /// grim next to a bright casual mock-up. Narrow because it is stretched
        /// across the frustum anyway - only the vertical ramp carries any detail.
        /// </summary>
        private static void WriteSky()
        {
            const int height = 256;
            Texture2D texture = new Texture2D(1, height, TextureFormat.RGBA32, false);
            Color[] pixels = new Color[height];

            for (int py = 0; py < height; py++)
            {
                // y runs 0 at the bottom of the texture to 1 at the top, so the
                // stops are written top-down and read against (1 - t).
                float t = 1f - (py + 0.5f) / height;
                pixels[py] = t < 0.44f
                    ? Color.Lerp(SkyTop, SkyMid, t / 0.44f)
                    : Color.Lerp(SkyMid, SkyBottom, (t - 0.44f) / 0.56f);
            }

            texture.SetPixels(pixels);
            texture.Apply();

            File.WriteAllBytes(SkyPath, texture.EncodeToPNG());
            Object.DestroyImmediate(texture);

            AssetDatabase.ImportAsset(SkyPath, ImportAssetOptions.ForceUpdate);
            ApplyImportSettings(SkyPath, Vector4.zero);
        }

        /// <summary>
        /// Set explicitly rather than left to SharedArtImporter: that
        /// postprocessor only stamps an asset whose import settings are
        /// missing, so a regenerated file would silently keep whatever border
        /// it had before - and the border here is derived from the radius this
        /// generator drew, not guessed per file.
        /// </summary>
        private static void ApplyImportSettings(string path, Vector4 border)
        {
            TextureImporter importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null) return;

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = UiPixelsPerUnit;
            // Bilinear, not Point: these are smooth anti-aliased curves, and
            // point sampling would throw the anti-aliasing away the moment a
            // panel is drawn at anything other than 1:1.
            importer.filterMode = FilterMode.Bilinear;
            importer.mipmapEnabled = false;
            importer.alphaIsTransparency = true;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.wrapMode = TextureWrapMode.Clamp;

            TextureImporterSettings settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;
            settings.spriteAlignment = (int)SpriteAlignment.Center;
            importer.SetTextureSettings(settings);

            importer.spriteBorder = border;
            importer.SaveAndReimport();
        }
    }
}
