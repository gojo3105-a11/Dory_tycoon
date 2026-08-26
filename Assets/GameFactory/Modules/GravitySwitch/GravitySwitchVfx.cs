using GameFactory.Core;
using UnityEngine;

namespace GameFactory.Modules.GravitySwitch
{
    /// <summary>Plays a burst on VfxManager wherever this is (the player) whenever gravity flips. Purely visual, holds no gameplay state.</summary>
    public class GravitySwitchVfx : MonoBehaviour
    {
        private static readonly Color BurstColor = new Color(0.55f, 0.2f, 0.9f);

        private void OnEnable()
        {
            GravitySwitchController.GravityInvertedChanged += HandleGravityInvertedChanged;
        }

        private void OnDisable()
        {
            GravitySwitchController.GravityInvertedChanged -= HandleGravityInvertedChanged;
        }

        private void HandleGravityInvertedChanged(bool inverted)
        {
            VfxManager.Instance?.PlayBurst(transform.position, BurstColor, 0.2f, 16);
        }
    }
}
