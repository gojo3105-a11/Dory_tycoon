using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>
    /// Attached to pooled runner objects (ground tiles, obstacles, coins) so
    /// they return themselves to their pool once the player has run past them,
    /// or immediately on request (e.g. a coin being collected).
    /// </summary>
    public class RecycleWhenPassed : MonoBehaviour
    {
        private GameObjectPool pool;
        private Transform player;
        private float behindDistance = 6f;

        public void Initialize(GameObjectPool ownerPool, Transform playerTransform, float recycleBehindDistance = 6f)
        {
            pool = ownerPool;
            player = playerTransform;
            behindDistance = recycleBehindDistance;
        }

        public void ReleaseNow()
        {
            if (pool != null) pool.Release(gameObject);
        }

        private void Update()
        {
            if (player == null || pool == null) return;

            if (player.position.x - transform.position.x > behindDistance)
            {
                ReleaseNow();
            }
        }
    }
}
