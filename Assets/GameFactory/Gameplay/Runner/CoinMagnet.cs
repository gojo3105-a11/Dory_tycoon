using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>
    /// Shop-purchased passive item: while owned, auto-collects any Coin that
    /// enters this larger trigger radius around the player. Disabled by
    /// default so an unpurchased magnet has no effect.
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

            // Ownership depends on GameManager.Instance, which is only
            // guaranteed set by Start (Unity runs all Awake calls in the
            // scene before any Start call) - stay disabled until then.
            enabled = false;
        }

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
