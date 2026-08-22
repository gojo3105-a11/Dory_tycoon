using System;
using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>Spawns pooled obstacles ahead of the player at a difficulty-scaled random gap.</summary>
    public class ObstacleSpawner : MonoBehaviour
    {
        [SerializeField] private GameObject obstaclePrefab;
        [SerializeField] private Transform player;
        [SerializeField] private float spawnAheadDistance = 12f;
        [SerializeField] private float groundY;
        [SerializeField] private float minGap = 4f;
        [SerializeField] private float maxGap = 8f;

        private GameObjectPool pool;
        private float nextSpawnX;

        /// <summary>Wires structural references. Called at edit time by SceneGenerator.</summary>
        public void SetReferences(GameObject prefab, Transform playerTransform, float ground)
        {
            obstaclePrefab = prefab;
            player = playerTransform;
            groundY = ground;
        }

        /// <summary>Applies GameSpec-driven tuning. Called at runtime by RunnerGameInitializer.</summary>
        public void Configure(float levelLength, string difficulty)
        {
            float scale = string.Equals(difficulty, "Hard", StringComparison.OrdinalIgnoreCase) ? 0.7f
                : string.Equals(difficulty, "Easy", StringComparison.OrdinalIgnoreCase) ? 1.3f
                : 1f;

            minGap = Mathf.Max(2f, 4f * scale);
            maxGap = Mathf.Max(minGap + 1f, 8f * scale);
        }

        private void Awake()
        {
            pool = gameObject.AddComponent<GameObjectPool>();
            pool.Initialize(obstaclePrefab, 6);
            nextSpawnX = (player != null ? player.position.x : 0f) + spawnAheadDistance;
        }

        private void Update()
        {
            if (player == null) return;

            while (nextSpawnX < player.position.x + spawnAheadDistance)
            {
                SpawnAt(nextSpawnX);
                nextSpawnX += UnityEngine.Random.Range(minGap, maxGap);
            }
        }

        private void SpawnAt(float x)
        {
            GameObject instance = pool.Get(new Vector3(x, groundY, 0f), Quaternion.identity);
            RecycleWhenPassed recycle = instance.GetComponent<RecycleWhenPassed>();
            if (recycle == null) recycle = instance.AddComponent<RecycleWhenPassed>();
            recycle.Initialize(pool, player);
        }
    }
}
