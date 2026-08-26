using GameFactory.Core;
using UnityEngine;
using UnityEngine.UI;

namespace GameFactory.UI
{
    /// <summary>
    /// Drives the Shop panel: shows the player's persistent currency
    /// balance and lets them buy/equip the two MVP items (coin magnet,
    /// red skin). Reads/writes SaveSystem directly via ShopKeys - the
    /// items themselves (CoinMagnet, MainCharacterSkin) read the same keys
    /// independently at their own Start, so no runtime wiring is needed
    /// beyond the purchase happening before the next run starts.
    /// </summary>
    public class ShopController : MonoBehaviour
    {
        [SerializeField] private GameObject shopPanel;
        [SerializeField] private Text currencyText;
        [SerializeField] private Button openButton;
        [SerializeField] private Button coinMagnetButton;
        [SerializeField] private Text coinMagnetButtonLabel;
        [SerializeField] private Button redSkinButton;
        [SerializeField] private Text redSkinButtonLabel;
        [SerializeField] private Button closeButton;

        private string gameId;
        private PanelTransition shopTransition;

        /// <summary>Wires structural references. Called at edit time by SceneGenerator.</summary>
        public void SetReferences(GameObject panel, Text currency, Button open, Button coinMagnet, Text coinMagnetLabel, Button redSkin, Text redSkinLabel, Button close)
        {
            shopPanel = panel;
            currencyText = currency;
            openButton = open;
            coinMagnetButton = coinMagnet;
            coinMagnetButtonLabel = coinMagnetLabel;
            redSkinButton = redSkin;
            redSkinButtonLabel = redSkinLabel;
            closeButton = close;
        }

        /// <summary>
        /// Button clicks are hooked up here, at runtime, and not by
        /// SceneGenerator: onClick.AddListener registers a non-persistent
        /// listener, which is not serialized into the saved scene, so wiring
        /// it at edit time would silently produce dead buttons.
        /// </summary>
        private void Start()
        {
            gameId = GameManager.Instance != null ? GameManager.Instance.GameId : string.Empty;
            shopTransition = shopPanel != null ? shopPanel.GetComponent<PanelTransition>() : null;

            if (openButton != null) openButton.onClick.AddListener(Open);
            if (coinMagnetButton != null) coinMagnetButton.onClick.AddListener(HandleCoinMagnetClicked);
            if (redSkinButton != null) redSkinButton.onClick.AddListener(HandleRedSkinClicked);
            if (closeButton != null) closeButton.onClick.AddListener(Close);

            if (shopPanel != null) shopPanel.SetActive(false);
            Refresh();
        }

        public void Open()
        {
            if (shopTransition != null) shopTransition.Show();
            else if (shopPanel != null) shopPanel.SetActive(true);

            Refresh();
        }

        public void Close()
        {
            if (shopTransition != null) shopTransition.Hide();
            else if (shopPanel != null) shopPanel.SetActive(false);
        }

        private void HandleCoinMagnetClicked()
        {
            if (IsOwned(ShopKeys.CoinMagnetOwned)) return;
            TryPurchase(ShopKeys.CoinMagnetOwned, ShopKeys.CoinMagnetCost);
        }

        private void HandleRedSkinClicked()
        {
            if (!IsOwned(ShopKeys.RedSkinOwned))
            {
                TryPurchase(ShopKeys.RedSkinOwned, ShopKeys.RedSkinCost);
                return;
            }

            bool equipped = SaveSystem.GetInt(gameId, ShopKeys.RedSkinEquipped) != 0;
            SaveSystem.SaveInt(gameId, ShopKeys.RedSkinEquipped, equipped ? 0 : 1);
            Refresh();
        }

        private void TryPurchase(string ownedKey, int cost)
        {
            int currency = SaveSystem.GetInt(gameId, ShopKeys.Currency);
            if (currency < cost) return;

            SaveSystem.SaveInt(gameId, ShopKeys.Currency, currency - cost);
            SaveSystem.SaveInt(gameId, ownedKey, 1);
            Refresh();
        }

        private bool IsOwned(string key) => SaveSystem.GetInt(gameId, key) != 0;

        private void Refresh()
        {
            if (currencyText != null) currencyText.text = SaveSystem.GetInt(gameId, ShopKeys.Currency).ToString();

            if (coinMagnetButtonLabel != null)
            {
                coinMagnetButtonLabel.text = IsOwned(ShopKeys.CoinMagnetOwned) ? "보유중" : $"구매 ({ShopKeys.CoinMagnetCost})";
            }

            if (redSkinButtonLabel != null)
            {
                if (!IsOwned(ShopKeys.RedSkinOwned))
                {
                    redSkinButtonLabel.text = $"구매 ({ShopKeys.RedSkinCost})";
                }
                else
                {
                    redSkinButtonLabel.text = SaveSystem.GetInt(gameId, ShopKeys.RedSkinEquipped) != 0 ? "장착됨" : "장착";
                }
            }
        }
    }
}
