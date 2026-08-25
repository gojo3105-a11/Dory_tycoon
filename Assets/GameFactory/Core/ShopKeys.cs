namespace GameFactory.Core
{
    /// <summary>
    /// Single source of truth for the SaveSystem keys and prices the Shop
    /// (ShopController), CoinMagnet, and MainCharacterSkin all need to agree
    /// on - keeping them in one place avoids a silent mismatch from a typo'd
    /// string literal in one of the three.
    /// </summary>
    public static class ShopKeys
    {
        public const string Currency = "currency";
        public const string CoinMagnetOwned = "shop.coin_magnet.owned";
        public const string RedSkinOwned = "shop.red_skin.owned";
        public const string RedSkinEquipped = "shop.red_skin.equipped";

        public const int CoinMagnetCost = 50;
        public const int RedSkinCost = 30;
    }
}
