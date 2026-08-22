using UnityEngine;

namespace GameFactory.Modules.GravitySwitch
{
    /// <summary>A trigger volume that flips global gravity while the player is inside it.</summary>
    [RequireComponent(typeof(Collider2D))]
    public class GravitySwitchZone : MonoBehaviour
    {
        [SerializeField] private bool invertGravityInsideZone = true;
        [SerializeField] private string playerTag = "Player";

        public void Configure(bool invertInsideZone) => invertGravityInsideZone = invertInsideZone;

        private void Reset()
        {
            Collider2D col = GetComponent<Collider2D>();
            if (col != null) col.isTrigger = true;
        }

        private void OnTriggerEnter2D(Collider2D other)
        {
            if (!other.CompareTag(playerTag)) return;
            GravitySwitchController.SetInverted(invertGravityInsideZone);
        }

        private void OnTriggerExit2D(Collider2D other)
        {
            if (!other.CompareTag(playerTag)) return;
            GravitySwitchController.SetInverted(!invertGravityInsideZone);
        }
    }
}
