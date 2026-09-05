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

        // A gap must be longer than the jump that has to clear it, or the
        // player lands on the next obstacle no matter how well they time it.
        // 1.6x leaves room to land, recover and take off again; 3.0x is the
        // longest breather before the level reads as empty.
        private const float MinGapPerJump = 1.6f;
        private const float MaxGapPerJump = 3.0f;

        /// <summary>Applies GameSpec-driven tuning. Called at runtime by RunnerGameInitializer.
        ///
        /// jumpDistance is how far one jump actually carries the player, from
        /// RunnerPlayerController.JumpDistance. Spacing was a pair of fixed
        /// numbers before, so with the real arc of 12.2 units against a 4-8
        /// gap a single jump sailed over two or three obstacles.
        /// </summary>
        public void Configure(float levelLength, string difficulty, float jumpDistance = 0f)
        {
            float scale = string.Equals(difficulty, "Hard", StringComparison.OrdinalIgnoreCase) ? 0.8f
                : string.Equals(difficulty, "Easy", StringComparison.OrdinalIgnoreCase) ? 1.25f
                : 1f;

            // Falling back to the old constants when the arc is unknown keeps
            // an older scene working rather than spacing everything at zero.
            float reach = jumpDistance > 0.1f ? jumpDistance : 2.5f;

            minGap = Mathf.Max(2f, reach * MinGapPerJump * scale);
            maxGap = Mathf.Max(minGap + reach * 0.5f, reach * MaxGapPerJump * scale);
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
