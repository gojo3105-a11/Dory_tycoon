namespace GameFactory.Editor
{
    /// <summary>
    /// Derives each game's Android application id from its GameSpec id.
    /// Deliberately keeps the underscore (Android package segments allow it)
    /// so the mapping is unambiguous and trivially reversible - no clever
    /// string-mangling that could make two different game ids collide.
    /// </summary>
    public static class BundleIdUtility
    {
        private const string Prefix = "com.gamefactory.";

        public static string GetBundleId(string gameId) => Prefix + gameId;

        public static bool IsValidAndroidPackageName(string packageName)
        {
            if (string.IsNullOrEmpty(packageName)) return false;

            string[] segments = packageName.Split('.');
            if (segments.Length < 2) return false;

            foreach (string segment in segments)
            {
                if (segment.Length == 0 || !char.IsLetter(segment[0])) return false;

                foreach (char c in segment)
                {
                    if (!char.IsLetterOrDigit(c) && c != '_') return false;
                }
            }

            return true;
        }
    }
}
