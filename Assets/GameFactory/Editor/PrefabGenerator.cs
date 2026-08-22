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
            string spritePath = CreateSolidSprite(assetFolder, "player_sprite.png", VividColorFromSeed(spec.game.id));

            GameObject go = new GameObject("Player");
            go.tag = "Player";

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = AssetDatabase.LoadAssetAtPath<Sprite>(spritePath);

            Rigidbody2D rb = go.AddComponent<Rigidbody2D>();
            rb.freezeRotation = true;

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.size = Vector2.one * 0.9f;

            Transform groundCheck = new GameObject("GroundCheck").transform;
            groundCheck.SetParent(go.transform);
            groundCheck.localPosition = new Vector3(0f, -0.5f, 0f);

            RunnerPlayerController controller = go.AddComponent<RunnerPlayerController>();
            controller.SetGroundCheck(groundCheck, 1 << groundLayer);

            return SaveAsPrefab(go, assetFolder, "Player.prefab");
        }

        private static GameObject CreateGroundTilePrefab(GameSpec spec, string assetFolder, float tileWidth, int groundLayer)
        {
            string spritePath = CreateSolidSprite(assetFolder, "ground_sprite.png", MutedColorFromSeed(spec.theme.environment));

            GameObject go = new GameObject("GroundTile");
            go.layer = groundLayer;

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = AssetDatabase.LoadAssetAtPath<Sprite>(spritePath);
            sr.drawMode = SpriteDrawMode.Tiled;
            sr.size = new Vector2(tileWidth, 1f);

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.size = new Vector2(tileWidth, 1f);

            return SaveAsPrefab(go, assetFolder, "GroundTile.prefab");
        }

        private static GameObject CreateObstaclePrefab(string assetFolder)
        {
            string spritePath = CreateSolidSprite(assetFolder, "obstacle_sprite.png", new Color(0.85f, 0.15f, 0.15f));

            GameObject go = new GameObject("Obstacle");
            go.tag = "Obstacle";

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = AssetDatabase.LoadAssetAtPath<Sprite>(spritePath);

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.isTrigger = true;
            col.size = Vector2.one;

            return SaveAsPrefab(go, assetFolder, "Obstacle.prefab");
        }

        private static GameObject CreateCoinPrefab(string assetFolder)
        {
            string spritePath = CreateSolidSprite(assetFolder, "coin_sprite.png", new Color(1f, 0.85f, 0.2f), 48);

            GameObject go = new GameObject("Coin");

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = AssetDatabase.LoadAssetAtPath<Sprite>(spritePath);

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.isTrigger = true;
            col.size = Vector2.one * 0.6f;

            go.AddComponent<Coin>();

            return SaveAsPrefab(go, assetFolder, "Coin.prefab");
        }

        private static GameObject CreateGravityZonePrefab(string assetFolder)
        {
            string spritePath = CreateSolidSprite(assetFolder, "gravity_zone_sprite.png", new Color(0.55f, 0.2f, 0.9f, 0.25f));

            GameObject go = new GameObject("GravityZone");

            BoxCollider2D col = go.AddComponent<BoxCollider2D>();
            col.isTrigger = true;
            col.size = new Vector2(10f, 6f);

            SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = AssetDatabase.LoadAssetAtPath<Sprite>(spritePath);
            sr.drawMode = SpriteDrawMode.Tiled;
            sr.size = new Vector2(10f, 6f);
            sr.sortingOrder = -1;

            go.AddComponent<GravitySwitchZone>();

            return SaveAsPrefab(go, assetFolder, "GravityZone.prefab");
        }

        private static Color VividColorFromSeed(string seed)
        {
            float hue = Mathf.Abs(SeedHash(seed)) % 360 / 360f;
            return Color.HSVToRGB(hue, 0.65f, 0.95f);
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
