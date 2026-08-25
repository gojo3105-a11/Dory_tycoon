using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>
    /// Applies the shop-purchased skin to the shared MainCharacter visual by
    /// recoloring its placeholder primitives - a real skin swap (different
    /// mesh/texture) can replace this once actual character art exists,
    /// without changing how the shop purchases/equips it.
    /// </summary>
    public class MainCharacterSkin : MonoBehaviour
    {
        private static readonly Color RedSkinColor = new Color(0.75f, 0.15f, 0.15f);

        private void Start()
        {
            string gameId = GameManager.Instance != null ? GameManager.Instance.GameId : string.Empty;
            if (SaveSystem.GetInt(gameId, ShopKeys.RedSkinEquipped) == 0) return;

            ApplyColorIfPresent("Body");
            ApplyColorIfPresent("Head");
        }

        private void ApplyColorIfPresent(string childName)
        {
            Transform child = transform.Find(childName);
            Renderer renderer = child != null ? child.GetComponent<Renderer>() : null;
            if (renderer != null) renderer.material.color = RedSkinColor;
        }
    }
}
