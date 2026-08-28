using System.IO;
using GameFactory.Core.Spec;
using GameFactory.Gameplay.Runner;
using GameFactory.Modules.GravitySwitch;
using UnityEditor;
using UnityEngine;

namespace GameFactory.Editor
{
    /// <summary>The set of prefab assets a generated Runner game needs to play.</summary>
    public readonly struct RunnerPrefabSet
    {
        public GameObject Player { get; }
        public GameObject GroundTile { get; }
        public GameObject Obstacle { get; }
        public GameObject Coin { get; }
        /// <summary>Null when the GameSpec does not use the GravitySwitch mechanic.</summary>
        public GameObject GravityZone { get; }
        public int GroundLayer { get; }

        public RunnerPrefabSet(GameObject player, GameObject groundTile, GameObject obstacle, GameObject coin, GameObject gravityZone, int groundLayer)
        {
            Player = player;
            GroundTile = groundTile;
            Obstacle = obstacle;
            Coin = coin;
            GravityZone = gravityZone;
            GroundLayer = groundLayer;
        }
    }

    /// <summary>
    /// Creates and saves the placeholder prefabs a Runner game needs: Player,
    /// GroundTile, Obstacle, Coin, and (when used) a GravityZone volume.
    /// Sprites are procedurally generated solid-color placeholders - real art
    /// can replace them later without touching any generation code.
    /// </summary>
    public static class PrefabGenerator
    {
        private const int SpriteSize = 64;

        /// <summary>
        /// Where licensed art packs land. A file here wins over the
        /// procedural placeholder of the same canonical name, so adding real
        /// art is purely additive - if the folder is empty the generator
        /// behaves exactly as before and the verified build cannot break.
        /// </summary>
        private const string SharedArtFolder = "Assets/Common/Art/Runner";

        public static RunnerPrefabSet GenerateRunnerPrefabs(GameSpec spec, string assetFolder)
        {
            int groundLayer = TagLayerUtility.EnsureLayer("Ground");
            TagLayerUtility.EnsureTag("Obstacle");

            GameObject player = CreatePlayerPrefab(spec, assetFolder, groundLayer);
            GameObject groundTile = CreateGroundTilePrefab(spec, assetFolder, 10f, groundLayer);
            GameObject obstacle = CreateObstaclePrefab(assetFolder);
            GameObject coin = CreateCoinPrefab(assetFolder);
            GameObject gravityZone = spec.mechanics.gravitySwitch ? CreateGravityZonePrefab(assetFolder) : null;

            return new RunnerPrefabSet(player, groundTile, obstacle, coin, gravityZone, groundLayer);
        }

        private static GameObject CreatePlayerPrefab(GameSpec spec, string assetFolder, int groundLayer)
        {
            GameObject go = new GameObject("Player");
            go.tag = "Player";

            Rigidbody2D rb = go.AddComponent<Rigidbody2D>();
            rb.freezeRotation = true;

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.size = Vector2.one * 0.9f;

            Transform groundCheck = new GameObject("GroundCheck").transform;
            groundCheck.SetParent(go.transform);
            groundCheck.localPosition = new Vector3(0f, -0.5f, 0f);

            InstantiateMainCharacterVisual(go.transform);

            GameObject magnetGO = new GameObject("CoinMagnet");
            magnetGO.transform.SetParent(go.transform, false);
            magnetGO.AddComponent<CoinMagnet>();

            RunnerPlayerController controller = go.AddComponent<RunnerPlayerController>();
            controller.SetGroundCheck(groundCheck, 1 << groundLayer);

            if (spec.mechanics.gravitySwitch) go.AddComponent<GravitySwitchVfx>();

            return SaveAsPrefab(go, assetFolder, "Player.prefab");
        }

        /// <summary>
        /// Attaches the shared MainCharacter(도리) prefab as a purely visual
        /// child - the 2D Rigidbody2D/Collider2D on the Player root above
        /// still drives all movement/collision, per Game01_IMPLEMENTATION_PLAN.md §1.
        /// </summary>
        private static void InstantiateMainCharacterVisual(Transform parent)
        {
            GameObject mainCharacterPrefab = MainCharacterGenerator.EnsureMainCharacterPrefab();
            GameObject instance = (GameObject)PrefabUtility.InstantiatePrefab(mainCharacterPrefab, parent);

            // Instantiating with a parent preserves world position, so pin the
            // visual to the gameplay root explicitly.
            instance.transform.localPosition = Vector3.zero;
            instance.transform.localRotation = Quaternion.identity;
        }

        private static GameObject CreateGroundTilePrefab(GameSpec spec, string assetFolder, float tileWidth, int groundLayer)
        {
            GameObject go = new GameObject("GroundTile");
            go.layer = groundLayer;

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = ResolveSprite("ground", assetFolder, "ground_sprite.png", MutedColorFromSeed(spec.theme.environment));
            sr.drawMode = SpriteDrawMode.Tiled;
            sr.size = new Vector2(tileWidth, 1f);

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.size = new Vector2(tileWidth, 1f);

            return SaveAsPrefab(go, assetFolder, "GroundTile.prefab");
        }

