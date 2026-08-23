using System.IO;
using UnityEditor;

namespace GameFactory.Editor
{
    /// <summary>
    /// Exits Unity from a CLI entry point AND writes a small sentinel file
    /// recording the exit code first. This exists because relying on the
    /// calling process's own exit code is not reliable for Unity batch mode
    /// on Windows - Unity can relaunch itself as a new process, so whatever
    /// process the shell was actually watching may exit long before the real
    /// work (and EditorApplication.Exit) happens. CI scripts instead poll for
    /// this sentinel file. See scripts/ci/wait-for-unity.ps1.
    /// </summary>
    public static class CommandLineExit
    {
        public static void Exit(int code, string sentinelName)
        {
            string path = Path.Combine(EditorPaths.ProjectRoot, "Logs", $"{sentinelName}.exitcode");
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, code.ToString());
            EditorApplication.Exit(code);
        }
    }
}
