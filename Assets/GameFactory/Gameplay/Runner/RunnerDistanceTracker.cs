using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>
    /// Turns how far the player has auto-run into the run's score, in metres.
    ///
    /// Until this existed the Runner had no distance metric at all: Coin was
    /// the only caller of AddScore, so "score" was literally the number of
    /// coins picked up and a long clean run scored zero. Distance is the
    /// genre's headline number; coins are the shop currency (GameManager.Coins).
    /// </summary>
    public class RunnerDistanceTracker : MonoBehaviour
    {
        [SerializeField] private Transform player;

        /// <summary>
        /// World units per displayed metre. 1 keeps the number honest against
        /// the level geometry: a ground tile is 10 units wide, so a tile is
        /// 10 m and the default moveSpeed of 6 reads as 6 m/s.
        /// </summary>
        [SerializeField] private float unitsPerMetre = 1f;

        private float originX;
        private bool tracking;

        /// <summary>Wires structural references. Called at edit time by SceneGenerator.</summary>
        public void SetTarget(Transform playerTransform) => player = playerTransform;

        private void Update()
        {
            GameManager manager = GameManager.Instance;
            if (player == null || manager == null) return;

            if (manager.CurrentState != GameManager.GameState.Playing)
            {
                // Re-arm so the next run measures from wherever the player
                // actually starts, rather than from the previous run's origin.
                tracking = false;
                return;
            }

            if (!tracking)
            {
                originX = player.position.x;
                tracking = true;
                return;
            }

            if (unitsPerMetre <= 0f) return;

            // Floor, not round: the counter should never show a metre the
            // player has not finished covering.
            int metres = Mathf.FloorToInt((player.position.x - originX) / unitsPerMetre);
            if (metres > 0) manager.SetScore(metres);
        }
    }
}
