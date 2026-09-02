using GameFactory.Core;
using UnityEngine;
using UnityEngine.UI;

namespace GameFactory.UI
{
    /// <summary>
    /// Swaps every Text under this object onto the Korean-capable font at
    /// startup.
    ///
    /// This has to happen at runtime rather than in SceneGenerator: the font
    /// comes from Font.CreateDynamicFontFromOSFont, which is a managed object
    /// with no asset path, so assigning it at edit time would serialise a null
    /// reference into the saved scene and every label would fall back to the
    /// Latin-only built-in font again.
    /// </summary>
    public class KoreanFontApplier : MonoBehaviour
    {
        private void Awake()
        {
            Font font = KoreanFont.Get();
            if (font == null) return;

            // true: labels inside GameOverPanel/ShopPanel are saved inactive
            // and would otherwise keep the built-in font.
            foreach (Text text in GetComponentsInChildren<Text>(true))
            {
                text.font = font;
            }
        }
    }
}
