using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>
    /// Supplies a font that can actually draw Hangul.
    ///
    /// The UI is Korean, but every Text in a generated scene was assigned
    /// Unity's built-in LegacyRuntime.ttf, which is a Latin-only Liberation
    /// Sans. Its glyph table has no Hangul, so on a device the shop's "상점"
    /// and "구매" render as tofu boxes - which is very likely part of what
    /// looked wrong about the buttons. This asks the OS for a Korean face
    /// instead and falls back to the built-in font if the platform has none.
    /// </summary>
    public static class KoreanFont
    {
        /// <summary>
        /// Candidate OS font families, most-specific first. Unity resolves
        /// these against the platform's installed fonts and uses the ones it
        /// finds as a fallback chain, so listing Android and Windows names
        /// together is deliberate: the Editor picks up Malgun Gothic, a device
        /// picks up Noto Sans CJK KR, and neither has to know about the other.
        /// </summary>
        private static readonly string[] Candidates =
        {
            "Noto Sans CJK KR",   // Android 5+ system Korean face
            "NotoSansKR",
            "NanumGothic",        // common on Samsung devices
            "Malgun Gothic",      // Windows (Unity Editor)
            "AppleSDGothicNeo-Regular",
            "Droid Sans Fallback" // last-ditch CJK-capable face on older Android
        };

        private static Font cached;
        private static bool resolved;

        /// <summary>
        /// The shared Korean-capable font, or Unity's built-in font when the
        /// platform offers nothing better. Never null.
        ///
        /// The result is cached in a static field on purpose: a dynamic font
        /// created here is a plain managed object with no scene reference, so
        /// dropping it would let Unity collect the font - and every Text using
        /// it would go blank - the next time the GC ran.
        /// </summary>
        public static Font Get()
        {
            if (resolved) return cached;

            resolved = true;

            // Not supported on every platform, and documented to be able to
            // return null, so this is guarded rather than trusted.
            Font osFont = Font.CreateDynamicFontFromOSFont(Candidates, 48);
            cached = osFont != null ? osFont : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            // Say so out loud when the result still cannot draw Hangul. Every
            // label in this game is Korean, so the alternative is a screen of
            // tofu boxes with nothing in the log explaining it - the exact
            // silent-failure shape that wastes an afternoon on a device.
            if (!HasHangul(cached))
            {
                Debug.LogWarning(
                    "[KoreanFont] No Korean-capable font found on this platform " +
                    $"(tried: {string.Join(", ", Candidates)}). Korean labels will " +
                    "render as empty boxes. Fix: ship a Korean TTF in the project " +
                    "and load it instead of the OS font.");
            }

            return cached;
        }

        /// <summary>
        /// Whether the font can draw a representative Hangul syllable.
        /// HasCharacter only answers for dynamic fonts, so a built-in fallback
        /// reports false - which is the right answer here anyway, since the
        /// built-in font genuinely has no Hangul.
        /// </summary>
        private static bool HasHangul(Font font)
        {
            return font != null && font.dynamic && font.HasCharacter('가');
        }
    }
}
