using GameFactory.Core;
using GameFactory.Modules.GravitySwitch;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>Periodically spawns alternating normal/inverted GravitySwitchZone volumes ahead of the player.</summary>
    public class GravityZoneSpawner : MonoBehaviour
    {
        [SerializeField] private GameObject zonePrefab;
        [SerializeField] private Transform player;
        [SerializeField] private float spawnAheadDistance = 12f;
        [SerializeField] private float zoneY;
        [SerializeField] private float zoneLength = 12f;
        [SerializeField] private float zoneHeight = 6f;
        [SerializeField] private float gapBetweenZones = 24f;

        private GameObjectPool pool;
        private float nextSpawnX;
        private bool nextInverted = true;

        /// <summary>Wires structural references. Called at edit time by LevelGenerator.</summary>
        public void SetReferences(GameObject prefab, Transform playerTransform, float y)
        {
            zonePrefab = prefab;
            player = playerTransform;
            zoneY = y;
        }

        /// <summary>Applies GameSpec-driven tuning. Called at edit time by LevelGenerator.</summary>
        public void Configure(float levelLength)
        {
            zoneLength = Mathf.Max(4f, levelLength * 0.4f);
            gapBetweenZones = Mathf.Max(zoneLength, levelLength * 0.6f);
        }

        private void Awake()
        {
            pool = gameObject.AddComponent<GameObjectPool>();
            pool.Initialize(zonePrefab, 4);
            nextSpawnX = (player != null ? player.position.x : 0f) + spawnAheadDistance + gapBetweenZones;
        }

        private void Update()
        {
            if (player == null || zonePrefab == null) return;

            while (nextSpawnX < player.position.x + spawnAheadDistance)
            {
                SpawnAt(nextSpawnX);
                nextSpawnX += zoneLength + gapBetweenZones;
            }
        }

        private void SpawnAt(float x)
        {
            GameObject instance = pool.Get(new Vector3(x + zoneLength / 2f, zoneY, 0f), Quaternion.identity);

            BoxCollider2D box = instance.GetComponent<BoxCollider2D>();
            if (box != null) box.size = new Vector2(zoneLength, zoneHeight);

            SpriteRenderer sr = instance.GetComponent<SpriteRenderer>();
            if (sr != null) sr.size = new Vector2(zoneLength, zoneHeight);

            GravitySwitchZone zone = instance.GetComponent<GravitySwitchZone>();
            if (zone != null) zone.Configure(nextInverted);
            nextInverted = !nextInverted;

            RecycleWhenPassed recycle = instance.GetComponent<RecycleWhenPassed>();
            if (recycle == null) recycle = instance.AddComponent<RecycleWhenPassed>();
            recycle.Initialize(pool, player, zoneLength + 4f);
        }
    }
}
