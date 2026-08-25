using System;

namespace GameFactory.Core.Spec
{
    /// <summary>
    /// Root data structure for a GameSpec JSON file. Every field is a plain
    /// value type so it round-trips cleanly through UnityEngine.JsonUtility
    /// (no dictionaries, no polymorphism, no nullable reference types).
    /// </summary>
    [Serializable]
    public class GameSpec
    {
        public GameInfo game = new GameInfo();
        public PlayerConfig player = new PlayerConfig();
        public MechanicsConfig mechanics = new MechanicsConfig();
        public LevelConfig level = new LevelConfig();
        public EnemyConfig enemy = new EnemyConfig();
        public SpecialConfig special = new SpecialConfig();
        public ThemeConfig theme = new ThemeConfig();
    }

    [Serializable]
    public class GameInfo
    {
        /// <summary>Lowercase, underscore-separated unique id, e.g. "game01".</summary>
        public string id = string.Empty;
        public string title = string.Empty;
        /// <summary>Must match a name in GameGenre.</summary>
        public string genre = string.Empty;
    }

    [Serializable]
    public class PlayerConfig
    {
        public float moveSpeed = 6f;
        public float jumpPower = 10f;
    }

    [Serializable]
    public class MechanicsConfig
    {
        public bool jump = true;
        public bool doubleJump;
        public bool dash;
        public bool wallJump;
        public bool gravitySwitch;
        public bool teleport;
        public bool timeSlow;
    }

    [Serializable]
    public class LevelConfig
    {
        public int levelCount = 1;
        /// <summary>Easy, Medium, or Hard.</summary>
        public string difficulty = "Medium";
        public bool procedural = true;
        /// <summary>Approximate level length in world units (Runner) or cells (Puzzle).</summary>
        public float length = 60f;
    }

    [Serializable]
    public class EnemyConfig
    {
        public bool enabled;
        public int types;
    }

    [Serializable]
    public class SpecialConfig
    {
        /// <summary>Name of a single headline gimmick module, e.g. "GravitySwitch", "FallingFloor".</summary>
        public string mechanic = string.Empty;
    }

    [Serializable]
    public class ThemeConfig
    {
        public string environment = string.Empty;
        public string character = string.Empty;
    }
}
