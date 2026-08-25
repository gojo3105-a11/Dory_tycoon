using System.IO;
using GameFactory.Core;
using UnityEditor;
using UnityEngine;

namespace GameFactory.Editor
{
    /// <summary>
    /// Builds the temporary placeholder for the shared "MainCharacter" (도리/Dori)
    /// used across all 10 games until a real 3D model exists - see
    /// Assets/Common/Character/CHARACTER_DESIGN.md and Game01_IMPLEMENTATION_PLAN.md
    /// §4. Purely primitive shapes (capsule/sphere/cylinder/cube), no
    /// colliders and no Animator - this is a visual-only prefab meant to be
    /// nested under whatever gameplay root (2D or 3D) each game actually
    /// uses for movement/physics.
    /// </summary>
    public static class MainCharacterGenerator
    {
        public const string PrefabFolder = "Assets/Common/Character/Prefabs";
        public const string PrefabPath = PrefabFolder + "/MainCharacter.prefab";
        private const string MaterialFolder = "Assets/Common/Character/Materials";

        private static readonly Color CreamColor = new Color(0.95f, 0.87f, 0.75f);
        private static readonly Color HairColor = new Color(0.55f, 0.27f, 0.15f);
        private static readonly Color BowTieColor = new Color(0.12f, 0.16f, 0.35f);

        [MenuItem("Game Factory/Generate/Main Character Placeholder (Dori)")]
        private static void RegenerateMenuItem()
        {
            GameObject prefab = BuildAndSavePrefab();
            EditorUtility.DisplayDialog("Game Factory", $"MainCharacter placeholder (re)generated:\n{AssetDatabase.GetAssetPath(prefab)}", "OK");
        }

        /// <summary>Returns the existing MainCharacter prefab, or creates the placeholder if none exists yet.</summary>
        public static GameObject EnsureMainCharacterPrefab()
        {
            GameObject existing = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
            return existing != null ? existing : BuildAndSavePrefab();
        }

        private static GameObject BuildAndSavePrefab()
        {
            Directory.CreateDirectory(EditorPaths.ToAbsolutePath(PrefabFolder));
            Directory.CreateDirectory(EditorPaths.ToAbsolutePath(MaterialFolder));

            // AssetDatabase.CreateAsset below refuses to write into a folder
            // the database has not seen yet, so make it pick these up first.
            AssetDatabase.Refresh();

            Material creamMat = GetOrCreateMaterial("Cream.mat", CreamColor);
            Material hairMat = GetOrCreateMaterial("Hair.mat", HairColor);
            Material bowTieMat = GetOrCreateMaterial("BowTie.mat", BowTieColor);

            GameObject root = new GameObject("MainCharacter");

            AddPrimitiveChild(root.transform, "Body", PrimitiveType.Capsule, creamMat,
                localPosition: new Vector3(0f, 0.5f, 0f), localScale: new Vector3(0.6f, 0.5f, 0.5f));

            Transform head = AddPrimitiveChild(root.transform, "Head", PrimitiveType.Sphere, creamMat,
                localPosition: new Vector3(0f, 1.05f, 0f), localScale: new Vector3(0.5f, 0.5f, 0.5f));

            AddPrimitiveChild(head, "EarL", PrimitiveType.Sphere, creamMat,
                localPosition: new Vector3(-0.35f, 0.35f, 0f), localScale: new Vector3(0.25f, 0.25f, 0.25f));
            AddPrimitiveChild(head, "EarR", PrimitiveType.Sphere, creamMat,
                localPosition: new Vector3(0.35f, 0.35f, 0f), localScale: new Vector3(0.25f, 0.25f, 0.25f));

            Transform hairSpike = AddPrimitiveChild(head, "HairSpike", PrimitiveType.Cylinder, hairMat,
                localPosition: new Vector3(0f, 0.55f, -0.05f), localScale: new Vector3(0.16f, 0.5f, 0.16f));
            hairSpike.localRotation = Quaternion.Euler(-20f, 0f, 0f);

            AddPrimitiveChild(root.transform, "BowTie", PrimitiveType.Cube, bowTieMat,
                localPosition: new Vector3(0f, 0.78f, 0.28f), localScale: new Vector3(0.28f, 0.14f, 0.08f));

            root.AddComponent<MainCharacterSkin>();

            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
            Object.DestroyImmediate(root);

            Debug.Log($"[MainCharacterGenerator] Placeholder prefab saved at {PrefabPath} - temporary primitives only, not a real 3D model. See Assets/Common/Character/CHARACTER_DESIGN.md.");
            return prefab;
        }

        private static Transform AddPrimitiveChild(Transform parent, string name, PrimitiveType type, Material material, Vector3 localPosition, Vector3 localScale)
        {
            GameObject go = GameObject.CreatePrimitive(type);
            go.name = name;

            // Visual-only placeholder: no physics collisions come from this
            // hierarchy. (Which Collider subclass CreatePrimitive attaches
            // varies by primitive, hence the base-class lookup.)
            Collider autoCollider = go.GetComponent<Collider>();
            if (autoCollider != null) Object.DestroyImmediate(autoCollider);

            go.GetComponent<MeshRenderer>().sharedMaterial = material;

            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPosition;
            go.transform.localScale = localScale;

            return go.transform;
        }

        private static Material GetOrCreateMaterial(string fileName, Color color)
        {
            string assetPath = $"{MaterialFolder}/{fileName}";
            Material existing = AssetDatabase.LoadAssetAtPath<Material>(assetPath);
            if (existing != null) return existing;

            Material material = new Material(Shader.Find("Standard")) { color = color };
            AssetDatabase.CreateAsset(material, assetPath);
            return material;
        }
    }
}