        private static GameObject CreateObstaclePrefab(string assetFolder)
        {
            GameObject go = new GameObject("Obstacle");
            go.tag = "Obstacle";

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = ResolveSprite("obstacle", assetFolder, "obstacle_sprite.png", new Color(0.85f, 0.15f, 0.15f));

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.isTrigger = true;
            col.size = SpriteWorldSize(sr.sprite, Vector2.one);

            return SaveAsPrefab(go, assetFolder, "Obstacle.prefab");
        }

        private static GameObject CreateCoinPrefab(string assetFolder)
        {
            GameObject go = new GameObject("Coin");

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = ResolveSprite("coin", assetFolder, "coin_sprite.png", new Color(1f, 0.85f, 0.2f), 48);

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.isTrigger = true;
            // Pickup stays slightly smaller than the art so a near miss reads
            // as a miss rather than a surprise grab.
            col.size = SpriteWorldSize(sr.sprite, Vector2.one) * 0.6f;

            go.AddComponent<Coin>();

            return SaveAsPrefab(go, assetFolder, "Coin.prefab");
        }

        private static GameObject CreateGravityZonePrefab(string assetFolder)
        {
            GameObject go = new GameObject("GravityZone");

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.isTrigger = true;
            col.size = new Vector2(10f, 6f);

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = ResolveSprite("gravity_zone", assetFolder, "gravity_zone_sprite.png", new Color(0.55f, 0.2f, 0.9f, 0.25f));
            sr.drawMode = SpriteDrawMode.Tiled;
            sr.size = new Vector2(10f, 6f);
            sr.sortingOrder = -1;

            go.AddComponent<GravitySwitchZone>();

            return SaveAsPrefab(go, assetFolder, "GravityZone.prefab");
        }

        /// <summary>
        /// Returns licensed art from SharedArtFolder when present, otherwise
        /// generates the solid-colour placeholder. Callers get a Sprite either
        /// way and do not need to care which they got.
        /// </summary>
        private static Sprite ResolveSprite(string canonicalName, string assetFolder, string placeholderFileName,
            Color placeholderColor, int placeholderSize = SpriteSize)
        {
            string artPath = $"{SharedArtFolder}/{canonicalName}.png";
            Sprite licensed = AssetDatabase.LoadAssetAtPath<Sprite>(artPath);
            if (licensed != null) return licensed;

            string placeholderPath = CreateSolidSprite(assetFolder, placeholderFileName, placeholderColor, placeholderSize);
            return AssetDatabase.LoadAssetAtPath<Sprite>(placeholderPath);
        }

        /// <summary>
        /// Sizes a collider from the sprite it is paired with. Real art can be
        /// any resolution, so a hardcoded collider size that matched the 64px
        /// placeholder would no longer line up with what the player sees.
        /// </summary>
        private static Vector2 SpriteWorldSize(Sprite sprite, Vector2 fallback)
        {
            if (sprite == null) return fallback;
            return sprite.bounds.size;
        }

        private static Color MutedColorFromSeed(string seed)
        {
            float hue = Mathf.Abs(SeedHash(seed + "_ground")) % 360 / 360f;
            return Color.HSVToRGB(hue, 0.25f, 0.4f);
        }

        private static int SeedHash(string seed)
        {
            return string.IsNullOrEmpty(seed) ? 0 : seed.GetHashCode();
        }

        private static string CreateSolidSprite(string assetFolder, string fileName, Color color, int size = SpriteSize)
        {
            string assetPath = $"{assetFolder}/{fileName}";
            Directory.CreateDirectory(EditorPaths.ToAbsolutePath(assetFolder));

            Texture2D texture = new Texture2D(size, size, TextureFormat.RGBA32, false);
            Color32[] pixels = new Color32[size * size];
            Color32 pixelColor = color;
            for (int i = 0; i < pixels.Length; i++) pixels[i] = pixelColor;
            texture.SetPixels32(pixels);
            texture.Apply();

            File.WriteAllBytes(EditorPaths.ToAbsolutePath(assetPath), texture.EncodeToPNG());
            Object.DestroyImmediate(texture);

            AssetDatabase.ImportAsset(assetPath);
            TextureImporter importer = (TextureImporter)AssetImporter.GetAtPath(assetPath);
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = size;
            importer.filterMode = FilterMode.Point;
            importer.mipmapEnabled = false;
            importer.alphaIsTransparency = true;
            importer.SaveAndReimport();

            return assetPath;
        }

        private static GameObject SaveAsPrefab(GameObject sceneInstance, string assetFolder, string fileName)
        {
            Directory.CreateDirectory(EditorPaths.ToAbsolutePath(assetFolder));
            string assetPath = $"{assetFolder}/{fileName}";
            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(sceneInstance, assetPath);
            Object.DestroyImmediate(sceneInstance);
            return prefab;
        }
    }
}
