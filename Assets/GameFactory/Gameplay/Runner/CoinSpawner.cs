using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>Spawns pooled, collectible coins ahead of the player at a fixed spacing.</summary>
    public class CoinSpawner : MonoBehaviour
    {
        [SerializeField] private GameObject coinPrefab;
        [SerializeField] private Transform player;
        [SerializeField] private float spawnAheadDistance = 12f;
        [SerializeField] private float coinY = 1f;
        [SerializeField] private float spacing = 3f;

        private GameObjectPool pool;
        private float nextSpawnX;

        /// <summary>Wires structural references. Called at edit time by SceneGenerator.</summary>
        public void SetReferences(GameObject prefab, Transform playerTransform, float y)
        {
            coinPrefab = prefab;
            player = playerTransform;
            coinY = y;
        }

        /// <summary>Applies GameSpec-driven tuning. Called at runtime by RunnerGameInitializer.</summary>
        public void Configure(float levelLength)
        {
            spacing = Mathf.Max(1.5f, levelLength / 40f);
        }

        private void Awake()
        {
            pool = gameObject.AddComponent<GameObjectPool>();
            pool.Initialize(coinPrefab, 10);
            nextSpawnX = (player != null ? player.position.x : 0f) + spawnAheadDistance;
        }

        private void Update()
        {
            if (player == null) return;

            while (nextSpawnX < player.position.x + spawnAheadDistance)
            {
                SpawnAt(nextSpawnX);
                nextSpawnX += spacing;
            }
        }

        private void SpawnAt(float x)
        {
            GameObject instance = pool.Get(new Vector3(x, coinY, 0f), Quaternion.identity);

            RecycleWhenPassed recycle = instance.GetComponent<RecycleWhenPassed>();
            if (recycle == null) recycle = instance.AddComponent<RecycleWhenPassed>();
            recycle.Initialize(pool, player);

            Coin coin = instance.GetComponent<Coin>();
            if (coin != null) coin.ResetState();
        }
    }
}
