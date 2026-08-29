using UnityEditor;
using UnityEngine;

namespace GameFactory.Editor
{
    /// <summary>
    /// Forces consistent sprite import settings on everything dropped into
    /// Assets/Common/Art/, so licensed art packs can be added by simply
    /// copying files in - no manual Inspector work per texture.
    ///
    /// Full Rect mesh type matters specifically: SpriteRenderer.drawMode
    /// Tiled (used by the ground tile) silently refuses to tile a sprite
    /// imported with the default Tight mesh.
    /// </summary>
    public class SharedArtImporter : AssetPostprocessor
    {
        public const string SharedArtRoot = "Assets/Common/Art/";

        private void OnPreprocessTexture()
        {
            if (!assetPath.StartsWith(SharedArtRoot)) return;

            TextureImporter importer = (TextureImporter)assetImporter;

            // Only stamp defaults on first import. Re-stamping on every
            // reimport would silently revert any deliberate per-asset tweak.
            if (!importer.importSettingsMissing) return;

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = 64f;
            importer.filterMode = FilterMode.Point;
            importer.mipmapEnabled = false;
            importer.alphaIsTransparency = true;
            importer.textureCompression = TextureImporterCompression.Uncompressed;

            TextureImporterSettings settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;
            importer.SetTextureSettings(settings);
        }
    }
}
