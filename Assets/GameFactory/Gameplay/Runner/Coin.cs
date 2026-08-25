using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>Adds score and returns itself to its pool when the player touches it.</summary>
    [RequireComponent(typeof(Collider2D))]
    public class Coin : MonoBehaviour
    {
        [SerializeField] private int scoreValue = 1;
        [SerializeField] private string playerTag = "Player";

        private bool collected;

        private void Reset()
        {
            Collider2D col = GetComponent<Collider2D>();
            if (col != null) col.isTrigger = true;
        }

        /// <summary>Called by CoinSpawner when this pooled instance is reused.</summary>
        public void ResetState() => collected = false;

        /// <summary>Collects this coin. Called directly by CoinMagnet, or via the trigger below on direct player contact.</summary>
        public void Collect()
        {
            if (collected) return;

            collected = true;
            GameManager.Instance.AddScore(scoreValue);
            GetComponent<RecycleWhenPassed>()?.ReleaseNow();
        }

        private void OnTriggerEnter2D(Collider2D other)
        {
            if (!other.CompareTag(playerTag)) return;
            Collect();
        }
    }
}
