using System;
using UnityEditor;

namespace GameFactory.Editor
{
    /// <summary>
    /// Programmatically ensures required Tags/Layers exist before generated
    /// prefabs reference them, by editing ProjectSettings/TagManager.asset.
    /// This is the standard (if slightly obscure) way to manage tags/layers
    /// from an Editor script - there is no public UnityEditor.Tags API.
    /// </summary>
    public static class TagLayerUtility
    {
        private const int FirstUserLayer = 8; // layers 0-7 are Unity built-ins

        public static void EnsureTag(string tag)
        {
            SerializedObject tagManager = LoadTagManager();
            SerializedProperty tagsProp = tagManager.FindProperty("tags");

            for (int i = 0; i < tagsProp.arraySize; i++)
            {
                if (tagsProp.GetArrayElementAtIndex(i).stringValue == tag) return;
            }

            tagsProp.InsertArrayElementAtIndex(tagsProp.arraySize);
            tagsProp.GetArrayElementAtIndex(tagsProp.arraySize - 1).stringValue = tag;
            tagManager.ApplyModifiedPropertiesWithoutUndo();
        }

        /// <summary>Returns the layer index, creating the layer in the first free user slot if needed.</summary>
        public static int EnsureLayer(string layerName)
        {
            SerializedObject tagManager = LoadTagManager();
            SerializedProperty layersProp = tagManager.FindProperty("layers");

            for (int i = FirstUserLayer; i < layersProp.arraySize; i++)
            {
                if (layersProp.GetArrayElementAtIndex(i).stringValue == layerName) return i;
            }

            for (int i = FirstUserLayer; i < layersProp.arraySize; i++)
            {
                SerializedProperty slot = layersProp.GetArrayElementAtIndex(i);
                if (string.IsNullOrEmpty(slot.stringValue))
                {
                    slot.stringValue = layerName;
                    tagManager.ApplyModifiedPropertiesWithoutUndo();
                    return i;
                }
            }

            throw new InvalidOperationException($"No free layer slots available to create layer '{layerName}'.");
        }

        private static SerializedObject LoadTagManager()
        {
            UnityEngine.Object[] assets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/TagManager.asset");
            if (assets == null || assets.Length == 0)
            {
                throw new InvalidOperationException("Could not load ProjectSettings/TagManager.asset.");
            }

            return new SerializedObject(assets[0]);
        }
    }
}
