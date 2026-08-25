using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>
    /// Shop-purchased passive item: while owned, auto-collects any Coin that
    /// enters this larger trigger radius around the player. Switches itself
    /// off in Start when the magnet has not been bought, so an unpurchased
    /// magnet has no effect.
    /// </summary>
    [RequireComponent(typeof(CircleCollider2D))]
    public class CoinMagnet : MonoBehaviour
    {
        private const float Radius = 2.5f;

        private void Awake()
        {
            CircleCollider2D col = GetComponent<CircleCollider2D>();
            col.isTrigger = true;
            col.radius = Radius;
        }

        /// <summary>
        /// Ownership is read here rather than in Awake because it needs
        /// GameManager.Instance, which is only guaranteed once every Awake in
        /// the scene has run. Disabling in Awake instead would be a trap:
        /// Unity never calls Start on a component already disabled by then,
        /// so the magnet could never switch itself back on. Nothing is missed
        /// by waiting - physics (and so OnTriggerEnter2D) first runs after Start.
        /// </summary>
        private void Start()
        {
            string gameId = GameManager.Instance != null ? GameManager.Instance.GameId : string.Empty;
            enabled = SaveSystem.GetInt(gameId, ShopKeys.CoinMagnetOwned) != 0;
        }

        private void OnTriggerEnter2D(Collider2D other)
        {
            other.GetComponent<Coin>()?.Collect();
        }
    }
}
