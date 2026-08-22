namespace GameFactory.Core.Spec
{
    /// <summary>
    /// Supported game genres. New genres should only be added here once a
    /// matching folder exists under Assets/GameFactory/Gameplay/.
    /// </summary>
    public enum GameGenre
    {
        Runner,
        Puzzle,
        Physics,
        Idle,
        Defense,
        Merge,
        Arcade,
        Shooter
    }
}
