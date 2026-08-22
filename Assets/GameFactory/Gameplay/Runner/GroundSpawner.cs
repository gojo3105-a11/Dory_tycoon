using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>Tiles an endless ground strip ahead of the player and recycles tiles once passed.</summary>
    public class GroundSpawner : MonoBehaviour
    {
        [SerializeField] private GameObject groundTilePrefab;
        [SerializeField] private Transform player;
        [SerializeField] private float tileWidth = 10f;
        [SerializeField] private float groundY = -1f;
        [SerializeField] private int tilesAhead = 3;

        private GameObjectPool pool;
        private float nextSpawnX;

        /// <summary>Wires structural references. Called at edit time by SceneGenerator.</summary>
        public void SetReferences(GameObject prefab, Transform playerTransform, float width, float ground)
        {
            groundTilePrefab = prefab;
            player = playerTransform;
            tileWidth = width;
            groundY = ground;
        }

        private void Awake()
        {
            pool = gameObject.AddComponent<GameObjectPool>();
            pool.Initialize(groundTilePrefab, tilesAhead + 2);
            nextSpawnX = 0f;

            for (int i = 0; i < tilesAhead; i++)
            {
                SpawnNextTile();
            }
        }

        private void Update()
        {
            if (player == null) return;

            while (nextSpawnX < player.position.x + tileWidth * tilesAhead)
            {
                SpawnNextTile();
            }
        }

        private void SpawnNextTile()
        {
            GameObject instance = pool.Get(new Vector3(nextSpawnX, groundY, 0f), Quaternion.identity);

            RecycleWhenPassed recycle = instance.GetComponent<RecycleWhenPassed>();
            if (recycle == null) recycle = instance.AddComponent<RecycleWhenPassed>();
            recycle.Initialize(pool, player, tileWidth * (tilesAhead + 1));

            nextSpawnX += tileWidth;
        }
    }
}
