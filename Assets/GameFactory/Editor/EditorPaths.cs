using System.IO;
using UnityEngine;

namespace GameFactory.Editor
{
    /// <summary>Helpers for converting between Assets-relative paths and absolute filesystem paths.</summary>
    public static class EditorPaths
    {
        public static string ProjectRoot => Path.GetDirectoryName(Application.dataPath);

        public static string ToAbsolutePath(string projectRelativePath)
        {
            return Path.Combine(ProjectRoot, projectRelativePath);
        }
    }
}
